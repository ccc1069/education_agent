"""API 集成测试: 认证路由 + 业务路由 + 错误处理。"""

import pytest


# ---------- /health /ready /live /metrics (公开) ----------


@pytest.mark.asyncio
async def test_live_returns_ok_without_auth(client):
    resp = await client.get("/live")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_metrics_returns_ok_without_auth(client):
    resp = await client.get("/metrics")
    assert resp.status_code == 200


# ---------- /api/v1/auth/register ----------


@pytest.mark.asyncio
async def test_register_learner_success(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "new@example.com",
            "password": "StrongPass123!",
            "name": "新学生",
        },
    )
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["success"] if "success" in body else "user_id" in body or "data" in body


@pytest.mark.asyncio
async def test_register_duplicate_email_fails(client):
    payload = {
        "email": "dup@example.com",
        "password": "StrongPass123!",
        "name": "Dup User",
    }
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 400


# ---------- /api/v1/auth/login ----------


@pytest.mark.asyncio
async def test_login_success(client):
    # 先注册
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "StrongPass123!",
            "name": "Login User",
        },
    )
    # 再登录
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "StrongPass123!"},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongpass@example.com",
            "password": "StrongPass123!",
            "name": "WP User",
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpass@example.com", "password": "WrongPass!"},
    )
    assert resp.status_code in (400, 401)


# ---------- /api/v1/auth/me ----------


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def _register_and_login(client, email: str, password: str = "StrongPass123!") -> str:
    """辅助: 注册 + 登录,返回 access token。"""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Test User"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return login.json()["access_token"]


@pytest.mark.asyncio
async def test_me_returns_user_info(client):
    token = await _register_and_login(client, "me@example.com")
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"


# ---------- /api/v1/learners/* (需认证) ----------


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_no_token(client):
    resp = await client.get("/api/v1/knowledge-graph")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_accepts_valid_token(client):
    token = await _register_and_login(client, "prot@example.com")
    resp = await client.get(
        "/api/v1/knowledge-graph", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invalid_token_rejected(client):
    resp = await client.get(
        "/api/v1/knowledge-graph",
        headers={"Authorization": "Bearer fake.token.here"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_with_wrong_secret_rejected(client):
    """用错误的 secret 签的 token 应被拒绝。"""
    import jwt as pyjwt
    from config.settings import settings

    fake_token = pyjwt.encode(
        {
            "sub": "1",
            "email": "x@example.com",
            "role": "student",
            "type": "access",
            "exp": 9999999999,
            "iat": 1,
            "jti": "test-jti",
        },
        "wrong-secret",
        algorithm=settings.jwt_algorithm,
    )
    resp = await client.get(
        "/api/v1/knowledge-graph",
        headers={"Authorization": f"Bearer {fake_token}"},
    )
    assert resp.status_code == 401
