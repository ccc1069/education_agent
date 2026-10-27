"""具体定时任务测试: tasks/__init__.py 中的 4 个任务。

使用真实 SQLite in-memory DB(无 mock),验证:
- execute_pending_deletions: 到期删除请求被执行
- send_review_reminders: 到期复习计划被扫描
- cleanup_expired_tokens: 过期 token 被清理
- generate_daily_stats: 当日统计正确
- TASK_REGISTRY 完整性
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from db.models import (
    AuditLogORM,
    PrivacyDeletionRequestORM,
    RefreshTokenORM,
    ReviewScheduleORM,
    SubmissionORM,
    UserORM,
    LearnerORM,
    UserRole,
)
from tasks import (
    TASK_REGISTRY,
    cleanup_expired_tokens,
    execute_pending_deletions,
    generate_daily_stats,
    get_task_func,
    get_task_names,
    send_review_reminders,
)


# ---------- TASK_REGISTRY 完整性 ----------


def test_task_registry_contains_all_tasks():
    assert set(get_task_names()) == {
        "execute_pending_deletions",
        "send_review_reminders",
        "cleanup_expired_tokens",
        "generate_daily_stats",
    }


def test_task_registry_has_required_fields():
    for name, info in TASK_REGISTRY.items():
        assert "func" in info
        assert "description" in info
        assert "category" in info
        assert callable(info["func"])


def test_get_task_func_returns_callable():
    func = get_task_func("cleanup_expired_tokens")
    assert callable(func)


def test_get_task_func_unknown_returns_none():
    assert get_task_func("nonexistent_task") is None


# ---------- execute_pending_deletions ----------


@pytest.mark.asyncio
async def test_execute_pending_deletions_processes_due_requests(test_engine):
    """到期且 pending 的删除请求应被执行。"""
    session_factory = async_sessionmaker(
        test_engine, expire_on_commit=False
    )

    # 准备: 一个用户 + 一个到期删除请求
    async with session_factory() as session:
        user = UserORM(
            email="del@test.local",
            password_hash="x",
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

        req = PrivacyDeletionRequestORM(
            user_id=user_id,
            status="pending",
            scheduled_at=datetime.utcnow() - timedelta(hours=1),
        )
        session.add(req)
        await session.commit()

    # 执行任务
    result = await execute_pending_deletions(session_factory, batch_size=10)

    assert result["total_due"] == 1
    assert len(result["executed"]) == 1
    assert result["failed"] == []


@pytest.mark.asyncio
async def test_execute_pending_deletions_skips_future_scheduled(test_engine):
    """未到期的删除请求不应被执行。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async with session_factory() as session:
        user = UserORM(
            email="future@test.local",
            password_hash="x",
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

        # scheduled_at 在未来
        req = PrivacyDeletionRequestORM(
            user_id=user_id,
            status="pending",
            scheduled_at=datetime.utcnow() + timedelta(days=1),
        )
        session.add(req)
        await session.commit()

    result = await execute_pending_deletions(session_factory, batch_size=10)

    assert result["total_due"] == 0
    assert result["executed"] == []


@pytest.mark.asyncio
async def test_execute_pending_deletions_skips_completed(test_engine):
    """已完成的删除请求不应被再次执行。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async with session_factory() as session:
        user = UserORM(
            email="done@test.local",
            password_hash="x",
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

        req = PrivacyDeletionRequestORM(
            user_id=user_id,
            status="completed",
            scheduled_at=datetime.utcnow() - timedelta(hours=1),
        )
        session.add(req)
        await session.commit()

    result = await execute_pending_deletions(session_factory, batch_size=10)

    assert result["total_due"] == 0


@pytest.mark.asyncio
async def test_execute_pending_deletions_handles_empty(test_engine):
    """无到期请求时返回空统计。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    result = await execute_pending_deletions(session_factory)

    assert result["total_due"] == 0
    assert result["executed"] == []
    assert result["failed"] == []


# ---------- send_review_reminders ----------


@pytest.mark.asyncio
async def test_send_review_reminders_finds_due_reviews(test_engine):
    """到期复习计划应被扫描并通过 NotificationService 投递(WS 离线 -> failed)。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async with session_factory() as session:
        learner = LearnerORM(public_id="pub-review-1", name="Review Student")
        session.add(learner)
        await session.flush()
        user = UserORM(
            email="review@test.local",
            password_hash="x",
            role=UserRole.STUDENT,
            learner_id=learner.id,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        # next_review 已过期
        review = ReviewScheduleORM(
            learner_id=learner.id,
            knowledge_id="kp_test_1",
            repetition=0,
            interval_days=1,
            next_review=datetime.utcnow() - timedelta(hours=2),
        )
        session.add(review)
        await session.commit()

    result = await send_review_reminders(session_factory, batch_size=10)

    assert result["reminders_count"] == 1
    # WS 在测试环境无连接 -> 投递失败 -> failed_count
    assert result["delivered_count"] == 0
    assert result["failed_count"] == 1
    reminder = result["reminders"][0]
    assert reminder["knowledge_id"] == "kp_test_1"
    assert reminder["status"] == "failed"
    assert reminder["notification_id"] > 0


@pytest.mark.asyncio
async def test_send_review_reminders_skips_inactive_users(test_engine):
    """未激活用户的复习计划应被跳过。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async with session_factory() as session:
        learner = LearnerORM(public_id="pub-inactive", name="Inactive")
        session.add(learner)
        await session.flush()
        user = UserORM(
            email="inactive@test.local",
            password_hash="x",
            role=UserRole.STUDENT,
            learner_id=learner.id,
            is_active=False,  # 未激活
        )
        session.add(user)
        await session.flush()
        review = ReviewScheduleORM(
            learner_id=learner.id,
            knowledge_id="kp_test_2",
            repetition=0,
            interval_days=1,
            next_review=datetime.utcnow() - timedelta(hours=1),
        )
        session.add(review)
        await session.commit()

    result = await send_review_reminders(session_factory)

    assert result["reminders_count"] == 0


@pytest.mark.asyncio
async def test_send_review_reminders_skips_future_reviews(test_engine):
    """未到期的复习计划不应被扫描。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async with session_factory() as session:
        learner = LearnerORM(public_id="pub-future", name="Future")
        session.add(learner)
        await session.flush()
        user = UserORM(
            email="future-r@test.local",
            password_hash="x",
            role=UserRole.STUDENT,
            learner_id=learner.id,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        review = ReviewScheduleORM(
            learner_id=learner.id,
            knowledge_id="kp_test_3",
            repetition=0,
            interval_days=1,
            next_review=datetime.utcnow() + timedelta(days=1),  # 未来
        )
        session.add(review)
        await session.commit()

    result = await send_review_reminders(session_factory)

    assert result["reminders_count"] == 0


# ---------- cleanup_expired_tokens ----------


@pytest.mark.asyncio
async def test_cleanup_expired_tokens_deletes_old_revoked(test_engine):
    """过期且已撤销的 token 应被删除。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    old_cutoff = datetime.utcnow() - timedelta(days=40)
    async with session_factory() as session:
        # 应被删除: 过期 40 天 + 已撤销
        old_token = RefreshTokenORM(
            user_id=1,
            token_hash="old_hash_1",
            expires_at=old_cutoff,
            revoked=True,
        )
        # 不应被删除: 过期但未撤销
        unrevoked = RefreshTokenORM(
            user_id=1,
            token_hash="unrevoked_hash",
            expires_at=old_cutoff,
            revoked=False,
        )
        # 不应被删除: 近期撤销
        recent = RefreshTokenORM(
            user_id=1,
            token_hash="recent_hash",
            expires_at=datetime.utcnow() - timedelta(days=1),
            revoked=True,
        )
        session.add_all([old_token, unrevoked, recent])
        await session.commit()

    result = await cleanup_expired_tokens(session_factory, days_old=30)

    assert result["deleted_tokens"] == 1
    # 验证未删除的还在
    async with session_factory() as session:
        remaining = (
            await session.execute(select(RefreshTokenORM))
        ).scalars().all()
        remaining_hashes = {t.token_hash for t in remaining}
        assert "old_hash_1" not in remaining_hashes
        assert "unrevoked_hash" in remaining_hashes
        assert "recent_hash" in remaining_hashes


@pytest.mark.asyncio
async def test_cleanup_expired_tokens_handles_empty(test_engine):
    """无 token 时返回 0。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    result = await cleanup_expired_tokens(session_factory)

    assert result["deleted_tokens"] == 0


# ---------- generate_daily_stats ----------


@pytest.mark.asyncio
async def test_generate_daily_stats_returns_correct_fields(test_engine):
    """统计结果包含所有必需字段。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    result = await generate_daily_stats(session_factory)

    assert "date" in result
    assert "active_learners" in result
    assert "total_submissions" in result
    assert "accuracy" in result
    assert "total_audit_logs" in result
    assert "generated_at" in result
    assert result["active_learners"] == 0
    assert result["total_submissions"] == 0
    assert result["total_audit_logs"] == 0


@pytest.mark.asyncio
async def test_generate_daily_stats_counts_submissions(test_engine):
    """统计今日答题数和正确率。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    learner = LearnerORM(public_id="pub-stats", name="Stats")
    async with session_factory() as session:
        session.add(learner)
        await session.flush()
        learner_id = learner.id

        # 3 个今日 submission: 2 对 1 错
        now = datetime.utcnow()
        for is_correct in [True, True, False]:
            sub = SubmissionORM(
                learner_id=learner_id,
                knowledge_id="kp1",
                is_correct=is_correct,
                created_at=now,
            )
            session.add(sub)
        await session.commit()

    result = await generate_daily_stats(session_factory)

    assert result["total_submissions"] == 3
    assert result["active_learners"] == 1
    assert result["accuracy"] == round(2 / 3, 4)


@pytest.mark.asyncio
async def test_generate_daily_stats_counts_audit_logs(test_engine):
    """统计累计审计日志数。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async with session_factory() as session:
        for i in range(5):
            log = AuditLogORM(
                actor=f"user_{i}",
                action="test_action",
                target=f"test:{i}",
                ip="127.0.0.1",
                created_at=datetime.utcnow(),
            )
            session.add(log)
        await session.commit()

    result = await generate_daily_stats(session_factory)

    assert result["total_audit_logs"] == 5
