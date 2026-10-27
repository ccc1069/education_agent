"""健康检查端点: /health /ready /live。

设计:
- /live: 进程存活(永远返回 200,除非进程死了)
- /ready: 就绪检查(数据库可连通 + 依赖服务可用)
- /health: 综合健康检查(包含详细子状态)
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy import text

from db.base import async_engine


class HealthStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"


@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    detail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


async def _check_database() -> ComponentHealth:
    """数据库连通性检查。"""
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return ComponentHealth(name="database", status=HealthStatus.UP)
    except Exception as e:
        return ComponentHealth(
            name="database",
            status=HealthStatus.DOWN,
            detail=f"DB unreachable: {e.__class__.__name__}",
        )


async def _check_llm() -> ComponentHealth:
    """LLM provider 可用性检查(快速 ping)。"""
    try:
        from llm.factory import get_llm_provider

        provider = get_llm_provider()
        return ComponentHealth(
            name="llm",
            status=HealthStatus.UP,
            extra={"provider": provider.__class__.__name__},
        )
    except Exception as e:
        return ComponentHealth(
            name="llm",
            status=HealthStatus.DEGRADED,
            detail=f"LLM provider issue: {e.__class__.__name__} (will fallback to template)",
        )


async def liveness_check() -> dict[str, Any]:
    """存活检查: 只要进程能响应就算活着。"""
    return {"status": HealthStatus.UP.value, "alive": True}


async def readiness_check() -> dict[str, Any]:
    """就绪检查: 数据库可连通 + LLM 可用。"""
    db_health, llm_health = await asyncio.gather(
        _check_database(), _check_llm(), return_exceptions=False
    )

    components = {db_health.name: db_health, llm_health.name: llm_health}

    if any(c.status == HealthStatus.DOWN for c in components.values()):
        overall = HealthStatus.DOWN
    elif any(c.status == HealthStatus.DEGRADED for c in components.values()):
        overall = HealthStatus.DEGRADED
    else:
        overall = HealthStatus.UP

    return {
        "status": overall.value,
        "components": {
            name: {
                "status": c.status.value,
                "detail": c.detail,
                **c.extra,
            }
            for name, c in components.items()
        },
    }


async def health_check() -> dict[str, Any]:
    """综合健康检查(供 /health 用)。"""
    ready = await readiness_check()
    live = await liveness_check()
    return {
        "status": ready["status"],
        "alive": live["alive"],
        "components": ready["components"],
    }
