"""认证模块测试: JWT + password + dependencies。"""

import time

import pytest

from auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_token,
)
from auth.password import hash_password, verify_password


# ---------- password ----------


def test_password_hash_is_unique():
    """同密码两次 hash 结果应不同(salt)。"""
    h1 = hash_password("mypassword")
    h2 = hash_password("mypassword")
    assert h1 != h2


def test_password_verify_correct():
    h = hash_password("mypassword")
    assert verify_password("mypassword", h) is True


def test_password_verify_wrong():
    h = hash_password("mypassword")
    assert verify_password("wrongpassword", h) is False


def test_password_verify_empty():
    h = hash_password("mypassword")
    assert verify_password("", h) is False


# ---------- JWT access token ----------


def test_access_token_roundtrip():
    token = create_access_token(user_id=42, email="u@example.com", role="student")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload.user_id == 42
    assert payload.email == "u@example.com"
    assert payload.role == "student"
    assert payload.token_type == "access"


def test_access_token_expired():
    """构造一个过期的 token(把 exp 设为过去时间)。"""
    import jwt as pyjwt
    from config.settings import settings

    expired_payload = {
        "sub": "1",
        "email": "x@example.com",
        "role": "student",
        "type": "access",
        "exp": int(time.time()) - 10,
        "iat": int(time.time()) - 100,
        "jti": "test-jti",
    }
    token = pyjwt.encode(
        expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    assert decode_access_token(token) is None


def test_access_token_invalid_signature():
    """篡改的 token 应被拒绝。"""
    token = create_access_token(
        user_id=1, email="u@example.com", role="student"
    )
    tampered = token[:-5] + "XXXXX"
    assert decode_access_token(tampered) is None


def test_access_token_wrong_secret():
    """用另一个 secret 签的 token 应被拒绝。"""
    import jwt as pyjwt
    from config.settings import settings

    fake_token = pyjwt.encode(
        {
            "sub": "1",
            "email": "x@example.com",
            "role": "student",
            "type": "access",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "jti": "test-jti",
        },
        "wrong-secret",
        algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(fake_token) is None  # type: ignore[arg-type]


def test_access_token_rejects_refresh_token():
    """access 校验器应拒绝 refresh 类型的 token。"""
    refresh_token, _, _ = create_refresh_token(user_id=1, email="u@example.com")
    assert decode_access_token(refresh_token) is None


# ---------- refresh token ----------


def test_refresh_token_hashable():
    """refresh token 应可被 hash(用于 DB 比对)。"""
    rt, rt_hash, expires_at = create_refresh_token(user_id=1, email="u@example.com")
    assert rt_hash != rt  # 不能存原文
    assert hash_token(rt) == rt_hash  # 同 token 同 hash
    assert expires_at is not None


def test_refresh_token_different_each_call():
    rt1, _, _ = create_refresh_token(user_id=1, email="u@example.com")
    rt2, _, _ = create_refresh_token(user_id=1, email="u@example.com")
    assert rt1 != rt2  # 随机性
