"""LearnerModelService 单元测试: L1 缓存 + DB 持久化协调层。"""

import pytest

from core.learner_model import KnowledgeState, LearnerModel
from services.learner_model_service import LearnerModelService


@pytest.fixture
def service():
    return LearnerModelService()


def test_service_starts_with_empty_cache(service):
    assert service.cache == {}
    assert service.get_cached("any-id") is None


def test_put_and_get_cached(service):
    model = LearnerModel(learner_id="learner-1")
    service.put_cached(model, internal_id=42)
    assert service.get_cached("learner-1") is model
    assert service.get_internal_id("learner-1") == 42


def test_invalidate_removes_cache_and_id_map(service):
    model = LearnerModel(learner_id="learner-1")
    service.put_cached(model, internal_id=42)
    service.invalidate("learner-1")
    assert service.get_cached("learner-1") is None
    assert service.get_internal_id("learner-1") is None


def test_clear_wipes_all_state(service):
    m1 = LearnerModel(learner_id="learner-1")
    m2 = LearnerModel(learner_id="learner-2")
    service.put_cached(m1, internal_id=1)
    service.put_cached(m2, internal_id=2)
    service.clear()
    assert service.cache == {}
    assert service.get_internal_id("learner-1") is None


@pytest.mark.asyncio
async def test_load_creates_learner_if_missing(db_session, test_engine, monkeypatch):
    """load() 应在 DB 中为新学习者创建记录并缓存。"""
    from db import base as db_base
    from sqlalchemy.ext.asyncio import async_sessionmaker

    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False
    )
    monkeypatch.setattr(db_base, "AsyncSessionLocal", test_session_local)

    svc = LearnerModelService()
    model = await svc.load("new-learner-123")
    assert model.learner_id == "new-learner-123"
    assert svc.get_cached("new-learner-123") is model
    assert svc.get_internal_id("new-learner-123") is not None


@pytest.mark.asyncio
async def test_load_returns_cached_when_available(service):
    """已缓存的模型应直接返回,不查 DB。"""
    model = LearnerModel(learner_id="cached-learner")
    service.put_cached(model, internal_id=1)

    loaded = await service.load("cached-learner")
    assert loaded is model


@pytest.mark.asyncio
async def test_save_persists_knowledge_states(db_session, test_engine, monkeypatch):
    """save() 应将 model 的 knowledge_states 写入 DB。"""
    from db import base as db_base
    from sqlalchemy.ext.asyncio import async_sessionmaker

    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False
    )
    monkeypatch.setattr(db_base, "AsyncSessionLocal", test_session_local)

    svc = LearnerModelService()
    model = await svc.load("save-test-learner")

    # 添加一个知识点状态
    model.knowledge_states["arithmetic"] = KnowledgeState(knowledge_id="arithmetic")
    model.knowledge_states["arithmetic"].mastery = 0.75

    await svc.save(model)

    # 重新加载验证持久化
    svc.invalidate("save-test-learner")
    reloaded = await svc.load("save-test-learner")
    assert "arithmetic" in reloaded.knowledge_states
    assert reloaded.knowledge_states["arithmetic"].mastery == 0.75


@pytest.mark.asyncio
async def test_record_submission_writes_to_db(db_session, test_engine, monkeypatch):
    """record_submission() 应在 submissions 表新增记录。"""
    from db import base as db_base
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from repositories import SubmissionRepository

    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False
    )
    monkeypatch.setattr(db_base, "AsyncSessionLocal", test_session_local)

    svc = LearnerModelService()
    await svc.record_submission(
        learner_public_id="sub-test-learner",
        knowledge_id="arithmetic",
        is_correct=True,
        time_spent_seconds=15.0,
    )

    # 验证写入
    internal_id = svc.get_internal_id("sub-test-learner")
    assert internal_id is not None
    async with test_session_local() as s:
        sub_repo = SubmissionRepository(s)
        records = await sub_repo.list_by_learner(internal_id, "arithmetic")
        assert len(records) == 1
        assert records[0].is_correct is True
