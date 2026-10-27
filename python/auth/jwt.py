"""JWT 工具: 签发 + 校验 + refresh token 哈希。"""

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pydantic import BaseModel

from config.settings import settings

logger = logging.getLogger(__name__)

# JWT 载荷 key
SUBJECT_KEY = "sub"
ROLE_KEY = "role"
TYPE_KEY = "type"
EXP_KEY = "exp"
IAT_KEY = "iat"
JTI_KEY = "jti"  # JWT ID, 用于撤销

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


class TokenData(BaseModel):
    """解码后的 token 数据。"""

    user_id: int
    email: str
    role: str
    token_type: str
    jti: str
    expires_at: datetime


def create_access_token(
    user_id: int, email: str, role: str, expires_in_minutes: int | None = None
) -> str:
    """签发 access token。"""
    minutes = expires_in_minutes or settings.jwt_access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        SUBJECT_KEY: str(user_id),
        "email": email,
        ROLE_KEY: role,
        TYPE_KEY: ACCESS_TOKEN_TYPE,
        IAT_KEY: int(now.timestamp()),
        EXP_KEY: int((now + timedelta(minutes=minutes)).timestamp()),
        JTI_KEY: str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: int, email: str) -> tuple[str, str, datetime]:
    """签发 refresh token。返回 (token, token_hash, expires_at)。"""
    days = settings.jwt_refresh_token_expire_days
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=days)
    payload: dict[str, Any] = {
        SUBJECT_KEY: str(user_id),
        "email": email,
        TYPE_KEY: REFRESH_TOKEN_TYPE,
        IAT_KEY: int(now.timestamp()),
        EXP_KEY: int(expires_at.timestamp()),
        JTI_KEY: str(uuid.uuid4()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, hash_token(token), expires_at


def decode_access_token(token: str) -> TokenData | None:
    """解码 + 校验 access token。失败返回 None。"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": [EXP_KEY, SUBJECT_KEY, TYPE_KEY]},
        )
    except jwt.ExpiredSignatureError:
        logger.info("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token: %s", e)
        return None

    if payload.get(TYPE_KEY) != ACCESS_TOKEN_TYPE:
        logger.warning("Wrong token type: %s", payload.get(TYPE_KEY))
        return None

    try:
        return TokenData(
            user_id=int(payload[SUBJECT_KEY]),
            email=payload.get("email", ""),
            role=payload.get(ROLE_KEY, "student"),
            token_type=ACCESS_TOKEN_TYPE,
            jti=payload.get(JTI_KEY, ""),
            expires_at=datetime.fromtimestamp(payload[EXP_KEY], tz=timezone.utc),
        )
    except (KeyError, ValueError, TypeError) as e:
        logger.warning("Token payload invalid: %s", e)
        return None


def hash_token(token: str) -> str:
    """对 refresh token 做 SHA-256,存 DB 防止明文泄露。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
