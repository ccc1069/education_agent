"""OpenTelemetry 追踪配置。

设计:
- 通过 OTEL_EXPORTER_ENDPOINT 配置 OTLP gRPC 发送地址
- 自动 instrumentation: FastAPI, SQLAlchemy, httpx, logging
- 未配置时: 返回 no-op,不影响功能
"""

from typing import Any

from config.settings import settings

_tracer_provider: Any = None  # 延迟初始化


def configure_tracing() -> None:
    """初始化 OpenTelemetry。

    若 OTEL_EXPORTER_ENDPOINT 未配置,跳过(no-op)。
    """
    global _tracer_provider

    endpoint = settings.otel_exporter_endpoint
    if not endpoint:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        # opentelemetry-sdk 未安装
        return

    # OTel exporter 需要 collector 才能验证,无法单元测试
    resource = Resource.create(  # pragma: no cover
        {
            "service.name": "multi-agent-edu",
            "service.version": "2.0.0",
            "deployment.environment": settings.env,
        }
    )

    provider = TracerProvider(resource=resource)  # pragma: no cover
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)  # pragma: no cover
    provider.add_span_processor(BatchSpanProcessor(exporter))  # pragma: no cover
    trace.set_tracer_provider(provider)  # pragma: no cover

    _tracer_provider = provider  # pragma: no cover


def instrument_app(app: Any) -> None:
    """对 FastAPI 应用做自动 instrumentation。"""
    if _tracer_provider is None:
        # tracing 未启用
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)  # pragma: no cover
    except ImportError:
        pass

    try:
        from opentelemetry.instrumentation.sqlalchemy import (
            SQLAlchemyInstrumentor,
        )
        # 引擎在 db.base 中,直接 instrument 已存在的 engine
        from db.base import engine
        if engine is not None:
            SQLAlchemyInstrumentor.instrument_engine(engine.sync_engine)  # pragma: no cover
    except (ImportError, AttributeError):
        pass

    try:
        from opentelemetry.instrumentation.httpx import (
            HTTPXClientInstrumentor,
        )
        HTTPXClientInstrumentor().instrument()  # pragma: no cover
    except ImportError:
        pass

    try:
        from opentelemetry.instrumentation.logging import (
            LoggingInstrumentor,
        )
        LoggingInstrumentor().instrument(set_logging_format=True)  # pragma: no cover
    except ImportError:
        pass
