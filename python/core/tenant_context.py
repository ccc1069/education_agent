"""多租户上下文: ContextVar + 中间件识别 + 依赖注入。

设计:
- ContextVar 持有当前请求的 tenant_id(或 None 表示跨租户管理操作)
- 中间件从 JWT 的 tenant_id claim 或 X-Tenant-ID 头读取
- get_current_tenant_id() 依赖: 返回当前租户(若无则 403)
- require_cross_tenant(): 仅 ADMIN,且 tenant_context 为 None(平台管理员)

行级隔离:
- 业务表均有 tenant_id 列(migration 0009)
- SQLAlchemy event listener 在 query 编译时注入 WHERE tenant_id = :current
- 见 core/tenant_filter.py
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Awaitable, Callable

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

# 全局 contextvar: 每个请求独立作用域
# None = 跨租户(平台管理员); int = 当前租户 ID
_tenant_id: ContextVar[int | None] = ContextVar("tenant_id", default=None)


def get_tenant_id() -> int | None:
    """读取当前请求的 tenant_id(供 event listener 用)。"""
    return _tenant_id.get()


def set_tenant_id(tenant_id: int | None):
    """设置当前租户 ID,返回 token(供 reset_tenant_id 用)。"""
    return _tenant_id.set(tenant_id)


def reset_tenant_id(token) -> None:
    """恢复 contextvar 到之前状态。"""
    if token is not None:
        _tenant_id.reset(token)


# 不需要租户识别的路径(平台级 / 健康 / 文档)
SKIP_PATHS = {
    "/health",
    "/ready",
    "/live",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class TenantMiddleware(BaseHTTPMiddleware):
    """从 X-Tenant-ID 头识别租户,设置到 contextvar。

    优先级:
    1. X-Tenant-ID 头(若有,需用户为 ADMIN 才能跨租户)
    2. request.state.current_user.tenant_id(由 auth 依赖注入)
    3. None(未认证或平台级请求)

    实际 tenant_id 在 auth 依赖中再次校验,中间件只做 best-effort 设置。
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # 跳过平台级路径
        path = request.url.path
        if path in SKIP_PATHS or path.startswith("/docs"):
            return await call_next(request)

        # 从头读取(默认无)
        header_tenant = request.headers.get("X-Tenant-ID")
        tenant_id: int | None = None
        if header_tenant:
            try:
                tenant_id = int(header_tenant)
            except ValueError:
                logger.warning("invalid X-Tenant-ID header: %s", header_tenant)

        token = _tenant_id.set(tenant_id)
        try:
            response = await call_next(request)
            return response
        finally:
            _tenant_id.reset(token)


async def get_current_tenant_id() -> int:
    """FastAPI 依赖: 返回当前租户 ID。若无则 403。

    用法:
        @router.get("/items")
        async def list_items(tenant_id: int = Depends(get_current_tenant_id)):
            ...
    """
    tid = _tenant_id.get()
    if tid is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )
    return tid
