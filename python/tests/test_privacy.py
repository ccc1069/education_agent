"""PrivacyService 单元测试: 同意 + 导出 + 删除。"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import (
    KnowledgeStateORM,
    LearnerORM,
    SubmissionORM,
    UserORM,
    UserRole,
)
from services import PrivacyService


# ---------- 辅助 ----------


async def _make_user(
    session: AsyncSession,
    email: str = "test@example.com",
    role: UserRole = UserRole.STUDENT,
    with_learner: bool = True,
) -> tuple[int, int | None]:
    learner_id = None
    if with_learner:
        learner = LearnerORM(public_id=f"pub_{email}", name="Test User")
        session.add(learner)
        await session.flush()
        learner_id = learner.id
    user = UserORM(
        email=email,
        password_hash="x",
        role=role,
        learner_id=learner_id,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user.id, learner_id


# ---------- 同意管理 ----------


@pytest.mark.asyncio
async def test_set_consent_creates_record(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, _ = await _make_user(s, "c1@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        result = await service.set_consent(user_id, "analytics", True, ip="1.2.3.4")
        assert result["granted"] is True
        assert result["consent_type"] == "analytics"
        assert result["ip"] == "1.2.3.4"


@pytest.mark.asyncio
async def test_set_consent_rejects_unknown_type(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, _ = await _make_user(s, "c2@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        with pytest.raises(ValueError, match="unknown consent_type"):
            await service.set_consent(user_id, "unknown_type", True)


@pytest.mark.asyncio
async def test_consent_status_defaults_all_false(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, _ = await _make_user(s, "c3@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        status = await service.get_consent_status(user_id)
        assert status == {
            "analytics": False,
            "llm_training": False,
            "marketing": False,
            "third_party_share": False,
        }


@pytest.mark.asyncio
async def test_consent_status_returns_latest_per_type(test_engine):
    """同一类型多次设置,取最新。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, _ = await _make_user(s, "c4@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        await service.set_consent(user_id, "analytics", True)
        await service.set_consent(user_id, "analytics", False)
        await service.set_consent(user_id, "marketing", True)

    async with async_session() as s:
        service = PrivacyService(s)
        status = await service.get_consent_status(user_id)
        assert status["analytics"] is False  # 最新一次
        assert status["marketing"] is True


@pytest.mark.asyncio
async def test_get_consents_returns_all_types(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, _ = await _make_user(s, "c5@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        await service.set_consent(user_id, "analytics", True)
        await service.set_consent(user_id, "llm_training", False)

    async with async_session() as s:
        service = PrivacyService(s)
        consents = await service.get_consents(user_id)
        types = {c["consent_type"] for c in consents}
        assert types == {"analytics", "llm_training"}


# ---------- 数据导出 ----------


@pytest.mark.asyncio
async def test_request_export_collects_user_data(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, learner_id = await _make_user(s, "e1@x.com")
        # 加点学习数据
        s.add(
            KnowledgeStateORM(
                learner_id=learner_id, knowledge_id="kp_a", mastery=0.8, attempts=5
            )
        )
        s.add(
            SubmissionORM(
                learner_id=learner_id, knowledge_id="kp_a", is_correct=True
            )
        )
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        job = await service.request_export(user_id)

    assert job["status"] == "completed"
    assert job["file_size_bytes"] > 0
    assert job["download_url"] == f"/api/v1/privacy/export/{job['id']}/download"

    # 取实际数据
    async with async_session() as s:
        service = PrivacyService(s)
        data = await service.get_export_data(job["id"], user_id)

    assert data["user"]["email"] == "e1@x.com"
    assert data["learner"]["public_id"] == "pub_e1@x.com"
    assert len(data["knowledge_states"]) == 1
    assert data["knowledge_states"][0]["knowledge_id"] == "kp_a"
    assert len(data["submissions"]) == 1
    assert "exported_at" in data


@pytest.mark.asyncio
async def test_get_export_data_rejects_other_user(test_engine):
    """用户只能取自己的导出数据。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_a, _ = await _make_user(s, "ea@x.com")
        user_b, _ = await _make_user(s, "eb@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        job = await service.request_export(user_a)

    async with async_session() as s:
        service = PrivacyService(s)
        # user_b 想拿 user_a 的导出
        result = await service.get_export_data(job["id"], user_b)
        assert result is None


@pytest.mark.asyncio
async def test_list_export_jobs_returns_history(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, _ = await _make_user(s, "e2@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        await service.request_export(user_id)
        await service.request_export(user_id)

    async with async_session() as s:
        service = PrivacyService(s)
        jobs = await service.list_export_jobs(user_id)
        assert len(jobs) == 2


# ---------- 账户删除 ----------


@pytest.mark.asyncio
async def test_request_deletion_schedules_30_days_later(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, _ = await _make_user(s, "d1@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        before = datetime.utcnow()
        result = await service.request_deletion(user_id, reason="leaving")
        after = datetime.utcnow()

    assert result["status"] == "pending"
    assert result["reason"] == "leaving"
    # scheduled_at 在 now + 30 天附近
    scheduled = datetime.fromisoformat(result["scheduled_at"])
    min_expected = before + timedelta(days=29, hours=23)
    max_expected = after + timedelta(days=30, minutes=1)
    assert min_expected <= scheduled <= max_expected


@pytest.mark.asyncio
async def test_request_deletion_idempotent(test_engine):
    """已有 pending 请求时再次提交,返回已存在的请求。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, _ = await _make_user(s, "d2@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        first = await service.request_deletion(user_id)
        second = await service.request_deletion(user_id)

    assert first["id"] == second["id"]


@pytest.mark.asyncio
async def test_cancel_deletion_during_grace_period(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, _ = await _make_user(s, "d3@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        await service.request_deletion(user_id)

    async with async_session() as s:
        service = PrivacyService(s)
        result = await service.cancel_deletion(user_id)

    assert result["status"] == "cancelled"
    assert result["cancelled_at"] is not None


@pytest.mark.asyncio
async def test_cancel_deletion_returns_none_if_no_request(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, _ = await _make_user(s, "d4@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        result = await service.cancel_deletion(user_id)
        assert result is None


@pytest.mark.asyncio
async def test_execute_deletion_soft_deletes_user_and_pii(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, learner_id = await _make_user(s, "d5@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        await service.request_deletion(user_id)

    async with async_session() as s:
        service = PrivacyService(s)
        result = await service.execute_deletion(user_id)

    assert result["status"] == "completed"
    assert result["completed_at"] is not None

    # 验证用户被软删
    from sqlalchemy import select
    async with async_session() as s:
        user = (
            await s.execute(select(UserORM).where(UserORM.id == user_id))
        ).scalar_one()
        assert user.is_active is False
        assert "[deleted:" in user.email
        assert user.password_hash == "x"

        learner = (
            await s.execute(select(LearnerORM).where(LearnerORM.id == learner_id))
        ).scalar_one()
        assert learner.name == "[deleted]"
        assert learner.profile == {}


@pytest.mark.asyncio
async def test_execute_deletion_fails_without_request(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, _ = await _make_user(s, "d6@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        with pytest.raises(ValueError, match="no active deletion request"):
            await service.execute_deletion(user_id)


@pytest.mark.asyncio
async def test_get_deletion_request_returns_active_only(test_engine):
    """cancelled/completed 的请求不在 active 中。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        user_id, _ = await _make_user(s, "d7@x.com")
        await s.commit()

    async with async_session() as s:
        service = PrivacyService(s)
        await service.request_deletion(user_id)
        await service.cancel_deletion(user_id)

    async with async_session() as s:
        service = PrivacyService(s)
        result = await service.get_deletion_request(user_id)
        assert result is None  # cancelled 不算 active
