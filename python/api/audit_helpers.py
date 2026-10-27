"""审计写入辅助: 统一 IP/UA 提取与 log_action 调用。"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from services import AuditService


def client_ip(request: Request | None) -> str:
    """提取真实客户端 IP(支持反向代理)。"""
    if request is None:
        return ""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def client_ua(request: Request | None) -> str:
    if request is None:
        return ""
    return request.headers.get("user-agent", "")[:256]


async def write_audit(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    target: str,
    request: Request | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """追加一条审计日志(HMAC 链)。"""
    audit = AuditService(session)
    await audit.log_action(
        actor=actor,
        action=action,
        target=target,
        ip=client_ip(request),
        user_agent=client_ua(request),
        metadata=metadata,
    )
