"""认证服务: 注册、登录、刷新、登出 业务逻辑。"""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
)
from auth.password import hash_password, verify_password
from db.models import UserRole
from repositories import LearnerRepository, RefreshTokenRepository, UserRepository

logger = logging.getLogger(__name__)


class AuthService:
    """认证服务: 封装用户登录、注册、token 刷新的完整流程。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.token_repo = RefreshTokenRepository(session)
        self.learner_repo = LearnerRepository(session)

    async def _learner_public_id(self, learner_id: int | None) -> str | None:
        """对外暴露 learner public_id(WS / 前端用),不用内部自增 id。"""
        if learner_id is None:
            return None
        learner = await self.learner_repo.get_by_id(learner_id)
        return learner.public_id if learner else None

    async def register_student(
        self, email: str, password: str, name: str = ""
    ) -> tuple[int, str]:
        """学生注册。返回 (user_id, learner_public_id)。"""
        if await self.user_repo.get_by_email(email):
            raise ValueError("该邮箱已注册")
        if len(password) < 8:
            raise ValueError("密码至少 8 位")

        password_hash = hash_password(password)
        user, learner = await self.user_repo.create_student(email, password_hash, name)
        await self.session.commit()
        logger.info("Student registered: id=%d email=%s", user.id, email)
        return user.id, learner.public_id

    async def register_staff(
        self, email: str, password: str, role: UserRole, name: str = ""
    ) -> int:
        """教师/管理员注册(仅管理员可调用,在路由层校验)。"""
        if await self.user_repo.get_by_email(email):
            raise ValueError("该邮箱已注册")
        if len(password) < 8:
            raise ValueError("密码至少 8 位")

        password_hash = hash_password(password)
        user = await self.user_repo.create_staff(email, password_hash, role, name)
        await self.session.commit()
        logger.info("Staff registered: id=%d email=%s role=%s", user.id, email, role.value)
        return user.id

    async def login(self, email: str, password: str) -> dict:
        """登录: 返回 access_token + refresh_token + 用户信息。"""
        user = await self.user_repo.get_by_email(email)
        if user is None:
            # 故意不告诉用户"邮箱不存在",防枚举
            logger.info("Login failed: unknown email %s", email)
            raise ValueError("邮箱或密码错误")

        if not verify_password(password, user.password_hash):
            await self.user_repo.update_last_login(user.id, success=False)
            await self.session.commit()
            logger.info("Login failed: bad password for %s", email)
            raise ValueError("邮箱或密码错误")

        if not user.is_active:
            raise ValueError("账号已停用")

        # 生成 tokens
        access_token = create_access_token(user.id, user.email, user.role.value)
        refresh_token, _, expires_at = create_refresh_token(user.id, user.email)
        await self.token_repo.create(user.id, refresh_token, expires_at)
        await self.user_repo.update_last_login(user.id, success=True)
        await self.session.commit()

        logger.info("Login success: id=%d email=%s", user.id, email)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in_seconds": 1800,
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role.value,
                "learner_id": await self._learner_public_id(user.learner_id),
            },
        }

    async def refresh(self, refresh_token: str) -> dict:
        """用 refresh token 换新的 access token。"""
        record = await self.token_repo.get_by_token(refresh_token)
        if record is None:
            raise ValueError("无效的刷新令牌")
        if record.revoked:
            raise ValueError("刷新令牌已撤销")
        if record.expires_at < datetime.utcnow():
            raise ValueError("刷新令牌已过期")

        user = await self.user_repo.get_by_id(record.user_id)
        if user is None or not user.is_active:
            raise ValueError("用户不存在或已停用")

        # 旋转 refresh token(单次使用,防重放)
        await self.token_repo.revoke(refresh_token)
        new_access = create_access_token(user.id, user.email, user.role.value)
        new_refresh, _, expires_at = create_refresh_token(user.id, user.email)
        await self.token_repo.create(user.id, new_refresh, expires_at)
        await self.session.commit()

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
        }

    async def logout(self, refresh_token: str) -> None:
        """登出: 撤销 refresh token(access token 短期自然过期)。"""
        await self.token_repo.revoke(refresh_token)
        await self.session.commit()
