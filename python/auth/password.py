"""密码哈希: bcrypt(防彩虹表 + 自适应 cost)。"""

import logging

import bcrypt

logger = logging.getLogger(__name__)

# bcrypt cost factor: 12 是 2026 年推荐值(每次哈希约 250ms)
BCRYPT_COST = 12


def hash_password(plain: str) -> str:
    """生成 bcrypt 哈希。返回 utf-8 字符串以便存 DB。"""
    if not plain:
        raise ValueError("Password cannot be empty")
    salt = bcrypt.gensalt(rounds=BCRYPT_COST)
    hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码。常量时间比较,防时序攻击。"""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        logger.warning("Invalid password hash format")
        return False
