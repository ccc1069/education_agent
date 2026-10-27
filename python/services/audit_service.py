"""AuditService: 审计日志 HMAC 链。

设计:
- 追加写: 每次记录都基于上一条 curr_hash 计算自身 hash
- HMAC-SHA256(secret, prev_hash || id || actor || action || target || created_at)
- 链验证: 从任意点开始重算,与存储的 curr_hash 比对
- 不可篡改: 修改任一字段 -> 后续所有 hash 校验失败
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLogORM
from repositories import AuditRepository

logger = logging.getLogger(__name__)

# 签名用的 secret,与 JWT 共用 jwt_secret_key(避免引入新配置)
# 生产环境强烈建议单独配置 AUDIT_HMAC_SECRET
_HMAC_SECRET: bytes | None = None


def _get_hmac_secret() -> bytes:
    """加载 HMAC secret。

    优先级: AUDIT_HMAC_SECRET > JWT_SECRET_KEY > dev fallback
    """
    import os

    global _HMAC_SECRET
    if _HMAC_SECRET is not None:
        return _HMAC_SECRET

    raw = os.environ.get("AUDIT_HMAC_SECRET") or os.environ.get(
        "JWT_SECRET_KEY", "audit-chain-dev-only-not-for-prod"
    )
    _HMAC_SECRET = raw.encode("utf-8")
    return _HMAC_SECRET


def _reset_hmac_secret_for_test() -> None:
    """测试用: 重置缓存的 secret(切换环境变量后调用)。"""
    global _HMAC_SECRET
    _HMAC_SECRET = None


def compute_hash(
    log_id: int,
    actor: str,
    action: str,
    target: str,
    created_at: datetime,
    prev_hash: str,
) -> str:
    """计算审计日志的 HMAC。

    HMAC 输入 = prev_hash || id || actor || action || target || created_at_iso
    """
    payload = "|".join(
        [
            prev_hash,
            str(log_id),
            actor,
            action,
            target,
            created_at.isoformat() if created_at else "",
        ]
    )
    return hmac.new(
        _get_hmac_secret(), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


class AuditService:
    """审计日志服务: 写入 + 链验证。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AuditRepository(session)

    async def log_action(
        self,
        actor: str,
        action: str,
        target: str,
        ip: str = "",
        user_agent: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """追加一条审计日志(自动接链)。

        参数:
            actor: 操作者(email 或 service name)
            action: 动作类型(login / export_data / delete_user / ...)
            target: 操作目标(user:42 / class:1 / ...)
            ip: 来源 IP
            user_agent: UA
            metadata: 附加数据(非敏感)
        """
        prev_hash = await self.repo.get_last_hash()
        # 先 flush 拿到 id,再算 hash
        log = AuditLogORM(
            actor=actor,
            action=action,
            target=target,
            ip=ip,
            user_agent=user_agent,
            metadata_=metadata or {},
            prev_hash=prev_hash,
            curr_hash="",  # 占位,稍后更新
        )
        self.session.add(log)
        await self.session.flush()  # 拿到 log.id 与 log.created_at

        log.curr_hash = compute_hash(
            log_id=log.id,
            actor=log.actor,
            action=log.action,
            target=log.target,
            created_at=log.created_at,
            prev_hash=prev_hash,
        )
        await self.session.commit()
        logger.info(
            "audit_log: id=%d actor=%s action=%s target=%s",
            log.id,
            actor,
            action,
            target,
        )
        return self._to_dict(log)

    async def verify_chain(self, from_log_id: int = 1) -> dict[str, Any]:
        """验证从 from_log_id 开始的链完整性。

        返回:
            - valid: bool
            - checked: int
            - broken_at: int | None(首个校验失败的 ID)
        """
        logs = await self.repo.get_chain_from(from_log_id)
        prev_hash = logs[0].prev_hash if logs else ""
        for log in logs:
            expected = compute_hash(
                log_id=log.id,
                actor=log.actor,
                action=log.action,
                target=log.target,
                created_at=log.created_at,
                prev_hash=prev_hash,
            )
            if not hmac.compare_digest(expected, log.curr_hash):
                logger.warning(
                    "audit_chain_broken: log_id=%d expected=%s actual=%s",
                    log.id,
                    expected,
                    log.curr_hash,
                )
                return {"valid": False, "checked": log.id - from_log_id, "broken_at": log.id}
            prev_hash = log.curr_hash
        return {
            "valid": True,
            "checked": len(logs),
            "broken_at": None,
        }

    async def list_recent(
        self,
        limit: int = 100,
        offset: int = 0,
        actor: str | None = None,
        action: str | None = None,
    ) -> list[dict[str, Any]]:
        logs = await self.repo.list_recent(
            limit=limit, offset=offset, actor=actor, action=action
        )
        return [self._to_dict(l) for l in logs]

    def _to_dict(self, log: AuditLogORM) -> dict[str, Any]:
        return {
            "id": log.id,
            "actor": log.actor,
            "action": log.action,
            "target": log.target,
            "ip": log.ip,
            "user_agent": log.user_agent,
            "metadata": log.metadata_ or {},
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "prev_hash": log.prev_hash,
            "curr_hash": log.curr_hash,
        }
