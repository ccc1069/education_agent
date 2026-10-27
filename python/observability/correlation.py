"""Correlation ID 中间件: 为每个请求生成唯一 ID,贯穿日志和追踪。

设计:
- 从 X-Correlation-ID 头读取(若上游传入)
- 否则生成 uuid4
- 写入 contextvar,structlog 自动注入日志
- 通过响应头返回,便于客户端排查
"""

import uuid
from contextvars import ContextVar
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# 全局 contextvar: 每个请求独立作用域
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_correlation_id(cid: str | None) -> None:
    _correlation_id.set(cid)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """读取或生成 correlation_id,设置到 contextvar 和响应头。"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # 上游可能已经传入(便于跨服务追踪)
        cid = request.headers.get("X-Correlation-ID") or new_correlation_id()
        token = _correlation_id.set(cid)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = cid
            return response
        finally:
            _correlation_id.reset(token)
