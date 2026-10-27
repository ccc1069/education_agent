"""通知 API: 列表 / 未读数 / 标记已读 / 偏好管理。

权限:
- 所有路由需已认证用户
- 用户只能操作自己的通知(user_id 隔离)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, get_current_active_user
from db.session import get_session_dep
from services import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ---------- Pydantic 模型 ----------


class NotificationItem(BaseModel):
    id: int
    type: str
    channel: str
    status: str
    priority: int
    title: str
    body: str
    payload: dict[str, Any] = {}
    created_at: str | None = None
    read_at: str | None = None


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    total_unread: int
    limit: int
    offset: int


class UnreadCountResponse(BaseModel):
    unread: int


class MarkReadResponse(BaseModel):
    ok: bool
    id: int


class MarkAllReadResponse(BaseModel):
    ok: bool
    marked: int


class NotificationPreferences(BaseModel):
    ws_enabled: bool = True
    email_enabled: bool = False
    push_enabled: bool = False
    quiet_hours_start: int | None = Field(default=None, ge=0, le=23)
    quiet_hours_end: int | None = Field(default=None, ge=0, le=23)
    min_priority: int = Field(default=0, ge=0, le=2)


# ---------- 路由 ----------


def _to_item(n: Any) -> NotificationItem:
    return NotificationItem(
        id=n.id,
        type=n.type,
        channel=n.channel,
        status=n.status,
        priority=n.priority,
        title=n.title,
        body=n.body,
        payload=n.payload or {},
        created_at=n.created_at.isoformat() if n.created_at else None,
        read_at=n.read_at.isoformat() if n.read_at else None,
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    unread_only: bool = Query(default=False),
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
) -> NotificationListResponse:
    """列出我的通知。"""
    service = NotificationService(session)
    items = await service.list_notifications(
        user_id=current.id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )
    unread = await service.count_unread(current.id)
    return NotificationListResponse(
        items=[_to_item(n) for n in items],
        total_unread=unread,
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
) -> UnreadCountResponse:
    service = NotificationService(session)
    return UnreadCountResponse(unread=await service.count_unread(current.id))


@router.post("/read-all", response_model=MarkAllReadResponse)
async def mark_all_read(
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
) -> MarkAllReadResponse:
    service = NotificationService(session)
    marked = await service.mark_all_read(current.id)
    return MarkAllReadResponse(ok=True, marked=marked)


@router.post("/{notification_id}/read", response_model=MarkReadResponse)
async def mark_read(
    notification_id: int,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
) -> MarkReadResponse:
    service = NotificationService(session)
    ok = await service.mark_read(notification_id, current.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found or already read",
        )
    return MarkReadResponse(ok=True, id=notification_id)


@router.get("/preferences", response_model=NotificationPreferences)
async def get_preferences(
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
) -> NotificationPreferences:
    service = NotificationService(session)
    pref = await service.get_preferences(current.id)
    return NotificationPreferences(
        ws_enabled=pref.ws_enabled,
        email_enabled=pref.email_enabled,
        push_enabled=pref.push_enabled,
        quiet_hours_start=pref.quiet_hours_start,
        quiet_hours_end=pref.quiet_hours_end,
        min_priority=pref.min_priority,
    )


@router.post("/preferences", response_model=NotificationPreferences)
async def update_preferences(
    body: NotificationPreferences,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
) -> NotificationPreferences:
    service = NotificationService(session)
    updated = await service.update_preferences(
        current.id,
        ws_enabled=body.ws_enabled,
        email_enabled=body.email_enabled,
        push_enabled=body.push_enabled,
        quiet_hours_start=body.quiet_hours_start,
        quiet_hours_end=body.quiet_hours_end,
        min_priority=body.min_priority,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Preferences not found"
        )
    return NotificationPreferences(
        ws_enabled=updated.ws_enabled,
        email_enabled=updated.email_enabled,
        push_enabled=updated.push_enabled,
        quiet_hours_start=updated.quiet_hours_start,
        quiet_hours_end=updated.quiet_hours_end,
        min_priority=updated.min_priority,
    )
