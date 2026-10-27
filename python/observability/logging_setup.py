"""结构化日志配置(structlog)。

设计:
- 开发环境: 控制台彩色输出(console_renderer)
- 生产环境: JSON 输出(json_renderer),便于 ELK / Loki 采集
- 自动注入: correlation_id, request_id, 服务名,版本
- 与标准 logging 兼容,旧代码 logger.info() 自动走 structlog
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from config.settings import settings


def _add_app_context(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    """注入应用级上下文。"""
    event_dict.setdefault("service", "multi-agent-edu")
    event_dict.setdefault("env", settings.env)
    return event_dict


def _add_correlation_id(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    """注入当前请求的 correlation_id(若有)。"""
    cid = get_correlation_id()
    if cid:
        event_dict.setdefault("correlation_id", cid)
    return event_dict


def configure_logging() -> None:
    """配置 structlog + 标准 logging。

    必须在应用启动早期调用(早于 Agent 创建)。
    """
    log_level = logging.DEBUG if settings.is_dev else logging.INFO

    # 共享 processors: timestamper + context injection
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        _add_app_context,
        _add_correlation_id,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
    ]

    # structlog 配置
    structlog.configure(
        processors=[
            *shared_processors,
            # 决定渲染器: dev=console, prod=json
            (
                structlog.dev.ConsoleRenderer(colors=settings.is_dev)
                if settings.is_dev
                else structlog.processors.JSONRenderer()
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 桥接标准 logging -> structlog(旧 logger.info() 也会走 structlog)
    handler = logging.StreamHandler(sys.stdout)
    if settings.is_dev:
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=structlog.dev.ConsoleRenderer(colors=True),
                foreign_pre_chain=shared_processors,
            )
        )
    else:
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=structlog.processors.JSONRenderer(),
                foreign_pre_chain=shared_processors,
            )
        )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # 降低噪声日志
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.is_dev else logging.WARNING
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """获取一个 structlog logger。"""
    return structlog.get_logger(name)


# 循环导入避免: correlation_id 在 _add_correlation_id 中使用
from observability.correlation import get_correlation_id  # noqa: E402
