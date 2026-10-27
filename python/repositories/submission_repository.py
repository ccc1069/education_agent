"""答题记录仓储: append-only 写入。"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import SubmissionORM
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class SubmissionRepository(BaseRepository[SubmissionORM]):
    model = SubmissionORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def record(
        self,
        learner_id: int,
        knowledge_id: str,
        is_correct: bool,
        time_spent_seconds: float = 0.0,
    ) -> SubmissionORM:
        """记录一次答题(append-only)。"""
        submission = SubmissionORM(
            learner_id=learner_id,
            knowledge_id=knowledge_id,
            is_correct=is_correct,
            time_spent_seconds=time_spent_seconds,
        )
        self.session.add(submission)
        await self.session.flush()
        return submission

    async def list_by_learner(
        self,
        learner_id: int,
        knowledge_id: str | None = None,
        limit: int = 100,
    ) -> list[SubmissionORM]:
        stmt = select(SubmissionORM).where(SubmissionORM.learner_id == learner_id)
        if knowledge_id:
            stmt = stmt.where(SubmissionORM.knowledge_id == knowledge_id)
        stmt = stmt.order_by(SubmissionORM.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_stats(
        self, learner_id: int, knowledge_id: str | None = None, window: int = 20
    ) -> dict[str, Any]:
        """最近 N 次答题的统计(用于 EngagementAgent 状态检测)。"""
        records = await self.list_by_learner(learner_id, knowledge_id, limit=window)
        if not records:
            return {"total": 0, "correct": 0, "accuracy": 0.0, "avg_time": 0.0}
        total = len(records)
        correct = sum(1 for r in records if r.is_correct)
        avg_time = sum(r.time_spent_seconds for r in records) / total
        return {
            "total": total,
            "correct": correct,
            "accuracy": correct / total,
            "avg_time": avg_time,
        }
