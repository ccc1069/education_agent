"""NotificationService 单元测试。

覆盖:
- send: 正常路径(WS 在线 -> delivered)
- send: WS 离线 + email 禁用 -> failed
- send: WS 离线 + email 启用 -> fallback sent
- send: 偏好 min_priority 不达标 -> failed
- send: 勿扰时段 + 低优先级 -> failed
- send: 勿扰时段 + 高优先级 -> 透传
- send: 频控(6 次同类型 -> 第 6 次被拒)
- mark_read: 仅本人可读
- get_or_create: 首次创建,二次返回已有
- list_notifications / count_unread
- update_preferences: 白名单生效
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from db.models import (
    LearnerORM,
    NotificationORM,
    NotificationPreferenceORM,
    UserORM,
    UserRole,
)
from services.notification_service import (
    NotificationService,
    _choose_channel,
    _in_quiet_hours,
)


# ---------- helpers ----------


async def _make_user(session, email: str = "notify@test.local") -> tuple[int, str]:
    """创建学生 + learner,返回 (user_id, public_id)。"""
    learner = LearnerORM(public_id=f"pub-{email}", name="N")
    session.add(learner)
    await session.flush()
    user = UserORM(
        email=email,
        password_hash="x",
        role=UserRole.STUDENT,
        learner_id=learner.id,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    return user.id, learner.public_id


async def _set_prefs(
    session_factory, user_id: int, **fields
) -> NotificationPreferenceORM:
    """直接设置偏好(绕过 service.update)。"""
    async with session_factory() as session:
        pref = NotificationPreferenceORM(user_id=user_id, **fields)
        session.add(pref)
        await session.commit()
        return pref


# ---------- _in_quiet_hours 单元 ----------


def test_in_quiet_hours_none_returns_false():
    assert _in_quiet_hours(None, None) is False


def test_in_quiet_hours_same_start_end_returns_false():
    assert _in_quiet_hours(5, 5) is False


def test_in_quiet_hours_normal_window():
    # mock 北京时间当前小时
    with patch("services.notification_service.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 10, 0)
        assert _in_quiet_hours(8, 12) is True
        assert _in_quiet_hours(12, 18) is False


def test_in_quiet_hours_cross_midnight():
    with patch("services.notification_service.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 23, 0)
        # 22-7 跨午夜
        assert _in_quiet_hours(22, 7) is True
        mock_dt.now.return_value = datetime(2026, 1, 1, 6, 0)
        assert _in_quiet_hours(22, 7) is True
        mock_dt.now.return_value = datetime(2026, 1, 1, 8, 0)
        assert _in_quiet_hours(22, 7) is False


# ---------- _choose_channel 单元 ----------


def test_choose_channel_preferred_enabled():
    pref = NotificationPreferenceORM(
        user_id=1, ws_enabled=True, email_enabled=True, push_enabled=False
    )
    assert _choose_channel("ws", pref) == "ws"
    assert _choose_channel("email", pref) == "email"
    assert _choose_channel("push", pref) == "ws"  # push 禁用 -> 降级 ws


def test_choose_channel_all_disabled_returns_preferred():
    pref = NotificationPreferenceORM(
        user_id=1, ws_enabled=False, email_enabled=False, push_enabled=False
    )
    assert _choose_channel("ws", pref) == "ws"  # 全禁用,保留 preferred


# ---------- send() ----------


@pytest.mark.asyncio
async def test_send_ws_online_delivered(test_engine):
    """WS 在线 -> delivered。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id, public_id = await _make_user(session, "online@test.local")

    # mock manager.send_to_learner 返回 True(在线)
    with patch(
        "api.websocket.manager.send_to_learner", new=AsyncMock(return_value=True)
    ):
        async with session_factory() as session:
            svc = NotificationService(session)
            notif = await svc.send(
                user_id=user_id,
                type_="review_reminder",
                title="t",
                body="b",
                payload={"k": "v"},
                priority=1,
                preferred_channel="ws",
            )
            await session.commit()

    assert notif.status == "delivered"
    assert notif.channel == "ws"
    assert notif.sent_at is not None
    assert notif.delivered_at is not None


@pytest.mark.asyncio
async def test_send_ws_offline_no_email_failed(test_engine):
    """WS 离线 + email 禁用 -> failed(无降级)。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id, _ = await _make_user(session, "offline@test.local")

    with patch(
        "api.websocket.manager.send_to_learner", new=AsyncMock(return_value=False)
    ):
        async with session_factory() as session:
            svc = NotificationService(session)
            notif = await svc.send(
                user_id=user_id,
                type_="system",
                title="t",
                body="b",
                priority=0,
                preferred_channel="ws",
            )
            await session.commit()

    assert notif.status == "failed"
    assert notif.error_message is not None


@pytest.mark.asyncio
async def test_send_ws_offline_email_enabled_fallback(test_engine):
    """WS 离线 + email 启用 -> fallback 到 email(sent)。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id, _ = await _make_user(session, "fallback@test.local")
    await _set_prefs(session_factory, user_id, ws_enabled=True, email_enabled=True)

    with patch(
        "api.websocket.manager.send_to_learner", new=AsyncMock(return_value=False)
    ):
        async with session_factory() as session:
            svc = NotificationService(session)
            notif = await svc.send(
                user_id=user_id,
                type_="system",
                title="t",
                body="b",
                priority=0,
                preferred_channel="ws",
            )
            await session.commit()

    assert notif.status == "sent"
    assert notif.channel == "email"


@pytest.mark.asyncio
async def test_send_min_priority_below_threshold_failed(test_engine):
    """priority < pref.min_priority -> failed。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id, _ = await _make_user(session, "minp@test.local")
    await _set_prefs(session_factory, user_id, min_priority=2)

    async with session_factory() as session:
        svc = NotificationService(session)
        notif = await svc.send(
            user_id=user_id,
            type_="system",
            title="t",
            body="b",
            priority=1,  # < min_priority=2
            preferred_channel="ws",
        )
        await session.commit()

    assert notif.status == "failed"
    assert "min_priority" in (notif.error_message or "")


@pytest.mark.asyncio
async def test_send_quiet_hours_low_priority_failed(test_engine):
    """勿扰时段 + 低优先级(<2) -> failed。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id, _ = await _make_user(session, "quiet@test.local")
    await _set_prefs(
        session_factory, user_id, quiet_hours_start=0, quiet_hours_end=24
    )

    async with session_factory() as session:
        svc = NotificationService(session)
        notif = await svc.send(
            user_id=user_id,
            type_="system",
            title="t",
            body="b",
            priority=1,  # < 2
            preferred_channel="ws",
        )
        await session.commit()

    assert notif.status == "failed"
    assert "quiet_hours" in (notif.error_message or "")


@pytest.mark.asyncio
async def test_send_quiet_hours_high_priority_passes(test_engine):
    """勿扰时段 + 高优先级(>=2) -> 透传。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id, _ = await _make_user(session, "qhhigh@test.local")
    await _set_prefs(
        session_factory, user_id, quiet_hours_start=0, quiet_hours_end=24
    )

    with patch(
        "api.websocket.manager.send_to_learner", new=AsyncMock(return_value=True)
    ):
        async with session_factory() as session:
            svc = NotificationService(session)
            notif = await svc.send(
                user_id=user_id,
                type_="system",
                title="t",
                body="b",
                priority=2,  # 高
                preferred_channel="ws",
            )
            await session.commit()

    assert notif.status == "delivered"


@pytest.mark.asyncio
async def test_send_frequency_control_blocks_6th(test_engine):
    """1 小时内同类型 5 条后第 6 条被频控拒绝。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id, _ = await _make_user(session, "freq@test.local")

    with patch(
        "api.websocket.manager.send_to_learner", new=AsyncMock(return_value=True)
    ):
        # 发 5 条(全部成功)
        async with session_factory() as session:
            svc = NotificationService(session)
            for i in range(5):
                await svc.send(
                    user_id=user_id,
                    type_="review_reminder",
                    title=f"t{i}",
                    body="b",
                    priority=0,
                    preferred_channel="ws",
                )
            await session.commit()

        # 第 6 条应被频控
        async with session_factory() as session:
            svc = NotificationService(session)
            notif = await svc.send(
                user_id=user_id,
                type_="review_reminder",
                title="t6",
                body="b",
                priority=0,
                preferred_channel="ws",
            )
            await session.commit()

    assert notif.status == "failed"
    assert "freq_limit" in (notif.error_message or "")


@pytest.mark.asyncio
async def test_send_frequency_control_different_types_independent(test_engine):
    """不同 type 的频控独立。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id, _ = await _make_user(session, "freq2@test.local")

    with patch(
        "api.websocket.manager.send_to_learner", new=AsyncMock(return_value=True)
    ):
        async with session_factory() as session:
            svc = NotificationService(session)
            # 5 条 type=A
            for i in range(5):
                await svc.send(
                    user_id=user_id,
                    type_="review_reminder",
                    title=f"tA{i}",
                    body="b",
                    priority=0,
                    preferred_channel="ws",
                )
            # 1 条 type=B 应通过
            notif_b = await svc.send(
                user_id=user_id,
                type_="system",
                title="tB",
                body="b",
                priority=0,
                preferred_channel="ws",
            )
            await session.commit()

    assert notif_b.status == "delivered"


# ---------- mark_read ----------


@pytest.mark.asyncio
async def test_mark_read_only_owner(test_engine):
    """用户只能标记自己的通知。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        u1, _ = await _make_user(session, "u1@test.local")
        u2, _ = await _make_user(session, "u2@test.local")

    async with session_factory() as session:
        notif = NotificationORM(
            user_id=u1, type="t", channel="ws", status="delivered",
            priority=0, title="t", body="b", payload={},
        )
        session.add(notif)
        await session.commit()
        notif_id = notif.id

    # u2 不能标记 u1 的通知
    async with session_factory() as session:
        svc = NotificationService(session)
        ok = await svc.mark_read(notif_id, u2)
        await session.commit()
    assert ok is False

    # u1 可以
    async with session_factory() as session:
        svc = NotificationService(session)
        ok = await svc.mark_read(notif_id, u1)
        await session.commit()
    assert ok is True


# ---------- get_or_create ----------


@pytest.mark.asyncio
async def test_preferences_get_or_create_idempotent(test_engine):
    """首次创建,二次返回已有。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id, _ = await _make_user(session, "pref@test.local")

    async with session_factory() as session:
        svc = NotificationService(session)
        p1 = await svc.get_preferences(user_id)
        await session.commit()

    async with session_factory() as session:
        svc = NotificationService(session)
        p2 = await svc.get_preferences(user_id)
        await session.commit()

    assert p1.id == p2.id
    assert p1.user_id == user_id


@pytest.mark.asyncio
async def test_update_preferences_whitelist(test_engine):
    """update_preferences 只接受白名单字段。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id, _ = await _make_user(session, "pref2@test.local")

    async with session_factory() as session:
        svc = NotificationService(session)
        # 正常字段
        updated = await svc.update_preferences(
            user_id,
            ws_enabled=False,
            email_enabled=True,
            min_priority=1,
            quiet_hours_start=22,
            quiet_hours_end=7,
        )
        await session.commit()

    assert updated is not None
    assert updated.ws_enabled is False
    assert updated.email_enabled is True
    assert updated.min_priority == 1
    assert updated.quiet_hours_start == 22
    assert updated.quiet_hours_end == 7


# ---------- list / count ----------


@pytest.mark.asyncio
async def test_list_and_count(test_engine):
    """list_notifications + count_unread。"""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id, _ = await _make_user(session, "list@test.local")

    async with session_factory() as session:
        # 3 条未读 + 1 条已读
        for i in range(3):
            session.add(
                NotificationORM(
                    user_id=user_id, type="t", channel="ws", status="delivered",
                    priority=0, title=f"t{i}", body="b", payload={},
                )
            )
        session.add(
            NotificationORM(
                user_id=user_id, type="t", channel="ws", status="delivered",
                priority=0, title="read", body="b", payload={},
                read_at=datetime.utcnow(),
            )
        )
        await session.commit()

    async with session_factory() as session:
        svc = NotificationService(session)
        unread = await svc.count_unread(user_id)
        all_items = await svc.list_notifications(user_id, limit=10)
        only_unread = await svc.list_notifications(
            user_id, limit=10, unread_only=True
        )
        await session.commit()

    assert unread == 3
    assert len(all_items) == 4
    assert len(only_unread) == 3


@pytest.mark.asyncio
async def test_mark_all_read(test_engine):
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id, _ = await _make_user(session, "mar@test.local")

    async with session_factory() as session:
        for i in range(3):
            session.add(
                NotificationORM(
                    user_id=user_id, type="t", channel="ws", status="delivered",
                    priority=0, title=f"t{i}", body="b", payload={},
                )
            )
        await session.commit()

    async with session_factory() as session:
        svc = NotificationService(session)
        marked = await svc.mark_all_read(user_id)
        await session.commit()

    assert marked == 3

    async with session_factory() as session:
        svc = NotificationService(session)
        unread = await svc.count_unread(user_id)
        await session.commit()
    assert unread == 0
