"""TenantService 单元测试。

覆盖:
- create_tenant: 默认配额按 plan 初始化
- create_tenant: slug 重复抛 ValueError
- create_tenant: 未知 plan 抛 ValueError
- get_tenant_with_quota: 返回结构正确
- update_tenant: plan 变更同步配额上限
- delete_tenant: 软禁用(is_active=False)
- check_llm_quota: 超额返回 False
- record_llm_usage: 累加并持久化
- reset_monthly_usage: 清零
- list_tenants: 仅返回 active
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import TenantORM
from services import TenantService


async def _make_tenant(
    session: AsyncSession, slug: str = "t1", plan: str = "free"
) -> TenantORM:
    svc = TenantService(session)
    return await svc.create_tenant(name=f"Tenant {slug}", slug=slug, plan=plan)


@pytest.mark.asyncio
async def test_create_tenant_initializes_quota_by_plan(db_session):
    """创建租户时按 plan 初始化配额。"""
    svc = TenantService(db_session)
    tenant = await svc.create_tenant(name="Acme", slug="acme", plan="pro")

    assert tenant.id > 0
    quota = await svc.get_quota(tenant.id)
    assert quota is not None
    assert quota.max_users == 500
    assert quota.max_llm_tokens_per_month == 500_000
    assert quota.current_llm_tokens == 0


@pytest.mark.asyncio
async def test_create_tenant_duplicate_slug_raises(db_session):
    """slug 唯一约束。"""
    svc = TenantService(db_session)
    await svc.create_tenant(name="A", slug="dup", plan="free")
    with pytest.raises(ValueError, match="already exists"):
        await svc.create_tenant(name="B", slug="dup", plan="free")


@pytest.mark.asyncio
async def test_create_tenant_unknown_plan_raises(db_session):
    """未知 plan 抛 ValueError。"""
    svc = TenantService(db_session)
    with pytest.raises(ValueError, match="unknown plan"):
        await svc.create_tenant(name="X", slug="x", plan="platinum")


@pytest.mark.asyncio
async def test_get_tenant_with_quota_returns_full_dict(db_session):
    svc = TenantService(db_session)
    tenant = await _make_tenant(db_session, slug="gt", plan="enterprise")
    detail = await svc.get_tenant_with_quota(tenant.id)

    assert detail is not None
    assert detail["id"] == tenant.id
    assert detail["slug"] == "gt"
    assert detail["plan"] == "enterprise"
    assert detail["quota"]["max_users"] == 100_000
    assert detail["quota"]["current_llm_tokens"] == 0
    assert detail["user_count"] == 0


@pytest.mark.asyncio
async def test_update_tenant_changes_plan_and_quota(db_session):
    """plan 变更同步配额上限。"""
    svc = TenantService(db_session)
    tenant = await _make_tenant(db_session, slug="up", plan="free")
    updated = await svc.update_tenant(tenant.id, plan="pro", name="Up Pro")

    assert updated.plan == "pro"
    assert updated.name == "Up Pro"
    quota = await svc.get_quota(tenant.id)
    assert quota.max_users == 500
    assert quota.max_llm_tokens_per_month == 500_000


@pytest.mark.asyncio
async def test_update_tenant_unknown_plan_raises(db_session):
    svc = TenantService(db_session)
    tenant = await _make_tenant(db_session, slug="bad", plan="free")
    with pytest.raises(ValueError, match="unknown plan"):
        await svc.update_tenant(tenant.id, plan="diamond")


@pytest.mark.asyncio
async def test_delete_tenant_soft_deactivate(db_session):
    """删除=软禁用,is_active=False。"""
    svc = TenantService(db_session)
    tenant = await _make_tenant(db_session, slug="del", plan="free")
    ok = await svc.delete_tenant(tenant.id)
    assert ok is True

    refreshed = await svc.get_tenant(tenant.id)
    assert refreshed is not None
    assert refreshed.is_active is False


@pytest.mark.asyncio
async def test_list_tenants_returns_active_only(db_session):
    svc = TenantService(db_session)
    t1 = await _make_tenant(db_session, slug="l1", plan="free")
    t2 = await _make_tenant(db_session, slug="l2", plan="free")
    await svc.delete_tenant(t2.id)

    tenants = await svc.list_tenants(limit=100)
    ids = [t.id for t in tenants]
    assert t1.id in ids
    assert t2.id not in ids


@pytest.mark.asyncio
async def test_check_llm_quota_within_limit(db_session):
    svc = TenantService(db_session)
    tenant = await _make_tenant(db_session, slug="q1", plan="free")
    # free plan: 10_000/月
    ok = await svc.check_llm_quota(tenant.id, 5000)
    assert ok is True


@pytest.mark.asyncio
async def test_check_llm_quota_exceeded(db_session):
    svc = TenantService(db_session)
    tenant = await _make_tenant(db_session, slug="q2", plan="free")
    # 先用掉 9000
    await svc.record_llm_usage(tenant.id, 9000)
    ok = await svc.check_llm_quota(tenant.id, 2000)
    assert ok is False


@pytest.mark.asyncio
async def test_record_llm_usage_accumulates(db_session):
    svc = TenantService(db_session)
    tenant = await _make_tenant(db_session, slug="r1", plan="free")
    after1 = await svc.record_llm_usage(tenant.id, 1000)
    after2 = await svc.record_llm_usage(tenant.id, 500)
    assert after1 == 1000
    assert after2 == 1500

    quota = await svc.get_quota(tenant.id)
    assert quota.current_llm_tokens == 1500


@pytest.mark.asyncio
async def test_reset_monthly_usage_zeroes_counter(db_session):
    svc = TenantService(db_session)
    tenant = await _make_tenant(db_session, slug="rs", plan="free")
    await svc.record_llm_usage(tenant.id, 3000)
    await svc.reset_monthly_usage(tenant.id)

    quota = await svc.get_quota(tenant.id)
    assert quota.current_llm_tokens == 0


@pytest.mark.asyncio
async def test_update_quota_manual_override(db_session):
    """管理员手动覆盖配额上限。"""
    svc = TenantService(db_session)
    tenant = await _make_tenant(db_session, slug="oq", plan="free")
    quota = await svc.update_quota(
        tenant.id, max_users=10, max_llm_tokens_per_month=999
    )
    assert quota.max_users == 10
    assert quota.max_llm_tokens_per_month == 999
