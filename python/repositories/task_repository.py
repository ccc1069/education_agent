"""任务执行历史仓储: P2#17 异步任务与定时调度。"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import TaskExecutionORM
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class TaskExecutionRepository(BaseRepository[TaskExecutionORM]):
    """任务执行历史仓储。"""

    model = TaskExecutionORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_recent(
        self,
        limit: int = 50,
        offset: int = 0,
        task_name: str | None = None,
        status: str | None = None,
    ) -> list[TaskExecutionORM]:
        stmt = select(TaskExecutionORM).order_by(
            TaskExecutionORM.id.desc()
        ).limit(limit).offset(offset)
        if task_name:
            stmt = stmt.where(TaskExecutionORM.task_name == task_name)
        if status:
            stmt = stmt.where(TaskExecutionORM.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_last_success(self, task_name: str) -> TaskExecutionORM | None:
        """获取某任务最后一次成功执行。"""
        result = await self.session.execute(
            select(TaskExecutionORM)
            .where(
                TaskExecutionORM.task_name == task_name,
                TaskExecutionORM.status == "success",
            )
            .order_by(TaskExecutionORM.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_by_status(self, status: str) -> int:
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(TaskExecutionORM.id)).where(
                TaskExecutionORM.status == status
            )
        )
        return result.scalar_one() or 0

    async def to_dict(self, t: TaskExecutionORM) -> dict[str, Any]:
        return {
            "id": t.id,
            "task_name": t.task_name,
            "status": t.status,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "duration_ms": t.duration_ms,
            "error_message": t.error_message,
            "metadata": t.metadata_ or {},
            "triggered_by": t.triggered_by,
        }
