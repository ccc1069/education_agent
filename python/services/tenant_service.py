"""TenantService: 租户 CRUD + 配额管理 + LLM token 计费。

设计:
- create_tenant: 创建租户 + 默认配额(按 plan)
- list_tenants: 平台管理员查看所有
- get_tenant: 查单个
- update_tenant: 改 plan / name / is_active
- check_llm_quota: 检查 LLM token 是否超额(返回 bool)
- record_llm_usage: 增加用量
- reset_monthly_usage: 月初重置(由 cron 调用)

权限:
- 所有方法仅 ADMIN 角色可调(在路由层校验)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import TenantORM, TenantQuotaORM
from repositories import TenantQuotaRepository, TenantRepository

logger = logging.getLogger(__name__)

ALLOWED_PLANS = {"free", "pro", "enterprise"}


class TenantService:
    """租户管理服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tenant_repo = TenantRepository(session)
        self.quota_repo = TenantQuotaRepository(session)

    # ---------- CRUD ----------

    async def create_tenant(
        self,
        name: str,
        slug: str,
        plan: str = "free",
        settings: dict[str, Any] | None = None,
    ) -> TenantORM:
        """创建租户 + 默认配额。"""
        if plan not in ALLOWED_PLANS:
            raise ValueError(f"unknown plan={plan}, allowed={ALLOWED_PLANS}")
        existing = await self.tenant_repo.get_by_slug(slug)
        if existing is not None:
            raise ValueError(f"slug={slug} already exists")
        tenant = TenantORM(
            name=name,
            slug=slug,
            plan=plan,
            settings=settings or {},
        )
        self.session.add(tenant)
        await self.session.flush()
        # 自动创建配额
        await self.quota_repo.get_or_create(tenant.id, plan=plan)
        await self.session.commit()
        logger.info("tenant_created: id=%d slug=%s plan=%s", tenant.id, slug, plan)
        return tenant

    async def get_tenant(self, tenant_id: int) -> TenantORM | None:
        return await self.tenant_repo.get_by_id(tenant_id)

    async def get_tenant_with_quota(
        self, tenant_id: int
    ) -> dict[str, Any] | None:
        """查租户 + 配额(供 API 返回)。"""
        tenant = await self.tenant_repo.get_by_id(tenant_id)
        if tenant is None:
            return None
        quota = await self.quota_repo.get_by_tenant(tenant_id)
        user_count = await self.tenant_repo.count_users(tenant_id)
        return {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "plan": tenant.plan,
            "is_active": tenant.is_active,
            "settings": tenant.settings or {},
            "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
            "user_count": user_count,
            "quota": {
                "max_users": quota.max_users if quota else None,
                "max_llm_tokens_per_month": (
                    quota.max_llm_tokens_per_month if quota else None
                ),
                "current_llm_tokens": quota.current_llm_tokens if quota else 0,
                "period_start": (
                    quota.period_start.isoformat() if quota and quota.period_start else None
                ),
            },
        }

    async def list_tenants(
        self, limit: int = 100, offset: int = 0
    ) -> list[TenantORM]:
        return await self.tenant_repo.list_active(limit=limit, offset=offset)

    async def update_tenant(
        self, tenant_id: int, **fields: Any
    ) -> TenantORM | None:
        """更新租户字段(name/plan/is_active/settings)。"""
        allowed = {"name", "plan", "is_active", "settings"}
        clean = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "plan" in clean and clean["plan"] not in ALLOWED_PLANS:
            raise ValueError(f"unknown plan={clean['plan']}")
        if not clean:
            return await self.tenant_repo.get_by_id(tenant_id)
        # 用 update 语句
        from sqlalchemy import update as sa_update

        stmt = (
            sa_update(TenantORM)
            .where(TenantORM.id == tenant_id)
            .values(**clean)
            .execution_options(synchronize_session="fetch")
        )
        await self.session.execute(stmt)
        await self.session.flush()
        # plan 变更时同步更新配额上限
        if "plan" in clean:
            quota = await self.quota_repo.get_or_create(tenant_id, plan=clean["plan"])
            new_defaults = TenantQuotaRepository.PLAN_DEFAULTS.get(
                clean["plan"], TenantQuotaRepository.PLAN_DEFAULTS["free"]
            )
            await self.quota_repo.update(
                tenant_id,
                max_users=new_defaults["max_users"],
                max_llm_tokens_per_month=new_defaults["max_llm_tokens_per_month"],
            )
        await self.session.commit()
        return await self.tenant_repo.get_by_id(tenant_id)

    async def delete_tenant(self, tenant_id: int) -> bool:
        """软禁用租户(is_active=False),不真删(避免数据丢失)。"""
        await self.update_tenant(tenant_id, is_active=False)
        return True

    # ---------- 配额 ----------

    async def get_quota(self, tenant_id: int) -> TenantQuotaORM | None:
        return await self.quota_repo.get_by_tenant(tenant_id)

    async def update_quota(
        self, tenant_id: int, **fields: Any
    ) -> TenantQuotaORM | None:
        result = await self.quota_repo.update(tenant_id, **fields)
        await self.session.commit()
        return result

    async def check_llm_quota(self, tenant_id: int, tokens: int) -> bool:
        """检查是否还能用 tokens 个 LLM token。"""
        quota = await self.quota_repo.get_or_create(tenant_id)
        if quota.max_llm_tokens_per_month <= 0:
            return True  # 不限制
        remaining = quota.max_llm_tokens_per_month - quota.current_llm_tokens
        return remaining >= tokens

    async def record_llm_usage(self, tenant_id: int, tokens: int) -> int:
        """记录 LLM token 用量。返回更新后的 current_llm_tokens。"""
        await self.quota_repo.get_or_create(tenant_id)
        result = await self.quota_repo.increment_llm_tokens(tenant_id, tokens)
        await self.session.commit()
        return result

    async def reset_monthly_usage(self, tenant_id: int) -> None:
        await self.quota_repo.reset_monthly_usage(tenant_id)
        await self.session.commit()

    async def reset_all_monthly_usage(self) -> int:
        """重置所有租户的月度用量(供 cron 调用)。返回重置数。"""
        tenants = await self.tenant_repo.list_active(limit=10000)
        for t in tenants:
            await self.quota_repo.reset_monthly_usage(t.id)
        await self.session.commit()
        return len(tenants)
