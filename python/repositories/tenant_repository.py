"""租户 Repository: TenantORM + TenantQuotaORM。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import TenantORM, TenantQuotaORM, UserORM
from repositories.base import BaseRepository


class TenantRepository(BaseRepository[TenantORM]):
    """租户仓储。"""

    model = TenantORM

    async def get_by_slug(self, slug: str) -> TenantORM | None:
        stmt = select(TenantORM).where(TenantORM.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self, limit: int = 100, offset: int = 0) -> list[TenantORM]:
        stmt = (
            select(TenantORM)
            .where(TenantORM.is_active.is_(True))
            .order_by(TenantORM.id.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_users(self, tenant_id: int) -> int:
        stmt = select(func.count(UserORM.id)).where(UserORM.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())


class TenantQuotaRepository(BaseRepository[TenantQuotaORM]):
    """租户配额仓储。"""

    model = TenantQuotaORM

    # 不同 plan 的默认配额
    PLAN_DEFAULTS: dict[str, dict[str, int]] = {
        "free": {"max_users": 50, "max_llm_tokens_per_month": 10_000},
        "pro": {"max_users": 500, "max_llm_tokens_per_month": 500_000},
        "enterprise": {"max_users": 100_000, "max_llm_tokens_per_month": 10_000_000},
    }

    async def get_by_tenant(
        self, tenant_id: int
    ) -> TenantQuotaORM | None:
        stmt = select(TenantQuotaORM).where(
            TenantQuotaORM.tenant_id == tenant_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self, tenant_id: int, plan: str = "free"
    ) -> TenantQuotaORM:
        """获取或创建配额(根据 plan 初始化默认值)。"""
        quota = await self.get_by_tenant(tenant_id)
        if quota is not None:
            return quota
        defaults = self.PLAN_DEFAULTS.get(plan, self.PLAN_DEFAULTS["free"])
        quota = TenantQuotaORM(
            tenant_id=tenant_id,
            max_users=defaults["max_users"],
            max_llm_tokens_per_month=defaults["max_llm_tokens_per_month"],
        )
        self.session.add(quota)
        await self.session.flush()
        return quota

    async def update(
        self, tenant_id: int, **fields
    ) -> TenantQuotaORM | None:
        """更新配额字段。"""
        if not fields:
            return await self.get_by_tenant(tenant_id)
        allowed = {
            "max_users",
            "max_llm_tokens_per_month",
            "current_llm_tokens",
            "period_start",
        }
        clean = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if clean:
            stmt = (
                update(TenantQuotaORM)
                .where(TenantQuotaORM.tenant_id == tenant_id)
                .values(**clean)
                .execution_options(synchronize_session="fetch")
            )
            await self.session.execute(stmt)
            await self.session.flush()
        return await self.get_by_tenant(tenant_id)

    async def increment_llm_tokens(
        self, tenant_id: int, tokens: int
    ) -> int:
        """增加 LLM token 用量。返回更新后的 current_llm_tokens。"""
        stmt = (
            update(TenantQuotaORM)
            .where(TenantQuotaORM.tenant_id == tenant_id)
            .values(current_llm_tokens=TenantQuotaORM.current_llm_tokens + tokens)
            .execution_options(synchronize_session="fetch")
            .returning(TenantQuotaORM.current_llm_tokens)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(result.scalar_one())

    async def reset_monthly_usage(self, tenant_id: int) -> None:
        """月初重置用量。"""
        stmt = (
            update(TenantQuotaORM)
            .where(TenantQuotaORM.tenant_id == tenant_id)
            .values(current_llm_tokens=0, period_start=datetime.utcnow())
            .execution_options(synchronize_session="fetch")
        )
        await self.session.execute(stmt)
        await self.session.flush()
