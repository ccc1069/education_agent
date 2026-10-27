"""知识状态仓储: BKT 掌握度持久化 + CAS 乐观锁。"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import KnowledgeStateORM
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class OptimisticLockError(Exception):
    """knowledge_states CAS 冲突。"""


def _coerce_datetime(value: Any) -> datetime | None:
    """把 ISO 字符串等宽松输入规范为 datetime,避免 asyncpg 类型错误。"""
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            logger.warning("无法解析 last_attempt: %s", value)
            return None
    return None


class KnowledgeStateRepository(BaseRepository[KnowledgeStateORM]):
    """BKT 状态仓储。提供 CAS upsert。"""

    model = KnowledgeStateORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get(self, learner_id: int, knowledge_id: str) -> KnowledgeStateORM | None:
        result = await self.session.execute(
            select(KnowledgeStateORM).where(
                KnowledgeStateORM.learner_id == learner_id,
                KnowledgeStateORM.knowledge_id == knowledge_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_learner(self, learner_id: int) -> list[KnowledgeStateORM]:
        result = await self.session.execute(
            select(KnowledgeStateORM).where(KnowledgeStateORM.learner_id == learner_id)
        )
        return list(result.scalars().all())

    async def upsert_from_domain(
        self,
        learner_id: int,
        knowledge_id: str,
        state_dict: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> KnowledgeStateORM:
        """从领域对象同步到 DB，使用 WHERE version=? 的 CAS。

        冲突时最多重试 3 次（刷新 expected version，保留本次 mastery 字段）。
        成功后把新 version 写回 state_dict['version']（若传入可变 dict）。
        """
        if state_dict is None:
            state_dict = kwargs

        mastery = state_dict.get("mastery", 0.1)
        alpha = state_dict.get("alpha", 1.0)
        beta = state_dict.get("beta", 9.0)
        attempts = state_dict.get("attempts", 0)
        correct_count = state_dict.get("correct_count", 0)
        streak = state_dict.get("streak", 0)
        last_attempt = _coerce_datetime(state_dict.get("last_attempt"))
        expected = int(state_dict.get("version") or 0)

        for _ in range(3):
            existing = await self.get(learner_id, knowledge_id)
            if existing is None:
                new_state = KnowledgeStateORM(
                    learner_id=learner_id,
                    knowledge_id=knowledge_id,
                    mastery=mastery,
                    alpha=alpha,
                    beta=beta,
                    attempts=attempts,
                    correct_count=correct_count,
                    streak=streak,
                    last_attempt=last_attempt,
                    version=1,
                )
                try:
                    async with self.session.begin_nested():
                        self.session.add(new_state)
                        await self.session.flush()
                except IntegrityError:
                    continue
                state_dict["version"] = 1
                return new_state

            if expected <= 0:
                expected = int(existing.version or 1)

            stmt = (
                update(KnowledgeStateORM)
                .where(
                    KnowledgeStateORM.learner_id == learner_id,
                    KnowledgeStateORM.knowledge_id == knowledge_id,
                    KnowledgeStateORM.version == expected,
                )
                .values(
                    mastery=mastery,
                    alpha=alpha,
                    beta=beta,
                    attempts=attempts,
                    correct_count=correct_count,
                    streak=streak,
                    last_attempt=last_attempt,
                    version=expected + 1,
                )
            )
            result = await self.session.execute(stmt)
            if result.rowcount and result.rowcount > 0:
                await self.session.flush()
                state_dict["version"] = expected + 1
                existing.mastery = mastery
                existing.alpha = alpha
                existing.beta = beta
                existing.attempts = attempts
                existing.correct_count = correct_count
                existing.streak = streak
                existing.last_attempt = last_attempt
                existing.version = expected + 1
                return existing

            # 冲突：刷新 expected
            await self.session.refresh(existing)
            expected = int(existing.version or 0)
            logger.warning(
                "CAS conflict learner=%s kp=%s db_version=%s",
                learner_id,
                knowledge_id,
                expected,
            )

        raise OptimisticLockError(
            f"knowledge_states CAS failed: learner={learner_id} kp={knowledge_id}"
        )

    async def bulk_upsert(
        self, learner_id: int, states: dict[str, dict[str, Any]]
    ) -> int:
        """批量 CAS upsert。返回写入条数。"""
        if not states:
            return 0
        count = 0
        for knowledge_id, state_dict in states.items():
            await self.upsert_from_domain(learner_id, knowledge_id, state_dict)
            count += 1
        return count

    async def get_weak_points(
        self, learner_id: int, threshold: float = 0.4, limit: int = 10
    ) -> list[KnowledgeStateORM]:
        """获取薄弱知识点。"""
        result = await self.session.execute(
            select(KnowledgeStateORM)
            .where(
                KnowledgeStateORM.learner_id == learner_id,
                KnowledgeStateORM.mastery < threshold,
                KnowledgeStateORM.attempts > 0,
            )
            .order_by(KnowledgeStateORM.mastery.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
