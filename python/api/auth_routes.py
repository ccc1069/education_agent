"""认证路由: 注册、登录、刷新、登出、获取当前用户。"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit_helpers import write_audit
from auth import get_current_active_user, CurrentUser
from config.settings import settings
from core.rate_limiter import rate_limit
from db.session import get_session_dep as get_session
from db.models import UserRole
from repositories import RefreshTokenRepository, UserRepository
from services import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------- Pydantic 模型 ----------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=128)


class RegisterStaffRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    name: str = Field(default="", max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: dict


class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    learner_id: str | None  # learner public_id,供 WS / 前端使用


# ---------- 路由 ----------


@router.post(
    "/register",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit(settings.rate_limit_register_per_min, 60))],
)
async def register(
    req: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """学生注册(公开端点)。"""
    service = AuthService(session)
    try:
        user_id, learner_public_id = await service.register_student(
            req.email, req.password, req.name
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await write_audit(
        session,
        actor=req.email,
        action="auth.register",
        target=f"user:{user_id}",
        request=request,
        metadata={"learner_id": learner_public_id, "role": "student"},
    )
    return {
        "user_id": user_id,
        "learner_id": learner_public_id,
        "message": "Registration successful. Please login.",
    }


@router.post(
    "/register/staff",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def register_staff(
    req: RegisterStaffRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session),
):
    """教师/管理员注册(仅管理员可调用)。"""
    if current.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员可注册教职工账号",
        )
    service = AuthService(session)
    try:
        user_id = await service.register_staff(req.email, req.password, req.role, req.name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await write_audit(
        session,
        actor=current.email,
        action="auth.register_staff",
        target=f"user:{user_id}",
        request=request,
        metadata={"email": req.email, "role": req.role.value},
    )
    return {"user_id": user_id, "message": "Staff registered"}


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit(settings.rate_limit_login_per_min, 60))],
)
async def login(
    req: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """登录(公开端点)。返回 access + refresh token。"""
    service = AuthService(session)
    try:
        result = await service.login(req.email, req.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    user = result.get("user") or {}
    await write_audit(
        session,
        actor=req.email,
        action="auth.login",
        target=f"user:{user.get('id', req.email)}",
        request=request,
        metadata={"role": user.get("role")},
    )
    return result


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit(settings.rate_limit_refresh_per_min, 60))],
)
async def refresh_token(req: RefreshRequest, session: AsyncSession = Depends(get_session)):
    """用 refresh token 换新 token。"""
    service = AuthService(session)
    try:
        result = await service.refresh(req.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    # 补全 user 信息
    from auth.jwt import decode_access_token
    token_data = decode_access_token(result["access_token"])
    if token_data is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(token_data.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    result["user"] = {
        "id": user.id,
        "email": user.email,
        "role": user.role.value,
        "learner_id": await service._learner_public_id(user.learner_id),
    }
    return result


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    req: LogoutRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """登出: 撤销 refresh token。"""
    token_repo = RefreshTokenRepository(session)
    user_repo = UserRepository(session)
    record = await token_repo.get_by_token(req.refresh_token)
    actor = "anonymous"
    target = "user:unknown"
    if record is not None:
        user = await user_repo.get_by_id(record.user_id)
        if user is not None:
            actor = user.email
            target = f"user:{user.id}"
    service = AuthService(session)
    await service.logout(req.refresh_token)
    await write_audit(
        session,
        actor=actor,
        action="auth.logout",
        target=target,
        request=request,
    )
    return None


@router.get("/me", response_model=UserResponse)
async def get_me(current: CurrentUser = Depends(get_current_active_user)):
    """获取当前登录用户信息。"""
    return UserResponse(
        id=current.id,
        email=current.email,
        role=current.role.value,
        learner_id=current.learner_public_id,
    )
