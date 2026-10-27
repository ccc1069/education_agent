"""RateLimiter 单元测试 + 限流 API 集成测试。"""

from __future__ import annotations

import asyncio
import time

import pytest

from core.rate_limiter import (
    RateLimiter,
    RateLimitMiddleware,
    get_rate_limiter,
    rate_limit,
    reset_rate_limiter_for_test,
)


# ---------- 内存后端 ----------


@pytest.mark.asyncio
async def test_memory_limiter_allows_under_limit():
    limiter = RateLimiter()
    for i in range(5):
        allowed, headers = await limiter.check("test_key", limit=5, window=60)
        assert allowed is True, f"call {i} should be allowed"
    assert "X-RateLimit-Limit" in headers
    assert headers["X-RateLimit-Limit"] == "5"


@pytest.mark.asyncio
async def test_memory_limiter_blocks_over_limit():
    limiter = RateLimiter()
    for _ in range(3):
        await limiter.check("k", limit=3, window=60)
    allowed, headers = await limiter.check("k", limit=3, window=60)
    assert allowed is False
    assert "Retry-After" not in headers  # Retry-After 由依赖加
    assert headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_memory_limiter_window_reset():
    """窗口过后计数重置。"""
    limiter = RateLimiter()
    # 用极短 window 加速
    for _ in range(2):
        await limiter.check("k", limit=2, window=0.1)
    # 立即第 3 次应被拒
    allowed, _ = await limiter.check("k", limit=2, window=0.1)
    assert allowed is False
    # 等窗口过期
    await asyncio.sleep(0.15)
    allowed, _ = await limiter.check("k", limit=2, window=0.1)
    assert allowed is True


@pytest.mark.asyncio
async def test_memory_limiter_key_isolation():
    """不同 key 互不影响。"""
    limiter = RateLimiter()
    await limiter.check("user:1", limit=1, window=60)
    allowed_a, _ = await limiter.check("user:1", limit=1, window=60)
    allowed_b, _ = await limiter.check("user:2", limit=1, window=60)
    assert allowed_a is False
    assert allowed_b is True


@pytest.mark.asyncio
async def test_memory_limiter_concurrent_safe():
    """并发调用不超量。"""
    limiter = RateLimiter()

    async def call():
        allowed, _ = await limiter.check("concurrent", limit=10, window=60)
        return allowed

    results = await asyncio.gather(*[call() for _ in range(20)])
    allowed_count = sum(1 for r in results if r)
    # 并发下不应超过 limit
    assert allowed_count <= 10


# ---------- 单例 ----------


def test_get_rate_limiter_singleton():
    reset_rate_limiter_for_test()
    a = get_rate_limiter()
    b = get_rate_limiter()
    assert a is b
    reset_rate_limiter_for_test()


# ---------- FastAPI 依赖: login 限流 ----------


@pytest.mark.asyncio
async def test_login_rate_limit_blocks_after_max(client):
    """连续 6 次错误登录,第 6 次应返回 429(前 5 次返回 401)。"""
    # 全局 IP 限流是 100/min,登录单独限流 5/min,所以登录限流先触发
    # 但全局中间件也会计数,6 次 << 100,不影响
    body = {"email": "nonexistent@example.com", "password": "wrongpassword"}
    codes = []
    for _ in range(6):
        r = await client.post("/api/v1/auth/login", json=body)
        codes.append(r.status_code)
    # 前 5 次是 401(用户不存在),第 6 次 429
    assert codes[:5] == [401] * 5
    assert codes[5] == 429
    # 验证响应头
    r6 = await client.post("/api/v1/auth/login", json=body)
    assert r6.status_code == 429
    assert "Retry-After" in r6.headers
    assert "X-RateLimit-Limit" in r6.headers


@pytest.mark.asyncio
async def test_register_rate_limit(client):
    """注册端点限流(3 次/分钟)。"""
    body = {"email": "u@example.com", "password": "longenough", "name": "U"}
    codes = []
    for _ in range(4):
        r = await client.post("/api/v1/auth/register", json=body)
        codes.append(r.status_code)
    # 前 3 次是 201 或 400(重复 email),第 4 次 429
    assert codes[3] == 429


@pytest.mark.asyncio
async def test_rate_limit_disabled_when_setting_off(client, monkeypatch):
    """禁用限流时,超过 limit 也不返回 429。"""
    from config.settings import settings

    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    reset_rate_limiter_for_test()  # 清空之前的计数

    body = {"email": "x@example.com", "password": "wrong"}
    codes = []
    for _ in range(10):
        r = await client.post("/api/v1/auth/login", json=body)
        codes.append(r.status_code)
    # 全是 401,没有 429
    assert all(c == 401 for c in codes)


@pytest.mark.asyncio
async def test_global_ip_rate_limit(client, monkeypatch):
    """全局 IP 限流: 超过 N 次后所有端点都 429。"""
    from config.settings import settings

    # 降低全局阈值加速测试
    monkeypatch.setattr(settings, "rate_limit_global_per_min", 5)
    reset_rate_limiter_for_test()

    # 调用一个不需要 auth 的端点(/api/v1/auth/login 因限流依赖会先返回 429)
    # 用 /api/v1/auth/login 会先碰到 login 限流,所以测试 /me 端点(401 也算经过中间件)
    codes = []
    for _ in range(8):
        r = await client.get("/api/v1/auth/me")
        codes.append(r.status_code)
    # 前 5 次是 401(未登录),第 6+ 次 429
    assert 429 in codes
    assert codes[-1] == 429


@pytest.mark.asyncio
async def test_rate_limit_skips_health(client):
    """健康检查端点不限流。"""
    for _ in range(20):
        r = await client.get("/health")
        assert r.status_code == 200
