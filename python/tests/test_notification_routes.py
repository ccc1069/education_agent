"""通知 API 集成测试。

覆盖:
- 未登录 401
- 学生只能看自己的通知
- 标记已读后 unread_count 减少
- POST preferences 修改后 GET 返回新值
- 偏好校验(quiet_hours 0-23)
"""

from __future__ import annotations

from datetime import datetime

import pytest
from httpx import AsyncClient

from db.models import (
    LearnerORM,
    NotificationORM,
    UserORM,
    UserRole,
)


async def _seed_notification(
    test_engine, user_id: int, *, read: bool = False, type_: str = "system"
) -> int:
    """直接插入一条通知。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sf = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sf() as session:
        notif = NotificationORM(
            user_id=user_id,
            type=type_,
            channel="ws",
            status="delivered",
            priority=0,
            title="seed",
            body="b",
            payload={},
            read_at=datetime.utcnow() if read else None,
        )
        session.add(notif)
        await session.commit()
        return notif.id


@pytest.mark.asyncio
async def test_list_notifications_unauth_401(client: AsyncClient):
    """未登录返回 401。"""
    r = await client.get("/api/v1/notifications")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_notifications_returns_own_only(
    client: AsyncClient, auth_headers, admin_headers, test_engine
):
    """学生只能看到自己的通知。"""
    # 获取学生 user_id
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from db.models import UserORM

    sf = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sf() as session:
        result = await session.execute(
            select(UserORM).where(UserORM.email == "student@test.local")
        )
        student = result.scalar_one()
        student_id = student.id

    # 给学生插入 2 条,给管理员插入 1 条
    await _seed_notification(test_engine, student_id, type_="system")
    await _seed_notification(test_engine, student_id, type_="review_reminder")

    from sqlalchemy.ext.asyncio import async_sessionmaker

    sf = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sf() as session:
        result = await session.execute(
            select(UserORM).where(UserORM.email == "admin@test.local")
        )
        admin = result.scalar_one()
        await _seed_notification(test_engine, admin.id, type_="admin_only")

    r = await client.get("/api/v1/notifications", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 2
    assert all(item["type"] in ("system", "review_reminder") for item in data["items"])
    assert data["total_unread"] == 2


@pytest.mark.asyncio
async def test_unread_count(client: AsyncClient, auth_headers, test_engine):
    """unread-count 端点返回正确数。"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sf = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sf() as session:
        result = await session.execute(
            select(UserORM).where(UserORM.email == "student@test.local")
        )
        student = result.scalar_one()

    await _seed_notification(test_engine, student.id, read=False)
    await _seed_notification(test_engine, student.id, read=False)
    await _seed_notification(test_engine, student.id, read=True)

    r = await client.get(
        "/api/v1/notifications/unread-count", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["unread"] == 2


@pytest.mark.asyncio
async def test_mark_read_reduces_unread(
    client: AsyncClient, auth_headers, test_engine
):
    """标记已读后 unread_count 减少。"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sf = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sf() as session:
        result = await session.execute(
            select(UserORM).where(UserORM.email == "student@test.local")
        )
        student = result.scalar_one()

    notif_id = await _seed_notification(test_engine, student.id, read=False)

    # 标记前
    r = await client.get(
        "/api/v1/notifications/unread-count", headers=auth_headers
    )
    assert r.json()["unread"] == 1

    # 标记已读
    r = await client.post(
        f"/api/v1/notifications/{notif_id}/read", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # 标记后
    r = await client.get(
        "/api/v1/notifications/unread-count", headers=auth_headers
    )
    assert r.json()["unread"] == 0


@pytest.mark.asyncio
async def test_mark_read_not_found(client: AsyncClient, auth_headers):
    """不存在的通知 ID 返回 404。"""
    r = await client.post(
        "/api/v1/notifications/99999/read", headers=auth_headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_read(client: AsyncClient, auth_headers, test_engine):
    """批量标记已读。"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sf = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sf() as session:
        result = await session.execute(
            select(UserORM).where(UserORM.email == "student@test.local")
        )
        student = result.scalar_one()

    await _seed_notification(test_engine, student.id)
    await _seed_notification(test_engine, student.id)
    await _seed_notification(test_engine, student.id)

    r = await client.post(
        "/api/v1/notifications/read-all", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["marked"] == 3

    r = await client.get(
        "/api/v1/notifications/unread-count", headers=auth_headers
    )
    assert r.json()["unread"] == 0


@pytest.mark.asyncio
async def test_get_preferences_default(client: AsyncClient, auth_headers):
    """首次获取偏好返回默认值(ws_enabled=True, email/push=False)。"""
    r = await client.get(
        "/api/v1/notifications/preferences", headers=auth_headers
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ws_enabled"] is True
    assert data["email_enabled"] is False
    assert data["push_enabled"] is False
    assert data["min_priority"] == 0


@pytest.mark.asyncio
async def test_update_preferences_persists(
    client: AsyncClient, auth_headers
):
    """POST preferences 后 GET 返回新值。"""
    r = await client.post(
        "/api/v1/notifications/preferences",
        headers=auth_headers,
        json={
            "ws_enabled": False,
            "email_enabled": True,
            "push_enabled": False,
            "quiet_hours_start": 22,
            "quiet_hours_end": 7,
            "min_priority": 1,
        },
    )
    assert r.status_code == 200
    assert r.json()["email_enabled"] is True
    assert r.json()["ws_enabled"] is False
    assert r.json()["quiet_hours_start"] == 22
    assert r.json()["min_priority"] == 1

    # 再次 GET 验证持久化
    r = await client.get(
        "/api/v1/notifications/preferences", headers=auth_headers
    )
    assert r.json()["email_enabled"] is True
    assert r.json()["ws_enabled"] is False
    assert r.json()["quiet_hours_start"] == 22


@pytest.mark.asyncio
async def test_update_preferences_validates_quiet_hours(
    client: AsyncClient, auth_headers
):
    """quiet_hours 超出 0-23 应 422。"""
    r = await client.post(
        "/api/v1/notifications/preferences",
        headers=auth_headers,
        json={
            "ws_enabled": True,
            "email_enabled": False,
            "push_enabled": False,
            "quiet_hours_start": 25,  # 超出
            "quiet_hours_end": 7,
            "min_priority": 0,
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_unread_only_filter(
    client: AsyncClient, auth_headers, test_engine
):
    """unread_only=true 只返回未读。"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sf = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sf() as session:
        result = await session.execute(
            select(UserORM).where(UserORM.email == "student@test.local")
        )
        student = result.scalar_one()

    await _seed_notification(test_engine, student.id, read=False)
    await _seed_notification(test_engine, student.id, read=True)

    r = await client.get(
        "/api/v1/notifications?unread_only=true", headers=auth_headers
    )
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1
