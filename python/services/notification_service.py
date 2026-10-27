"""NotificationService: 统一通知服务。

特性:
- 多渠道投递: ws(实时 WebSocket 推送) / email / push
- 用户偏好: 各渠道开关 + 勿扰时段(北京时间 0-23) + min_priority 门槛
- 频控: 同 user + type 1 小时内不超过 5 条(防止刷屏)
- 投递回执: pending -> sent -> delivered -> read / failed
- 失败降级: WS 离线时降级到 email(若偏好允许)

设计:
- send() 同步投递 WS(在线即 delivered);email/push 当前为占位
- 频控被拒/偏好不达标: 仍持久化记录(status=failed),便于审计
- 偏好表 get_or_create(首次访问写入默认值)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import LearnerORM, NotificationORM, NotificationPreferenceORM, UserORM
from repositories import (
    NotificationPreferenceRepository,
    NotificationRepository,
)

logger = logging.getLogger(__name__)

# 同 user + type 在 1 小时内最多 5 条(防刷屏)
FREQ_LIMIT = 5
FREQ_WINDOW_SECONDS = 3600

CHANNELS = ("ws", "email", "push")


class NotificationService:
    """统一通知服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.notification_repo = NotificationRepository(session)
        self.preference_repo = NotificationPreferenceRepository(session)

    # ---------- 投递 ----------

    async def send(
        self,
        user_id: int,
        type_: str,
        title: str,
        body: str,
        payload: dict[str, Any] | None = None,
        priority: int = 0,
        preferred_channel: str = "ws",
    ) -> NotificationORM:
        """投递一条通知。

        流程:
        1. 获取偏好(自动创建)
        2. 检查 min_priority: 低于阈值 -> status=failed(reason)
        3. 检查勿扰时段: 落入且 priority<2 -> failed
        4. 检查频控: 1 小时内同类型超 5 条 -> failed
        5. 选择渠道: preferred -> 偏好降级
        6. 持久化(pending) -> 投递 -> 更新状态
        """
        pref = await self.preference_repo.get_or_create(user_id)

        # 1. min_priority 检查
        if priority < pref.min_priority:
            return await self._persist_failed(
                user_id=user_id,
                type_=type_,
                channel=preferred_channel,
                title=title,
                body=body,
                payload=payload or {},
                priority=priority,
                reason=f"priority {priority} < min_priority {pref.min_priority}",
            )

        # 2. 勿扰时段检查(仅高优先级穿透)
        if _in_quiet_hours(pref.quiet_hours_start, pref.quiet_hours_end) and priority < 2:
            return await self._persist_failed(
                user_id=user_id,
                type_=type_,
                channel=preferred_channel,
                title=title,
                body=body,
                payload=payload or {},
                priority=priority,
                reason="quiet_hours",
            )

        # 3. 频控(同 user+type 1 小时内 5 条)
        since = datetime.utcnow() - timedelta(seconds=FREQ_WINDOW_SECONDS)
        recent = await self.notification_repo.count_recent_same_type(
            user_id=user_id, type_=type_, since=since
        )
        if recent >= FREQ_LIMIT:
            return await self._persist_failed(
                user_id=user_id,
                type_=type_,
                channel=preferred_channel,
                title=title,
                body=body,
                payload=payload or {},
                priority=priority,
                reason=f"freq_limit {recent}/{FREQ_LIMIT}",
            )

        # 4. 渠道选择
        channel = _choose_channel(preferred_channel, pref)

        # 5. 持久化(pending)
        notif = NotificationORM(
            user_id=user_id,
            type=type_,
            channel=channel,
            status="pending",
            priority=priority,
            title=title,
            body=body,
            payload=payload or {},
        )
        self.session.add(notif)
        await self.session.flush()

        # 6. 投递
        await self._dispatch(notif, pref)
        await self.session.commit()
        return notif

    async def _dispatch(
        self, notif: NotificationORM, pref: NotificationPreferenceORM
    ) -> None:
        """根据 channel 派发通知,更新 status。"""
        now = datetime.utcnow()
        try:
            if notif.channel == "ws":
                delivered = await self._send_ws(notif)
            elif notif.channel == "email":
                delivered = await self._send_email(notif)
            elif notif.channel == "push":
                delivered = await self._send_push(notif)
            else:
                notif.status = "failed"
                notif.error_message = f"unknown channel {notif.channel}"
                return

            if delivered:
                notif.status = "delivered"
                notif.sent_at = now
                notif.delivered_at = now
            else:
                # 投递失败,尝试降级到 email
                if notif.channel != "email" and pref.email_enabled:
                    notif.channel = "email"
                    fallback_ok = await self._send_email(notif)
                    if fallback_ok:
                        notif.status = "sent"
                        notif.sent_at = now
                        return
                notif.status = "failed"
                notif.error_message = notif.error_message or "delivery_failed"
        except Exception as e:
            logger.exception("notification_dispatch_failed: id=%s", notif.id)
            notif.status = "failed"
            notif.error_message = f"exception: {e!s}"

    async def _send_ws(self, notif: NotificationORM) -> bool:
        """通过 WebSocket 实时推送。返回是否在线投递成功。"""
        from api.websocket import manager  # 延迟导入避免循环

        learner_public_id = await self._get_learner_public_id(notif.user_id)
        if learner_public_id is None:
            notif.error_message = "no learner profile"
            return False

        msg = {
            "type": "notification",
            "id": notif.id,
            "notification_type": notif.type,
            "title": notif.title,
            "body": notif.body,
            "priority": notif.priority,
            "payload": notif.payload,
            "created_at": notif.created_at.isoformat() if notif.created_at else None,
        }
        return await manager.send_to_learner(learner_public_id, msg)

    async def _send_email(self, notif: NotificationORM) -> bool:
        """占位: 真实实现需要 SMTP 客户端。"""
        logger.info(
            "email_notification_placeholder: id=%s user=%s title=%s",
            notif.id,
            notif.user_id,
            notif.title,
        )
        return True  # 占位视为成功

    async def _send_push(self, notif: NotificationORM) -> bool:
        """占位: 真实实现需要 FCM/APNs client。"""
        logger.info(
            "push_notification_placeholder: id=%s user=%s title=%s",
            notif.id,
            notif.user_id,
            notif.title,
        )
        return True

    async def _get_learner_public_id(self, user_id: int) -> str | None:
        """从 user_id 查 learner.public_id。"""
        result = await self.session.execute(
            select(LearnerORM.public_id)
            .join(UserORM, UserORM.learner_id == LearnerORM.id)
            .where(UserORM.id == user_id)
        )
        return result.scalar_one_or_none()

    async def _persist_failed(
        self,
        user_id: int,
        type_: str,
        channel: str,
        title: str,
        body: str,
        payload: dict[str, Any],
        priority: int,
        reason: str,
    ) -> NotificationORM:
        notif = NotificationORM(
            user_id=user_id,
            type=type_,
            channel=channel,
            status="failed",
            priority=priority,
            title=title,
            body=body,
            payload=payload,
            error_message=reason,
        )
        self.session.add(notif)
        await self.session.flush()
        await self.session.commit()
        return notif

    # ---------- 查询 ----------

    async def list_notifications(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
    ) -> list[NotificationORM]:
        return await self.notification_repo.list_by_user(
            user_id=user_id,
            limit=limit,
            offset=offset,
            unread_only=unread_only,
        )

    async def count_unread(self, user_id: int) -> int:
        return await self.notification_repo.count_unread(user_id)

    async def mark_read(self, notification_id: int, user_id: int) -> bool:
        ok = await self.notification_repo.mark_read(notification_id, user_id)
        if ok:
            await self.session.commit()
        return ok

    async def mark_all_read(self, user_id: int) -> int:
        marked = await self.notification_repo.mark_all_read(user_id)
        await self.session.commit()
        return marked

    # ---------- 偏好 ----------

    async def get_preferences(self, user_id: int) -> NotificationPreferenceORM:
        return await self.preference_repo.get_or_create(user_id)

    async def update_preferences(
        self, user_id: int, **fields: Any
    ) -> NotificationPreferenceORM | None:
        """更新偏好(若不存在则先创建)。"""
        await self.preference_repo.get_or_create(user_id)
        updated = await self.preference_repo.update(user_id, **fields)
        await self.session.commit()
        return updated


def _in_quiet_hours(start: int | None, end: int | None) -> bool:
    """当前北京时间小时是否在 [start, end) 内。"""
    if start is None or end is None:
        return False
    from zoneinfo import ZoneInfo

    now_hour = datetime.now(ZoneInfo("Asia/Shanghai")).hour
    if start == end:
        return False
    if start < end:
        return start <= now_hour < end
    # 跨午夜(如 22 -> 7)
    return now_hour >= start or now_hour < end


def _choose_channel(
    preferred: str, pref: NotificationPreferenceORM
) -> str:
    """根据偏好选择最终渠道: preferred -> 降级。"""
    if preferred == "ws" and pref.ws_enabled:
        return "ws"
    if preferred == "email" and pref.email_enabled:
        return "email"
    if preferred == "push" and pref.push_enabled:
        return "push"
    # preferred 被禁用,降级到任意启用的渠道
    if pref.ws_enabled:
        return "ws"
    if pref.email_enabled:
        return "email"
    if pref.push_enabled:
        return "push"
    return preferred  # 全部禁用,保留 preferred(将 failed)
