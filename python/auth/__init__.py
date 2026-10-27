"""认证授权模块: JWT + RBAC + bcrypt。"""

from auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_token,
    TokenData,
)
from auth.password import hash_password, verify_password
from auth.dependencies import (
    get_current_user,
    get_current_active_user,
    require_role,
    require_student,
    CurrentUser,
)

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "hash_token",
    "TokenData",
    "hash_password",
    "verify_password",
    "get_current_user",
    "get_current_active_user",
    "require_role",
    "require_student",
    "CurrentUser",
]
