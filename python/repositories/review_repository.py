"""复习计划仓储: SM-2 调度持久化。"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.spaced_repetition import ReviewItem
from db.models import ReviewScheduleORM
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ReviewScheduleRepository(BaseRepository[ReviewScheduleORM]):
    """SM-2 复习计划仓储。每个学习者+知识点一条记录。"""

    model = ReviewScheduleORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get(self, learner_id: int, knowledge_id: str) -> ReviewScheduleORM | None:
        result = await self.session.execute(
            select(ReviewScheduleORM).where(
                ReviewScheduleORM.learner_id == learner_id,
                ReviewScheduleORM.knowledge_id == knowledge_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_learner(self, learner_id: int) -> list[ReviewScheduleORM]:
        result = await self.session.execute(
            select(ReviewScheduleORM).where(ReviewScheduleORM.learner_id == learner_id)
        )
        return list(result.scalars().all())

    async def list_due(
        self, learner_id: int, now: datetime | None = None
    ) -> list[ReviewScheduleORM]:
        """获取到期需要复习的条目。"""
        now = now or datetime.now()
        result = await self.session.execute(
            select(ReviewScheduleORM)
            .where(
                ReviewScheduleORM.learner_id == learner_id,
                ReviewScheduleORM.next_review <= now,
            )
            .order_by(ReviewScheduleORM.next_review.asc())
        )
        return list(result.scalars().all())

    async def upsert_from_domain(
        self, learner_id: int, item: ReviewItem
    ) -> ReviewScheduleORM:
        """从 ReviewItem 同步到 DB(upsert)。

        PostgreSQL 走 ON CONFLICT(原子),其他 dialect 走 SELECT+INSERT/UPDATE。
        """
        values = {
            "learner_id": learner_id,
            "knowledge_id": item.knowledge_id,
            "easiness_factor": item.easiness_factor,
            "interval_days": item.interval_days,
            "repetition": item.repetition,
            "total_reviews": item.total_reviews,
            "next_review": item.next_review,
            "last_review": item.last_review,
        }

        if self.session.bind and self.session.bind.dialect.name == "postgresql":  # pragma: no cover
            stmt = pg_insert(ReviewScheduleORM).values(**values)  # pragma: no cover
            update_cols = {  # pragma: no cover
                "easiness_factor": stmt.excluded.easiness_factor,
                "interval_days": stmt.excluded.interval_days,
                "repetition": stmt.excluded.repetition,
                "total_reviews": stmt.excluded.total_reviews,
                "next_review": stmt.excluded.next_review,
                "last_review": stmt.excluded.last_review,
            }
            stmt = stmt.on_conflict_do_update(  # pragma: no cover
                constraint="uq_review_learner_knowledge", set_=update_cols
            ).returning(ReviewScheduleORM)
            result = await self.session.execute(stmt)  # pragma: no cover
            return result.scalar_one()  # pragma: no cover

        existing = await self.get(learner_id, item.knowledge_id)
        if existing is None:
            existing = ReviewScheduleORM(**values)
            self.session.add(existing)
        else:
            for k, v in values.items():
                setattr(existing, k, v)
        await self.session.flush()
        return existing

    def to_domain(self, record: ReviewScheduleORM) -> ReviewItem:
        """ORM -> ReviewItem。"""
        return ReviewItem(
            knowledge_id=record.knowledge_id,
            easiness_factor=record.easiness_factor,
            interval_days=record.interval_days,
            repetition=record.repetition,
            next_review=record.next_review,
            last_review=record.last_review,
            total_reviews=record.total_reviews,
        )
