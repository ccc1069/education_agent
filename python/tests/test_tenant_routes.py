"""租户管理 API 集成测试。

覆盖:
- 非 ADMIN 访问 403
- 未登录 401
- POST 创建租户 201 + 默认配额
- GET 列表
- GET /{id} 详情(含配额)
- POST /{id} 更新
- POST /{id}/delete 软禁用
- POST /{id}/quota 改配额
- POST /{id}/quota/reset 重置用量
- slug 重复 400
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_tenant_routes_unauth_401(client: AsyncClient):
    r = await client.get("/api/v1/tenants")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_tenant_routes_student_forbidden(client: AsyncClient, auth_headers):
    """非管理员被拒。"""
    r = await client.get("/api/v1/tenants", headers=auth_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_tenant_routes_teacher_forbidden(client: AsyncClient, teacher_headers):
    r = await client.get("/api/v1/tenants", headers=teacher_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_tenant_returns_201(client: AsyncClient, admin_headers):
    r = await client.post(
        "/api/v1/tenants",
        headers=admin_headers,
        json={"name": "Acme", "slug": "acme", "plan": "pro"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["slug"] == "acme"
    assert data["plan"] == "pro"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_tenant_duplicate_slug_400(client: AsyncClient, admin_headers):
    payload = {"name": "A", "slug": "dup-slug", "plan": "free"}
    r1 = await client.post("/api/v1/tenants", headers=admin_headers, json=payload)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/tenants", headers=admin_headers, json=payload)
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_create_tenant_invalid_slug_422(client: AsyncClient, admin_headers):
    """slug 必须 a-z0-9 开头。"""
    r = await client.post(
        "/api/v1/tenants",
        headers=admin_headers,
        json={"name": "X", "slug": "Invalid Slug", "plan": "free"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_tenants(client: AsyncClient, admin_headers):
    # 创建 2 个
    await client.post(
        "/api/v1/tenants",
        headers=admin_headers,
        json={"name": "T1", "slug": "lst-1", "plan": "free"},
    )
    await client.post(
        "/api/v1/tenants",
        headers=admin_headers,
        json={"name": "T2", "slug": "lst-2", "plan": "free"},
    )
    r = await client.get("/api/v1/tenants", headers=admin_headers)
    assert r.status_code == 200
    slugs = [t["slug"] for t in r.json()]
    assert "lst-1" in slugs
    assert "lst-2" in slugs


@pytest.mark.asyncio
async def test_get_tenant_detail(client: AsyncClient, admin_headers):
    create = await client.post(
        "/api/v1/tenants",
        headers=admin_headers,
        json={"name": "Detail", "slug": "detail", "plan": "enterprise"},
    )
    tid = create.json()["id"]
    r = await client.get(f"/api/v1/tenants/{tid}", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == tid
    assert data["plan"] == "enterprise"
    assert data["quota"]["max_users"] == 100_000
    assert data["user_count"] == 0


@pytest.mark.asyncio
async def test_get_tenant_not_found_404(client: AsyncClient, admin_headers):
    r = await client.get("/api/v1/tenants/999999", headers=admin_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_tenant(client: AsyncClient, admin_headers):
    create = await client.post(
        "/api/v1/tenants",
        headers=admin_headers,
        json={"name": "Old", "slug": "upd", "plan": "free"},
    )
    tid = create.json()["id"]
    r = await client.post(
        f"/api/v1/tenants/{tid}",
        headers=admin_headers,
        json={"name": "New", "plan": "pro"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "New"
    assert data["plan"] == "pro"


@pytest.mark.asyncio
async def test_delete_tenant_soft_delete(client: AsyncClient, admin_headers):
    create = await client.post(
        "/api/v1/tenants",
        headers=admin_headers,
        json={"name": "Del", "slug": "dlt", "plan": "free"},
    )
    tid = create.json()["id"]
    r = await client.post(f"/api/v1/tenants/{tid}/delete", headers=admin_headers)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_update_quota(client: AsyncClient, admin_headers):
    create = await client.post(
        "/api/v1/tenants",
        headers=admin_headers,
        json={"name": "Q", "slug": "qupd", "plan": "free"},
    )
    tid = create.json()["id"]
    r = await client.post(
        f"/api/v1/tenants/{tid}/quota",
        headers=admin_headers,
        json={"max_users": 25, "max_llm_tokens_per_month": 8888},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["max_users"] == 25
    assert data["max_llm_tokens_per_month"] == 8888


@pytest.mark.asyncio
async def test_reset_quota(client: AsyncClient, admin_headers):
    create = await client.post(
        "/api/v1/tenants",
        headers=admin_headers,
        json={"name": "R", "slug": "rset", "plan": "free"},
    )
    tid = create.json()["id"]
    r = await client.post(
        f"/api/v1/tenants/{tid}/quota/reset", headers=admin_headers
    )
    assert r.status_code == 200
    assert r.json()["reset"] is True


@pytest.mark.asyncio
async def test_reset_quota_not_found(client: AsyncClient, admin_headers):
    r = await client.post(
        "/api/v1/tenants/999999/quota/reset", headers=admin_headers
    )
    assert r.status_code == 404
