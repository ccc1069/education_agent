"""RAG 服务: 文档摄取 + 检索编排。

职责:
1. ingest_document: 去重 -> 切块 -> embedding -> 落库
2. search: query embedding -> 向量检索 -> 分数过滤 -> 返回带引用的结果
3. delete_document: 级联删除文档 + 分块
"""

import hashlib
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DocumentORM
from rag import (
    EmbeddingProvider,
    ScoredChunk,
    VectorStore,
    chunk_text,
    get_embedding_provider,
    get_vector_store,
)
from repositories import DocumentChunkRepository, DocumentRepository

logger = logging.getLogger(__name__)


class RAGService:
    """RAG 服务: 文档摄取 + 检索。"""

    def __init__(
        self,
        session: AsyncSession,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.session = session
        self.doc_repo = DocumentRepository(session)
        self.chunk_repo = DocumentChunkRepository(session)
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self._vector_store = vector_store

    @property
    def vector_store(self) -> VectorStore:
        if self._vector_store is None:
            self._vector_store = get_vector_store(self.session)
        return self._vector_store

    async def ingest_document(
        self,
        title: str,
        content: str,
        source_type: str = "text",
        source_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[int, bool]:
        """摄取文档: 去重 + 切块 + embedding + 落库。

        Args:
            title: 文档标题
            content: 文档全文
            source_type: text/markdown/pdf/docx
            source_url: 原始 URL(可选)
            metadata: 额外元信息

        Returns:
            (document_id, is_new) - is_new=False 表示已存在(去重)
        """
        if not content or not content.strip():
            raise ValueError("Document content cannot be empty")

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        existing = await self.doc_repo.get_by_content_hash(content_hash)
        if existing is not None:
            logger.info(
                "Document already ingested (hash=%s): id=%d title=%s",
                content_hash[:8],
                existing.id,
                existing.title,
            )
            return existing.id, False

        document = DocumentORM(
            title=title,
            source_type=source_type,
            source_url=source_url,
            content_hash=content_hash,
            status="indexing",
            metadata_=metadata or {},
        )
        await self.doc_repo.add(document)
        await self.session.flush()

        try:
            chunks = chunk_text(content)
            if not chunks:
                await self.doc_repo.update_status(
                    document.id, "failed", error_message="No chunks generated"
                )
                await self.session.commit()
                return document.id, True

            embeddings = await self.embedding_provider.embed_batch(
                [c.content for c in chunks]
            )

            chunk_dicts = [
                {
                    "document_id": document.id,
                    "chunk_index": c.chunk_index,
                    "content": c.content,
                    "embedding": emb,
                    "token_count": c.token_count,
                    "metadata": {"source_type": source_type},
                }
                for c, emb in zip(chunks, embeddings)
            ]
            await self.chunk_repo.bulk_create(chunk_dicts)

            await self.doc_repo.update_status(
                document.id,
                "indexed",
                total_chunks=len(chunks),
            )
            await self.session.commit()

            # 让 VectorStore 重新加载缓存
            if hasattr(self.vector_store, "invalidate"):
                self.vector_store.invalidate()

            logger.info(
                "Document ingested: id=%d title=%s chunks=%d",
                document.id,
                title,
                len(chunks),
            )
            return document.id, True
        except Exception as e:
            logger.error("Document ingestion failed: id=%d err=%s", document.id, e)
            await self.doc_repo.update_status(
                document.id, "failed", error_message=str(e)[:500]
            )
            await self.session.commit()
            raise

    async def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.7,
    ) -> list[ScoredChunk]:
        """检索: query embedding -> 向量检索 -> 分数过滤。

        Args:
            query: 查询文本
            top_k: 返回前 K 个(默认 5)
            min_score: 最小相似度(默认 0.7,<0.7 不引用)

        Returns:
            list[ScoredChunk]: 按 score 降序
        """
        if not query or not query.strip():
            return []

        query_embedding = await self.embedding_provider.embed(query)
        results = await self.vector_store.search(
            query_embedding, top_k=top_k, min_score=min_score
        )
        logger.info(
            "RAG search: query=%r top_k=%d min_score=%.2f hits=%d",
            query[:50],
            top_k,
            min_score,
            len(results),
        )
        return results

    async def delete_document(self, document_id: int) -> bool:
        """删除文档 + 关联分块。"""
        document = await self.doc_repo.get_by_id(document_id)
        if document is None:
            return False

        await self.chunk_repo.delete_by_document(document_id)
        await self.doc_repo.delete(document)
        await self.session.commit()

        if hasattr(self.vector_store, "invalidate"):
            self.vector_store.invalidate()

        logger.info("Document deleted: id=%d title=%s", document_id, document.title)
        return True

    async def list_documents(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Any]:
        """列出文档(简化返回)。"""
        docs = await self.doc_repo.list_documents(status=status, limit=limit, offset=offset)
        return [
            {
                "id": d.id,
                "title": d.title,
                "source_type": d.source_type,
                "source_url": d.source_url,
                "status": d.status,
                "total_chunks": d.total_chunks,
                "content_hash": d.content_hash[:8] + "..." if d.content_hash else None,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "error_message": d.error_message,
            }
            for d in docs
        ]

    async def get_document(self, document_id: int) -> dict[str, Any] | None:
        """获取单个文档详情(含分块正文预览,不含 embedding)。"""
        d = await self.doc_repo.get_by_id(document_id)
        if d is None:
            return None
        chunks = await self.chunk_repo.list_by_document(document_id)
        return {
            "id": d.id,
            "title": d.title,
            "source_type": d.source_type,
            "source_url": d.source_url,
            "status": d.status,
            "total_chunks": d.total_chunks,
            "content_hash": d.content_hash,
            "metadata": d.metadata_,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            "error_message": d.error_message,
            "chunks": [
                {
                    "chunk_index": c.chunk_index,
                    "content": c.content,
                    "token_count": c.token_count,
                }
                for c in chunks
            ],
        }
