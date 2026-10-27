"""可观测性: 结构化日志 + Prometheus 指标 + OpenTelemetry 追踪 + 健康检查。"""

from observability.logging_setup import configure_logging, get_logger
from observability.correlation import (
    CorrelationIdMiddleware,
    get_correlation_id,
    set_correlation_id,
)
from observability.metrics import (
    REQUEST_DURATION,
    AGENT_PROCESSING_DURATION,
    LLM_TOKENS_USED,
    LLM_REQUEST_DURATION,
    ACTIVE_WS_CONNECTIONS,
    MetricsMiddleware,
    metrics_handler,
)
from observability.tracing import configure_tracing, instrument_app
from observability.health import (
    HealthStatus,
    health_check,
    readiness_check,
    liveness_check,
)

__all__ = [
    "configure_logging",
    "get_logger",
    "CorrelationIdMiddleware",
    "get_correlation_id",
    "set_correlation_id",
    "REQUEST_DURATION",
    "AGENT_PROCESSING_DURATION",
    "LLM_TOKENS_USED",
    "LLM_REQUEST_DURATION",
    "ACTIVE_WS_CONNECTIONS",
    "MetricsMiddleware",
    "metrics_handler",
    "configure_tracing",
    "instrument_app",
    "HealthStatus",
    "health_check",
    "readiness_check",
    "liveness_check",
]
