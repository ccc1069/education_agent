"""租户管理 API(仅平台 ADMIN)。

权限:
- 所有路由仅 ADMIN 角色可访问
- 跨租户操作(无 tenant 上下文过滤)

端点:
- POST   /api/v1/tenants              创建租户
- GET    /api/v1/tenants              列出租户
- GET    /api/v1/tenants/{id}         查租户详情(含配额)
- POST   /api/v1/tenants/{id}         更新租户(name/plan/is_active)
- POST   /api/v1/tenants/{id}/delete  禁用租户(软删)
- GET    /api/v1/tenants/{id}/quota   查配额
- POST   /api/v1/tenants/{id}/quota   改配额
- POST   /api/v1/tenants/{id}/quota/reset  重置月度用量
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, get_current_active_user
from db.models import UserRole
from db.session import get_session_dep
from services import TenantService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["tenants"])


def _require_admin(current: CurrentUser = Depends(get_current_active_user)) -> CurrentUser:
    """仅平台 ADMIN 可访问。"""
    if current.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin only",
        )
    return current


# ---------- Pydantic ----------


class CreateTenantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    plan: str = Field(default="free", pattern=r"^(free|pro|enterprise)$")
    settings: dict[str, Any] = Field(default_factory=dict)


class UpdateTenantRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    plan: str | None = Field(default=None, pattern=r"^(free|pro|enterprise)$")
    is_active: bool | None = None
    settings: dict[str, Any] | None = None


class UpdateQuotaRequest(BaseModel):
    max_users: int | None = Field(default=None, ge=0)
    max_llm_tokens_per_month: int | None = Field(default=None, ge=0)


class TenantSummary(BaseModel):
    id: int
    name: str
    slug: str
    plan: str
    is_active: bool
    user_count: int = 0
    quota: dict[str, Any] | None = None


class TenantDetail(BaseModel):
    id: int
    name: str
    slug: str
    plan: str
    is_active: bool
    settings: dict[str, Any]
    created_at: str | None
    user_count: int
    quota: dict[str, Any]


# ---------- 路由 ----------


@router.post("", response_model=TenantSummary, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: CreateTenantRequest,
    _: CurrentUser = Depends(_require_admin),
    session: AsyncSession = Depends(get_session_dep),
) -> TenantSummary:
    svc = TenantService(session)
    try:
        tenant = await svc.create_tenant(
            name=body.name, slug=body.slug, plan=body.plan, settings=body.settings
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return TenantSummary(
        id=tenant.id, name=tenant.name, slug=tenant.slug, plan=tenant.plan, is_active=tenant.is_active
    )


@router.get("", response_model=list[TenantSummary])
async def list_tenants(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _: CurrentUser = Depends(_require_admin),
    session: AsyncSession = Depends(get_session_dep),
) -> list[TenantSummary]:
    svc = TenantService(session)
    tenants = await svc.list_tenants(limit=limit, offset=offset)
    items: list[TenantSummary] = []
    for t in tenants:
        detail = await svc.get_tenant_with_quota(t.id)
        if detail is None:
            continue
        items.append(
            TenantSummary(
                id=detail["id"],
                name=detail["name"],
                slug=detail["slug"],
                plan=detail["plan"],
                is_active=detail["is_active"],
                user_count=detail["user_count"],
                quota=detail["quota"],
            )
        )
    return items


@router.get("/{tenant_id}", response_model=TenantDetail)
async def get_tenant(
    tenant_id: int,
    _: CurrentUser = Depends(_require_admin),
    session: AsyncSession = Depends(get_session_dep),
) -> TenantDetail:
    svc = TenantService(session)
    detail = await svc.get_tenant_with_quota(tenant_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantDetail(**detail)


@router.post("/{tenant_id}", response_model=TenantSummary)
async def update_tenant(
    tenant_id: int,
    body: UpdateTenantRequest,
    _: CurrentUser = Depends(_require_admin),
    session: AsyncSession = Depends(get_session_dep),
) -> TenantSummary:
    svc = TenantService(session)
    try:
        tenant = await svc.update_tenant(
            tenant_id,
            name=body.name,
            plan=body.plan,
            is_active=body.is_active,
            settings=body.settings,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantSummary(
        id=tenant.id, name=tenant.name, slug=tenant.slug, plan=tenant.plan, is_active=tenant.is_active
    )


@router.post("/{tenant_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: int,
    _: CurrentUser = Depends(_require_admin),
    session: AsyncSession = Depends(get_session_dep),
) -> None:
    svc = TenantService(session)
    ok = await svc.delete_tenant(tenant_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")


@router.post("/{tenant_id}/quota")
async def update_quota(
    tenant_id: int,
    body: UpdateQuotaRequest,
    _: CurrentUser = Depends(_require_admin),
    session: AsyncSession = Depends(get_session_dep),
) -> dict[str, Any]:
    svc = TenantService(session)
    quota = await svc.update_quota(
        tenant_id,
        max_users=body.max_users,
        max_llm_tokens_per_month=body.max_llm_tokens_per_month,
    )
    if quota is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return {
        "tenant_id": tenant_id,
        "max_users": quota.max_users,
        "max_llm_tokens_per_month": quota.max_llm_tokens_per_month,
        "current_llm_tokens": quota.current_llm_tokens,
    }


@router.post("/{tenant_id}/quota/reset")
async def reset_quota(
    tenant_id: int,
    _: CurrentUser = Depends(_require_admin),
    session: AsyncSession = Depends(get_session_dep),
) -> dict[str, Any]:
    svc = TenantService(session)
    if await svc.get_tenant(tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    await svc.reset_monthly_usage(tenant_id)
    return {"tenant_id": tenant_id, "reset": True}
