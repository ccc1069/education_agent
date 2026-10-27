"""通知 Repository: NotificationORM + NotificationPreferenceORM。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update

from db.models import NotificationORM, NotificationPreferenceORM
from repositories.base import BaseRepository


class NotificationRepository(BaseRepository[NotificationORM]):
    """通知记录仓储。"""

    model = NotificationORM

    async def list_by_user(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
    ) -> list[NotificationORM]:
        stmt = select(NotificationORM).where(NotificationORM.user_id == user_id)
        if unread_only:
            stmt = stmt.where(NotificationORM.read_at.is_(None))
        stmt = stmt.order_by(NotificationORM.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_unread(self, user_id: int) -> int:
        stmt = (
            select(func.count(NotificationORM.id))
            .where(
                NotificationORM.user_id == user_id,
                NotificationORM.read_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def mark_read(self, notification_id: int, user_id: int) -> bool:
        """标记单条已读。返回是否影响行(权限/存在性)。"""
        stmt = (
            update(NotificationORM)
            .where(
                NotificationORM.id == notification_id,
                NotificationORM.user_id == user_id,
                NotificationORM.read_at.is_(None),
            )
            .values(read_at=datetime.utcnow())
        )
        result = await self.session.execute(stmt)
        return (result.rowcount or 0) > 0

    async def mark_all_read(self, user_id: int) -> int:
        """标记该用户全部未读为已读。返回影响行数。"""
        stmt = (
            update(NotificationORM)
            .where(
                NotificationORM.user_id == user_id,
                NotificationORM.read_at.is_(None),
            )
            .values(read_at=datetime.utcnow())
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0

    async def count_recent_same_type(
        self, user_id: int, type_: str, since: datetime
    ) -> int:
        """频控用: 统计该用户某类型自 since 以来的通知数。"""
        stmt = (
            select(func.count(NotificationORM.id))
            .where(
                NotificationORM.user_id == user_id,
                NotificationORM.type == type_,
                NotificationORM.created_at >= since,
            )
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def update_status(
        self,
        notification_id: int,
        status: str,
        error_message: str | None = None,
        sent_at: datetime | None = None,
        delivered_at: datetime | None = None,
    ) -> None:
        """更新通知状态(投递回执)。"""
        values: dict = {"status": status}
        if error_message is not None:
            values["error_message"] = error_message
        if sent_at is not None:
            values["sent_at"] = sent_at
        if delivered_at is not None:
            values["delivered_at"] = delivered_at
        stmt = (
            update(NotificationORM)
            .where(NotificationORM.id == notification_id)
            .values(**values)
        )
        await self.session.execute(stmt)


class NotificationPreferenceRepository(BaseRepository[NotificationPreferenceORM]):
    """通知偏好仓储。"""

    model = NotificationPreferenceORM

    async def get_by_user(
        self, user_id: int
    ) -> NotificationPreferenceORM | None:
        stmt = select(NotificationPreferenceORM).where(
            NotificationPreferenceORM.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self, user_id: int
    ) -> NotificationPreferenceORM:
        """获取或创建偏好(默认值)。"""
        pref = await self.get_by_user(user_id)
        if pref is not None:
            return pref
        pref = NotificationPreferenceORM(user_id=user_id)
        self.session.add(pref)
        await self.session.flush()
        return pref

    async def update(
        self, user_id: int, **fields
    ) -> NotificationPreferenceORM | None:
        """更新偏好字段,返回更新后的对象。"""
        if not fields:
            return await self.get_by_user(user_id)
        # 白名单字段
        allowed = {
            "ws_enabled",
            "email_enabled",
            "push_enabled",
            "quiet_hours_start",
            "quiet_hours_end",
            "min_priority",
        }
        clean = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if clean:
            stmt = (
                update(NotificationPreferenceORM)
                .where(NotificationPreferenceORM.user_id == user_id)
                .values(**clean)
                .execution_options(synchronize_session="fetch")
            )
            await self.session.execute(stmt)
            await self.session.flush()
        return await self.get_by_user(user_id)
