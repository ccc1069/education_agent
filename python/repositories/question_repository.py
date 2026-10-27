"""题目仓储: CRUD + 状态过滤 + embedding 相似度去重。"""

import logging
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import QuestionORM
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class QuestionRepository(BaseRepository[QuestionORM]):
    """题目仓储: CRUD + 状态机 + 列表过滤。"""

    model = QuestionORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_questions(
        self,
        status: str | None = None,
        knowledge_id: str | None = None,
        question_type: str | None = None,
        difficulty: int | None = None,
        created_by: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[QuestionORM]:
        """多条件过滤列表,按 created_at DESC + id DESC 排序。"""
        stmt = select(QuestionORM).order_by(
            QuestionORM.created_at.desc(), QuestionORM.id.desc()
        )
        if status:
            stmt = stmt.where(QuestionORM.status == status)
        if knowledge_id:
            stmt = stmt.where(QuestionORM.knowledge_id == knowledge_id)
        if question_type:
            stmt = stmt.where(QuestionORM.question_type == question_type)
        if difficulty is not None:
            stmt = stmt.where(QuestionORM.difficulty == difficulty)
        if created_by is not None:
            stmt = stmt.where(QuestionORM.created_by == created_by)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        question_id: int,
        status: str,
        reviewer_id: int | None = None,
    ) -> None:
        """更新题目状态(draft -> review -> published / rejected)。"""
        values: dict[str, Any] = {"status": status}
        if reviewer_id is not None:
            values["metadata_"] = {}  # 占位,实际可记 reviewer
        await self.session.execute(
            update(QuestionORM)
            .where(QuestionORM.id == question_id)
            .values(**values)
        )
        await self.session.flush()

    async def get_all_embeddings(self) -> list[QuestionORM]:
        """加载所有题目 + embedding(用于相似度去重)。"""
        result = await self.session.execute(
            select(QuestionORM).where(QuestionORM.content_embedding.is_not(None))
        )
        return list(result.scalars().all())

    async def delete(self, entity: QuestionORM) -> None:
        await self.session.delete(entity)
