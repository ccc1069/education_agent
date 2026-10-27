"""FastAPI 依赖: 解析当前用户、检查角色。"""

import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import decode_access_token, TokenData
from db.session import get_session_dep
from db.models import LearnerORM, UserORM, UserRole

logger = logging.getLogger(__name__)

# Bearer scheme: 自动从 Authorization header 提取 token
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """请求上下文中的当前用户(轻量 dataclass,避免 ORM 实例泄漏到路由)。"""

    id: int
    email: str
    role: UserRole
    learner_id: int | None  # 内部 DB id
    learner_public_id: str | None  # 外部可见 ID(供 orchestrator 用)
    is_active: bool


async def _load_user_by_id(session: AsyncSession, user_id: int) -> UserORM | None:
    """跨租户加载用户(auth 不受 tenant filter 限制)。"""
    from core.tenant_context import reset_tenant_id, set_tenant_id

    token = set_tenant_id(None)
    try:
        result = await session.execute(select(UserORM).where(UserORM.id == user_id))
        return result.scalar_one_or_none()
    finally:
        reset_tenant_id(token)


async def _load_learner_public_id(
    session: AsyncSession, learner_id: int | None
) -> str | None:
    if learner_id is None:
        return None
    from core.tenant_context import reset_tenant_id, set_tenant_id

    token = set_tenant_id(None)
    try:
        result = await session.execute(
            select(LearnerORM).where(LearnerORM.id == learner_id)
        )
        learner = result.scalar_one_or_none()
        return learner.public_id if learner else None
    finally:
        reset_tenant_id(token)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session_dep),
) -> CurrentUser:
    """从 Authorization: Bearer <token> 解析当前用户。

    用法: 在路由上声明 current_user: CurrentUser = Depends(get_current_user)
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少或无效的 Authorization 头",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data: TokenData | None = decode_access_token(credentials.credentials)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await _load_user_by_id(session, token_data.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用"
        )
    learner_public_id = await _load_learner_public_id(session, user.learner_id)

    current = CurrentUser(
        id=user.id,
        email=user.email,
        role=user.role,
        learner_id=user.learner_id,
        learner_public_id=learner_public_id,
        is_active=user.is_active,
    )
    # 注入到 request.state 供后续中间件(审计、限流)使用
    request.state.current_user = current

    # 多租户上下文(P2#11):
    # - 非管理员: 强制 tenant_id = user.tenant_id(防 X-Tenant-ID 越权)
    # - 管理员: 保留 middleware 设置的 tenant_id(None=跨租户,值=act-as)
    from core.tenant_context import set_tenant_id
    from db.models import UserRole

    if user.role != UserRole.ADMIN:
        set_tenant_id(user.tenant_id)

    return current


async def get_current_active_user(
    current: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """已激活用户(冗余检查,get_current_user 已包含)。"""
    if not current.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号未激活")
    return current


def require_role(*allowed: UserRole):
    """工厂: 生成角色检查依赖。

    用法:
        @router.get("/admin/stats", dependencies=[Depends(require_role(UserRole.ADMIN))])
        async def admin_stats(...): ...
    """

    async def _check(current: CurrentUser = Depends(get_current_active_user)) -> CurrentUser:
        if current.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"角色「{current.role.value}」无权访问，需要: {[r.value for r in allowed]}",
            )
        return current

    return _check


def require_student() -> CurrentUser:
    """学习主链路依赖: 须绑定 learner 档案(学生默认有;演示教师/管理员也可绑定)。"""

    async def _check(
        current: CurrentUser = Depends(get_current_active_user),
    ) -> CurrentUser:
        if not current.learner_public_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要学习者档案才能访问此接口，请使用学生账号或先绑定 learner",
            )
        return current

    return _check


async def get_session_for_user(
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
) -> AsyncSession:
    """便捷依赖: 返回已绑定当前用户上下文的 session。"""
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
