"""用户仓储: 用户 CRUD + refresh token 管理。"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import hash_token
from db.models import LearnerORM, RefreshTokenORM, UserORM, UserRole
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository[UserORM]):
    """用户仓储。"""

    model = UserORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_email(self, email: str) -> UserORM | None:
        result = await self.session.execute(select(UserORM).where(UserORM.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> UserORM | None:
        result = await self.session.execute(select(UserORM).where(UserORM.id == user_id))
        return result.scalar_one_or_none()

    async def create_student(
        self, email: str, password_hash: str, name: str = ""
    ) -> tuple[UserORM, LearnerORM]:
        """创建学生用户 + 关联的 Learner。返回 (user, learner)。"""
        import uuid

        learner = LearnerORM(public_id=str(uuid.uuid4()), name=name or email.split("@")[0])
        self.session.add(learner)
        await self.session.flush()

        user = UserORM(
            email=email,
            password_hash=password_hash,
            role=UserRole.STUDENT,
            is_active=True,
            is_verified=False,
            learner_id=learner.id,
        )
        self.session.add(user)
        await self.session.flush()
        return user, learner

    async def create_staff(
        self, email: str, password_hash: str, role: UserRole, name: str = ""
    ) -> UserORM:
        """创建教师/管理员(不绑定 learner)。"""
        if role == UserRole.STUDENT:
            raise ValueError("Use create_student for student accounts")
        user = UserORM(
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=True,
            is_verified=False,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_last_login(self, user_id: int, success: bool) -> None:
        """更新最后登录时间 + 失败计数。"""
        if success:
            await self.session.execute(
                update(UserORM)
                .where(UserORM.id == user_id)
                .values(last_login_at=datetime.utcnow(), failed_login_count=0)
            )
        else:
            await self.session.execute(
                update(UserORM)
                .where(UserORM.id == user_id)
                .values(failed_login_count=UserORM.failed_login_count + 1)
            )
        await self.session.flush()


class RefreshTokenRepository(BaseRepository[RefreshTokenORM]):
    """Refresh token 仓储: 存哈希,支持撤销。"""

    model = RefreshTokenORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self, user_id: int, token: str, expires_at: datetime
    ) -> RefreshTokenORM:
        record = RefreshTokenORM(
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=expires_at,
            revoked=False,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_token(self, token: str) -> RefreshTokenORM | None:
        token_hash = hash_token(token)
        result = await self.session.execute(
            select(RefreshTokenORM).where(RefreshTokenORM.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke(self, token: str) -> bool:
        record = await self.get_by_token(token)
        if record is None or record.revoked:
            return False
        record.revoked = True
        await self.session.flush()
        return True

    async def revoke_all_for_user(self, user_id: int) -> int:
        """撤销某用户所有 refresh token(强制下线)。"""
        result = await self.session.execute(
            update(RefreshTokenORM)
            .where(RefreshTokenORM.user_id == user_id, RefreshTokenORM.revoked == False)
            .values(revoked=True)
        )
        return result.rowcount or 0

    async def purge_expired(self, before: datetime) -> int:
        """清理过期 token。"""
        result = await self.session.execute(
            select(RefreshTokenORM).where(RefreshTokenORM.expires_at < before)
        )
        count = 0
        for rec in result.scalars().all():
            await self.session.delete(rec)
            count += 1
        return count
