"""向量存储: 跨方言检索。

设计:
- VectorStore 抽象: add / search / delete
- InMemoryVectorStore: 全量加载到内存,Python cosine 相似度
  - 优点: 跨方言(SQLite/PG 都可),无外部依赖
  - 缺点: 大规模知识库(>10k chunks)性能差
- PgVectorStore: pgvector 原生搜索(预留,生产用)
  - 用 :code:`<=>` (cosine distance) 算子
"""

import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DocumentChunkORM, DocumentORM
from repositories import DocumentChunkRepository

logger = logging.getLogger(__name__)


@dataclass
class ScoredChunk:
    """检索结果: chunk + 相似度分数 + 关联文档。"""

    chunk_id: int
    document_id: int
    content: str
    score: float
    chunk_index: int
    token_count: int
    metadata: dict[str, Any]
    document_title: str | None = None
    document_source_type: str | None = None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度。

    返回 [-1, 1],1 表示完全相似。
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorStore(ABC):
    """向量存储抽象。"""

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[ScoredChunk]:
        """检索最相似的 top_k 个 chunk。"""
        ...


class InMemoryVectorStore(VectorStore):
    """内存向量存储: 全量加载 + Python cosine 相似度。

    适用场景:
    - 单元测试
    - 小规模知识库(<10k chunks)
    - SQLite 部署

    生产环境大规模知识库应切换到 PgVectorStore。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._chunk_repo = DocumentChunkRepository(session)
        self._cache: list[tuple[DocumentChunkORM, DocumentORM | None]] | None = None

    async def _ensure_loaded(self) -> list[tuple[DocumentChunkORM, DocumentORM | None]]:
        if self._cache is None:
            pairs = await self._chunk_repo.get_all_embeddings_with_documents()
            self._cache = pairs
            logger.debug("InMemoryVectorStore loaded %d chunks", len(pairs))
        return self._cache

    def invalidate(self) -> None:
        """清除缓存(下次 search 时重新加载)。"""
        self._cache = None

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[ScoredChunk]:
        pairs = await self._ensure_loaded()
        scored: list[tuple[float, DocumentChunkORM, DocumentORM | None]] = []
        for chunk, doc in pairs:
            score = cosine_similarity(query_embedding, chunk.embedding or [])
            if score >= min_score:
                scored.append((score, chunk, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        results: list[ScoredChunk] = []
        for score, chunk, doc in scored[:top_k]:
            results.append(
                ScoredChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    content=chunk.content,
                    score=score,
                    chunk_index=chunk.chunk_index,
                    token_count=chunk.token_count,
                    metadata=chunk.metadata_ or {},
                    document_title=doc.title if doc else None,
                    document_source_type=doc.source_type if doc else None,
                )
            )
        return results


class PgVectorStore(VectorStore):  # pragma: no cover
    """pgvector 原生检索(生产用)。

    预留接口,需要 PG 安装 pgvector 扩展并启用。

    用法:
        ALTER DATABASE edu_agent SET ivfflat.probes = 10;
        CREATE INDEX ON document_chunks
            USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[ScoredChunk]:
        """用 pgvector 的 <=> 算子做原生搜索。

        <=> 是 cosine distance(0=完全相似,2=完全相反)
        相似度 = 1 - distance
        """
        from sqlalchemy import text

        # 注意: :name::type 会被 SQLAlchemy 误解析,须用 CAST(:name AS type)
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        sql = text(
            """
            SELECT
                c.id, c.document_id, c.content, c.chunk_index,
                c.token_count, c.metadata,
                1 - (c.embedding <=> CAST(:embedding AS vector)) AS score,
                d.title AS document_title, d.source_type AS document_source_type
            FROM document_chunks c
            LEFT JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
              AND 1 - (c.embedding <=> CAST(:embedding AS vector)) >= :min_score
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
            """
        )
        result = await self.session.execute(
            sql,
            {
                "embedding": embedding_str,
                "min_score": min_score,
                "top_k": top_k,
            },
        )
        rows = result.all()
        return [
            ScoredChunk(
                chunk_id=row[0],
                document_id=row[1],
                content=row[2],
                score=float(row[6]),
                chunk_index=row[3],
                token_count=row[4],
                metadata=row[5] or {},
                document_title=row[7],
                document_source_type=row[8],
            )
            for row in rows
        ]


def get_vector_store(session: AsyncSession) -> VectorStore:
    """工厂: 选 VectorStore。

    document_chunks.embedding / questions.content_embedding 当前为 JSON 数组,
    不能走 pgvector 的 <=> 算子。默认 InMemoryVectorStore(跨方言 cosine)。
    仅当环境变量 USE_PGVECTOR=1 且列为 vector 类型时启用 PgVectorStore。
    """
    import os

    if os.getenv("USE_PGVECTOR", "").strip().lower() in ("1", "true", "yes"):
        bind = session.bind
        if bind and bind.dialect.name == "postgresql":
            try:
                return PgVectorStore(session)
            except Exception as e:
                logger.warning("PgVectorStore init failed, fallback to InMemory: %s", e)
    return InMemoryVectorStore(session)
