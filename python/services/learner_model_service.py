"""学习者模型服务: L1 内存缓存 + DB 持久化的协调层。

设计:
- BaseAgent.get_learner_model() 保持同步,从 L1 缓存读
- 服务层负责首次加载(从 DB)、修改后写回
- 编排器在请求结束时调用 save() 持久化本次涉及的 learner
"""

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.learner_model import BKTParams, KnowledgeState, LearnerModel
from db import base as db_base
from repositories import (
    KnowledgeStateRepository,
    LearnerRepository,
    SubmissionRepository,
)

logger = logging.getLogger(__name__)


class LearnerModelService:
    """
    学习者模型服务。

    职责:
    1. 维护 L1 内存缓存(dict[public_id -> LearnerModel])
    2. 首次访问时从 DB 加载知识状态
    3. 修改后调用 save() 写回 DB(乐观锁)
    4. 记录答题(submissions 表,append-only)
    """

    def __init__(self) -> None:
        # L1 缓存: learner_public_id -> LearnerModel
        self._cache: dict[str, LearnerModel] = {}
        # DB 内部 ID 映射: public_id -> internal id
        self._id_map: dict[str, int] = {}
        self._bkt_params = BKTParams()

    @property
    def cache(self) -> dict[str, LearnerModel]:
        """暴露缓存 dict,供 Agent 同步读写。"""
        return self._cache

    def get_cached(self, learner_public_id: str) -> LearnerModel | None:
        return self._cache.get(learner_public_id)

    def put_cached(self, model: LearnerModel, internal_id: int) -> None:
        self._cache[model.learner_id] = model
        self._id_map[model.learner_id] = internal_id

    def get_internal_id(self, learner_public_id: str) -> int | None:
        return self._id_map.get(learner_public_id)

    def invalidate(self, learner_public_id: str) -> None:
        self._cache.pop(learner_public_id, None)
        self._id_map.pop(learner_public_id, None)

    def clear(self) -> None:
        self._cache.clear()
        self._id_map.clear()

    async def load(self, learner_public_id: str) -> LearnerModel:
        """从 DB 加载学习者模型(若已缓存则直接返回)。"""
        cached = self._cache.get(learner_public_id)
        if cached is not None:
            return cached

        async with db_base.AsyncSessionLocal() as session:
            learner_repo = LearnerRepository(session)
            state_repo = KnowledgeStateRepository(session)

            learner_orm = await learner_repo.get_or_create(
                public_id=learner_public_id or str(uuid.uuid4())
            )
            await session.commit()

            states_orm = await state_repo.list_by_learner(learner_orm.id)

        model = LearnerModel(learner_id=learner_orm.public_id, bkt_params=self._bkt_params)
        for s in states_orm:
            model.knowledge_states[s.knowledge_id] = KnowledgeState(
                knowledge_id=s.knowledge_id,
                mastery=s.mastery,
                alpha=s.alpha,
                beta=s.beta,
                attempts=s.attempts,
                correct_count=s.correct_count,
                streak=s.streak,
                last_attempt=s.last_attempt,
                version=s.version or 0,
            )

        self._cache[model.learner_id] = model
        self._id_map[model.learner_id] = learner_orm.id
        logger.info(
            "Loaded learner model from DB: %s (states=%d)",
            learner_orm.public_id,
            len(states_orm),
        )
        return model

    async def save(self, model: LearnerModel) -> None:
        """把模型知识状态同步回 DB(upsert)。"""
        internal_id = self._id_map.get(model.learner_id)
        if internal_id is None:
            async with db_base.AsyncSessionLocal() as session:
                learner_repo = LearnerRepository(session)
                learner_orm = await learner_repo.get_or_create(model.learner_id)
                await session.commit()
                internal_id = learner_orm.id
                self._id_map[model.learner_id] = internal_id

        async with db_base.AsyncSessionLocal() as session:
            state_repo = KnowledgeStateRepository(session)
            for knowledge_id, state in model.knowledge_states.items():
                dumped = state.model_dump(mode="python")
                await state_repo.upsert_from_domain(
                    internal_id,
                    knowledge_id,
                    dumped,
                )
                # CAS 成功后的 version 写回领域对象
                state.version = int(dumped.get("version") or state.version)
            await session.commit()
        logger.debug("Persisted learner model: %s", model.learner_id)

    async def record_submission(
        self,
        learner_public_id: str,
        knowledge_id: str,
        is_correct: bool,
        time_spent_seconds: float = 0.0,
    ) -> None:
        """记录一次答题到 submissions 表。"""
        async with db_base.AsyncSessionLocal() as session:
            learner_repo = LearnerRepository(session)
            submission_repo = SubmissionRepository(session)

            learner_orm = await learner_repo.get_or_create(learner_public_id)
            await submission_repo.record(
                learner_id=learner_orm.id,
                knowledge_id=knowledge_id,
                is_correct=is_correct,
                time_spent_seconds=time_spent_seconds,
            )
            await session.commit()
            self._id_map[learner_public_id] = learner_orm.id
