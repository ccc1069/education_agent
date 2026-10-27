"""审计 + 隐私 仓储: P2#15 数据合规与隐私。"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AuditLogORM,
    DataExportJobORM,
    PrivacyConsentORM,
    PrivacyDeletionRequestORM,
)
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class AuditRepository(BaseRepository[AuditLogORM]):
    """审计日志仓储: 追加写 + HMAC 链。"""

    model = AuditLogORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_last_hash(self) -> str:
        """获取最后一条审计日志的 curr_hash(链尾)。"""
        result = await self.session.execute(
            select(AuditLogORM.curr_hash)
            .where(AuditLogORM.curr_hash != "")
            .order_by(AuditLogORM.id.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row or ""

    async def list_recent(
        self,
        limit: int = 100,
        offset: int = 0,
        actor: str | None = None,
        action: str | None = None,
    ) -> list[AuditLogORM]:
        """按时间倒序查询审计日志。"""
        stmt = select(AuditLogORM).order_by(
            AuditLogORM.id.desc()
        ).limit(limit).offset(offset)
        if actor:
            stmt = stmt.where(AuditLogORM.actor == actor)
        if action:
            stmt = stmt.where(AuditLogORM.action == action)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, log_id: int) -> AuditLogORM | None:
        result = await self.session.execute(
            select(AuditLogORM).where(AuditLogORM.id == log_id)
        )
        return result.scalar_one_or_none()

    async def get_chain_from(self, log_id: int) -> list[AuditLogORM]:
        """从指定 ID 开始向后的所有日志(含自身),用于链验证。"""
        result = await self.session.execute(
            select(AuditLogORM)
            .where(AuditLogORM.id >= log_id)
            .order_by(AuditLogORM.id.asc())
        )
        return list(result.scalars().all())


class PrivacyConsentRepository(BaseRepository[PrivacyConsentORM]):
    """隐私同意记录仓储(追加写,不修改)。"""

    model = PrivacyConsentORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_latest(self, user_id: int, consent_type: str) -> PrivacyConsentORM | None:
        """获取用户某类型同意的最新状态。"""
        result = await self.session.execute(
            select(PrivacyConsentORM)
            .where(
                PrivacyConsentORM.user_id == user_id,
                PrivacyConsentORM.consent_type == consent_type,
            )
            .order_by(PrivacyConsentORM.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_user_consents(self, user_id: int) -> list[PrivacyConsentORM]:
        """获取用户所有同意类型(每种取最新)。"""
        result = await self.session.execute(
            select(PrivacyConsentORM)
            .where(PrivacyConsentORM.user_id == user_id)
            .order_by(PrivacyConsentORM.id.desc())
        )
        all_rows = list(result.scalars().all())
        # 按 consent_type 去重,保留最新
        seen: set[str] = set()
        latest: list[PrivacyConsentORM] = []
        for r in all_rows:
            if r.consent_type in seen:
                continue
            seen.add(r.consent_type)
            latest.append(r)
        return latest


class PrivacyDeletionRepository(BaseRepository[PrivacyDeletionRequestORM]):
    """账户删除请求仓储。"""

    model = PrivacyDeletionRequestORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_active_by_user(self, user_id: int) -> PrivacyDeletionRequestORM | None:
        """获取用户未完成的删除请求(pending/scheduled/executing)。"""
        result = await self.session.execute(
            select(PrivacyDeletionRequestORM)
            .where(
                PrivacyDeletionRequestORM.user_id == user_id,
                PrivacyDeletionRequestORM.status.in_(
                    ["pending", "scheduled", "executing"]
                ),
            )
            .order_by(PrivacyDeletionRequestORM.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_due(self, now: Any) -> list[PrivacyDeletionRequestORM]:
        """列出已到 scheduled_at 但仍未执行的请求(供定时任务扫描)。"""
        result = await self.session.execute(
            select(PrivacyDeletionRequestORM).where(
                PrivacyDeletionRequestORM.status == "pending",
                PrivacyDeletionRequestORM.scheduled_at.is_not(None),
                PrivacyDeletionRequestORM.scheduled_at <= now,
            )
        )
        return list(result.scalars().all())


class DataExportJobRepository(BaseRepository[DataExportJobORM]):
    """数据导出任务仓储。"""

    model = DataExportJobORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_user(
        self, user_id: int, limit: int = 20
    ) -> list[DataExportJobORM]:
        result = await self.session.execute(
            select(DataExportJobORM)
            .where(DataExportJobORM.user_id == user_id)
            .order_by(DataExportJobORM.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id(self, job_id: int) -> DataExportJobORM | None:
        result = await self.session.execute(
            select(DataExportJobORM).where(DataExportJobORM.id == job_id)
        )
        return result.scalar_one_or_none()
