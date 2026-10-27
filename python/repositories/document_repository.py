"""文档 + 分块仓储: RAG 知识库持久化。"""

import logging
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DocumentChunkORM, DocumentORM
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class DocumentRepository(BaseRepository[DocumentORM]):
    """文档仓储: CRUD + 去重。"""

    model = DocumentORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_content_hash(self, content_hash: str) -> DocumentORM | None:
        result = await self.session.execute(
            select(DocumentORM).where(DocumentORM.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def list_documents(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DocumentORM]:
        # 按 created_at DESC, 同 timestamp 时按 id DESC(同事务多行 timestamp 可能相同)
        stmt = select(DocumentORM).order_by(
            DocumentORM.created_at.desc(), DocumentORM.id.desc()
        )
        if status:
            stmt = stmt.where(DocumentORM.status == status)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        document_id: int,
        status: str,
        error_message: str | None = None,
        total_chunks: int | None = None,
    ) -> None:
        values: dict[str, Any] = {"status": status}
        if error_message is not None:
            values["error_message"] = error_message
        if total_chunks is not None:
            values["total_chunks"] = total_chunks
        await self.session.execute(
            update(DocumentORM).where(DocumentORM.id == document_id).values(**values)
        )
        await self.session.flush()


class DocumentChunkRepository(BaseRepository[DocumentChunkORM]):
    """文档分块仓储: 批量写入 + 按文档查询 + 向量检索(SQLite/PG 兼容)。"""

    model = DocumentChunkORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def bulk_create(self, chunks: list[dict[str, Any]]) -> list[DocumentChunkORM]:
        """批量创建分块。

        Args:
            chunks: list of dict with keys: document_id, chunk_index, content,
                    embedding, token_count, metadata
        """
        if not chunks:
            return []
        orm_objs = [DocumentChunkORM(**c) for c in chunks]
        self.session.add_all(orm_objs)
        await self.session.flush()
        return orm_objs

    async def list_by_document(self, document_id: int) -> list[DocumentChunkORM]:
        result = await self.session.execute(
            select(DocumentChunkORM)
            .where(DocumentChunkORM.document_id == document_id)
            .order_by(DocumentChunkORM.chunk_index.asc())
        )
        return list(result.scalars().all())

    async def delete_by_document(self, document_id: int) -> int:
        result = await self.session.execute(
            delete(DocumentChunkORM).where(
                DocumentChunkORM.document_id == document_id
            )
        )
        return result.rowcount or 0

    async def get_all_embeddings(self) -> list[DocumentChunkORM]:
        """加载所有 chunk + embedding(用于向量检索)。

        优化: 生产环境应用 pgvector 原生搜索,本方法供 SQLite/小规模知识库使用。
        """
        result = await self.session.execute(
            select(DocumentChunkORM).options()  # 不预加载 document 避免 N+1
        )
        return list(result.scalars().all())

    async def get_all_embeddings_with_documents(self) -> list[tuple[DocumentChunkORM, DocumentORM]]:
        """加载所有 chunk + 关联 document(用于返回检索结果时附带元信息)。"""
        from sqlalchemy.orm import selectinload

        result = await self.session.execute(
            select(DocumentChunkORM).options(selectinload(DocumentChunkORM.document))
        )
        chunks = result.scalars().all()
        return [(c, c.document) for c in chunks]
