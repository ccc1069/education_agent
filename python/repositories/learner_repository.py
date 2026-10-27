"""学习者仓储: 管理学习者基础信息。"""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import LearnerORM
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class LearnerRepository(BaseRepository[LearnerORM]):
    model = LearnerORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_public_id(self, public_id: str) -> LearnerORM | None:
        """根据外部 ID 查询学习者。"""
        result = await self.session.execute(
            select(LearnerORM).where(LearnerORM.public_id == public_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, public_id: str, name: str = "") -> LearnerORM:
        """获取或创建学习者(幂等)。"""
        learner = await self.get_by_public_id(public_id)
        if learner is not None:
            return learner
        learner = LearnerORM(public_id=public_id or str(uuid.uuid4()), name=name)
        self.session.add(learner)
        await self.session.flush()
        logger.info("Created new learner: %s", learner.public_id)
        return learner

    async def update_profile(self, public_id: str, profile: dict[str, Any]) -> LearnerORM | None:
        learner = await self.get_by_public_id(public_id)
        if learner is None:
            return None
        learner.profile = {**(learner.profile or {}), **profile}
        await self.session.flush()
        return learner
