"""API 限流: 滑动窗口 + Redis 后端(内存 fallback)。

设计:
- 滑动窗口: 用 sorted set(timestamps) 而非简单计数,允许精确的 N 次/窗口
- 后端: 优先 Redis(生产),fallback 到内存 dict(测试/单机)
- 双维度: 用户 (user_id) + IP
- 依赖工厂 rate_limit(limit, window): 用于 FastAPI Depends
- 全局中间件 RateLimitMiddleware: 每 IP 全局配额

返回头:
- X-RateLimit-Limit: 窗口上限
- X-RateLimit-Remaining: 剩余
- X-RateLimit-Reset: 重置时间(unix 秒)
- Retry-After: 拒绝时等待秒数
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from config.settings import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """滑动窗口限流器。Redis 优先,内存 fallback。"""

    def __init__(self, redis_client=None) -> None:
        self._redis = redis_client
        self._memory: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()  # 内存后端的并发安全

    async def check(self, key: str, limit: int, window: int) -> tuple[bool, dict]:
        """检查 key 是否允许通过。

        Returns:
            (allowed, headers) - headers 包含 X-RateLimit-* 字段。
        """
        now = time.time()
        window_start = now - window

        if self._redis is not None:
            return await self._check_redis(key, limit, window, now, window_start)
        return await self._check_memory(key, limit, window, now, window_start)

    async def _check_memory(
        self, key: str, limit: int, window: int, now: float, window_start: float
    ) -> tuple[bool, dict]:
        async with self._lock:
            timestamps = self._memory.get(key, [])
            # 清理过期
            timestamps = [t for t in timestamps if t > window_start]
            if len(timestamps) >= limit:
                reset_at = timestamps[0] + window
                return False, self._headers(limit, 0, int(reset_at - now), window)
            timestamps.append(now)
            self._memory[key] = timestamps
            remaining = limit - len(timestamps)
            reset_at = timestamps[0] + window if timestamps else now + window
            return True, self._headers(limit, remaining, int(reset_at - now), window)

    async def _check_redis(
        self, key: str, limit: int, window: int, now: float, window_start: float
    ) -> tuple[bool, dict]:
        redis_key = f"ratelimit:{key}"
        # 用 sorted set: score=timestamp, member=uuid
        import uuid

        member = f"{now}:{uuid.uuid4().hex}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zadd(redis_key, {member: now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, window)
            _, _, count, _ = await pipe.execute()
        if count > limit:
            # 拒绝: 取最早的 timestamp 算 reset
            earliest = await self._redis.zrange(redis_key, 0, 0, withscores=True)
            if earliest:
                reset_at = earliest[0][1] + window
            else:
                reset_at = now + window
            return False, self._headers(limit, 0, int(reset_at - now), window)
        remaining = limit - count
        return True, self._headers(limit, remaining, window, window)

    @staticmethod
    def _headers(limit: int, remaining: int, reset_in: int, window: int) -> dict:
        return {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(0, remaining)),
            "X-RateLimit-Reset": str(max(0, reset_in)),
        }


# ---------- 全局单例 ----------

_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """获取全局限流器单例。"""
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter


def set_rate_limiter_redis(redis_client) -> None:
    """注入 Redis 客户端(供 lifespan 调用)。"""
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(redis_client=redis_client)
    else:
        _limiter._redis = redis_client


def reset_rate_limiter_for_test() -> None:
    """测试用: 重置单例。"""
    global _limiter
    _limiter = None


# ---------- FastAPI 依赖 ----------


def _default_key(request: Request) -> str:
    """默认 key 策略: 已登录用户用 user_id,否则用 IP。"""
    user = getattr(request.state, "current_user", None)
    if user is not None:
        return f"user:{user.id}"
    client = request.client
    ip = client.host if client else "unknown"
    # 若经过反向代理,优先 X-Forwarded-For
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    return f"ip:{ip}"


def rate_limit(limit: int, window: int, key_func: Callable[[Request], str] | None = None):
    """FastAPI 依赖工厂。

    Usage:
        @router.post("/login", dependencies=[Depends(rate_limit(5, 60))])
        async def login(...): ...
    """

    async def _dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        limiter = get_rate_limiter()
        key = key_func(request) if key_func else _default_key(request)
        allowed, headers = await limiter.check(key, limit, window)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too Many Requests",
                headers={**headers, "Retry-After": str(window)},
            )

    return _dependency


# ---------- 全局 IP 限流中间件 ----------


class RateLimitMiddleware(BaseHTTPMiddleware):
    """全局 IP 限流: 每 IP 每分钟 N 次(默认 100)。

    跳过 /metrics /health /ready /live 等监控端点。
    """

    SKIP_PATHS = {"/metrics", "/health", "/ready", "/live", "/"}

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        client = request.client
        ip = client.host if client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()

        limiter = get_rate_limiter()
        allowed, headers = await limiter.check(
            f"global:{ip}",
            settings.rate_limit_global_per_min,
            60,
        )
        if not allowed:
            return Response(
                content='{"detail":"Too Many Requests"}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
                headers={**headers, "Retry-After": "60"},
            )
        response = await call_next(request)
        for k, v in headers.items():
            response.headers[k] = v
        return response
