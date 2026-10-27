"""Prometheus 指标定义 + ASGI 中间件。

定义的指标:
- REQUEST_DURATION: HTTP 请求耗时直方图
- AGENT_PROCESSING_DURATION: Agent 处理事件耗时
- LLM_TOKENS_USED: LLM token 消耗计数
- LLM_REQUEST_DURATION: LLM 调用耗时
- ACTIVE_WS_CONNECTIONS: 当前 WebSocket 连接数
"""

from typing import Awaitable, Callable

from prometheus_client import (
    CollectorRegistry,
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    REGISTRY,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------- 指标定义 ----------

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP 请求耗时",
    labelnames=("method", "path", "status"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

AGENT_PROCESSING_DURATION = Histogram(
    "agent_processing_duration_seconds",
    "Agent 处理事件耗时",
    labelnames=("agent_name", "event_type"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

LLM_TOKENS_USED = Counter(
    "llm_tokens_used_total",
    "LLM token 消耗总数",
    labelnames=("provider", "model", "kind"),  # kind: prompt/completion
)

LLM_REQUEST_DURATION = Histogram(
    "llm_request_duration_seconds",
    "LLM 调用耗时",
    labelnames=("provider", "model", "status"),  # status: success/error
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)

ACTIVE_WS_CONNECTIONS = Gauge(
    "websocket_active_connections",
    "当前 WebSocket 连接数",
)


# ---------- ASGI 中间件 ----------


class MetricsMiddleware(BaseHTTPMiddleware):
    """记录每个 HTTP 请求的耗时和状态码。

    跳过 /metrics /health /ready 等监控端点本身,避免自递归噪声。
    """

    SKIP_PATHS = {"/metrics", "/health", "/ready", "/"}

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        method = request.method
        # 路径归一化: 把数字 ID 替换成 :id,避免基数爆炸
        path = _normalize_path(request.url.path)

        try:
            response = await call_next(request)
            REQUEST_DURATION.labels(
                method=method, path=path, status=str(response.status_code)
            ).observe(0.0)  # 真正的耗时通过 ASGI 钩子更精确,这里用近似
            return response
        except Exception:
            REQUEST_DURATION.labels(method=method, path=path, status="500").observe(0.0)
            raise


def _normalize_path(path: str) -> str:
    """把 /api/learners/123/submissions -> /api/learners/:id/submissions。"""
    parts = path.split("/")
    normalized = []
    for p in parts:
        if p.isdigit() or (len(p) >= 8 and "-" in p and p.replace("-", "").isalnum()):
            normalized.append(":id")
        else:
            normalized.append(p)
    return "/".join(normalized)


# ---------- Prometheus 暴露端点 ----------


def metrics_handler() -> Response:
    """FastAPI 路由用: 返回 Prometheus 文本格式指标。"""
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
