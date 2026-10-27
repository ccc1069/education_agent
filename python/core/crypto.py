"""字段级 PII 加密(AES-256-GCM)。

设计:
- 主密钥从环境变量 PII_ENCRYPTION_KEY 加载(Base64 编码 32 字节)
- 每条字段独立 IV(12 字节随机),密文格式: base64(iv || ciphertext || tag)
- GCM 模式自带完整性校验,无需额外 HMAC
- 密钥未配置时,dev 环境自动生成临时密钥(并 WARN),prod 拒绝启动
"""

from __future__ import annotations

import base64
import logging
import os
import secrets
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_IV_LEN = 12  # GCM 推荐 96-bit IV
_KEY_LEN = 32  # AES-256


class CryptoError(Exception):
    """加密/解密失败。"""


def _load_master_key() -> bytes:
    """加载主密钥。

    优先级:
    1. 环境变量 PII_ENCRYPTION_KEY (Base64 编码 32 字节)
    2. dev/test 环境: 生成临时密钥(并 WARN,不应在生产使用)
    3. prod 环境: 拒绝启动
    """
    raw = os.environ.get("PII_ENCRYPTION_KEY", "").strip()
    if raw:
        try:
            key = base64.b64decode(raw, validate=True)
        except Exception as e:
            raise CryptoError("PII_ENCRYPTION_KEY 不是合法 Base64") from e
        if len(key) != _KEY_LEN:
            raise CryptoError(
                f"PII_ENCRYPTION_KEY 长度应为 {_KEY_LEN} 字节, 实际 {len(key)}"
            )
        return key

    env = os.environ.get("ENV", "dev").lower()
    if env in ("prod", "production"):
        raise CryptoError("生产环境必须配置 PII_ENCRYPTION_KEY")

    # dev/test: 生成临时密钥(进程退出即失效,加密数据无法跨进程解密)
    key = secrets.token_bytes(_KEY_LEN)
    logger.warning(
        "PII_ENCRYPTION_KEY 未配置,使用临时密钥(env=%s)。"
        "切勿在生产环境如此操作",
        env,
    )
    return key


_MASTER_KEY: bytes | None = None


def _get_master_key() -> bytes:
    """单例加载主密钥(避免每次加解密都读环境变量)。"""
    global _MASTER_KEY
    if _MASTER_KEY is None:
        _MASTER_KEY = _load_master_key()
    return _MASTER_KEY


def encrypt_field(plaintext: str | None) -> str | None:
    """加密字符串字段。

    返回: base64(iv || ciphertext || tag)
    None 输入返回 None(不加密)
    """
    if plaintext is None:
        return None
    if not isinstance(plaintext, str):
        raise CryptoError(f"encrypt_field 仅支持 str, 收到 {type(plaintext).__name__}")
    key = _get_master_key()
    iv = secrets.token_bytes(_IV_LEN)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(iv, plaintext.encode("utf-8"), associated_data=None)
    return base64.b64encode(iv + ct).decode("ascii")


def decrypt_field(ciphertext: str | None) -> str | None:
    """解密字符串字段。

    输入: base64(iv || ciphertext || tag)
    返回: 原文; None 输入返回 None
    """
    if ciphertext is None:
        return None
    if not isinstance(ciphertext, str):
        raise CryptoError(f"decrypt_field 仅支持 str, 收到 {type(ciphertext).__name__}")
    try:
        raw = base64.b64decode(ciphertext, validate=True)
    except Exception as e:
        raise CryptoError("密文不是合法 Base64") from e
    if len(raw) < _IV_LEN + 16:  # iv + 至少 1 字节 ct + 16 字节 tag
        raise CryptoError("密文长度不足")
    key = _get_master_key()
    iv, ct = raw[:_IV_LEN], raw[_IV_LEN:]
    aesgcm = AESGCM(key)
    try:
        pt = aesgcm.decrypt(iv, ct, associated_data=None)
    except Exception as e:
        raise CryptoError("解密失败(密钥错误或密文被篡改)") from e
    return pt.decode("utf-8")


def encrypt_dict(fields: dict[str, Any], field_names: set[str]) -> dict[str, Any]:
    """对字典中指定字段做加密,返回新字典(immutable)。"""
    result = dict(fields)
    for name in field_names:
        if name in result and result[name] is not None:
            result[name] = encrypt_field(str(result[name]))
    return result


def decrypt_dict(fields: dict[str, Any], field_names: set[str]) -> dict[str, Any]:
    """对字典中指定字段做解密,返回新字典(immutable)。"""
    result = dict(fields)
    for name in field_names:
        if name in result and result[name] is not None:
            try:
                result[name] = decrypt_field(result[name])
            except CryptoError:
                # 解密失败保留原值(可能是未加密的旧数据)
                logger.warning("decrypt_dict: 字段 %s 解密失败,保留原值", name)
    return result
