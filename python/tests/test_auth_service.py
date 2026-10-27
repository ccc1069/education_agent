"""AuthService 单元测试: 直接调用服务层,覆盖 register/login/refresh/logout 业务逻辑。"""

import pytest

from auth.jwt import create_refresh_token
from db.models import UserRole
from services import AuthService


@pytest.mark.asyncio
async def test_register_student_returns_user_id_and_learner_id(db_session):
    svc = AuthService(db_session)
    user_id, learner_public_id = await svc.register_student(
        "svc@example.com", "StrongPass123!", "Test"
    )
    assert user_id > 0
    assert learner_public_id


@pytest.mark.asyncio
async def test_register_student_rejects_duplicate_email(db_session):
    svc = AuthService(db_session)
    await svc.register_student("dup@example.com", "StrongPass123!", "Test")
    with pytest.raises(ValueError, match="该邮箱已注册"):
        await svc.register_student("dup@example.com", "StrongPass123!", "Other")


@pytest.mark.asyncio
async def test_register_student_rejects_short_password(db_session):
    svc = AuthService(db_session)
    with pytest.raises(ValueError, match="密码至少"):
        await svc.register_student("short@example.com", "abc", "Test")


@pytest.mark.asyncio
async def test_register_staff_creates_admin(db_session):
    svc = AuthService(db_session)
    user_id = await svc.register_staff(
        "admin@example.com", "StrongPass123!", UserRole.ADMIN, "Admin"
    )
    assert user_id > 0


@pytest.mark.asyncio
async def test_register_staff_rejects_student_role(db_session):
    svc = AuthService(db_session)
    with pytest.raises(ValueError, match="student"):
        await svc.register_staff(
            "stu@example.com", "StrongPass123!", UserRole.STUDENT, "Bad"
        )


@pytest.mark.asyncio
async def test_login_success_returns_tokens(db_session):
    svc = AuthService(db_session)
    await svc.register_student("login@example.com", "StrongPass123!", "Test")
    result = await svc.login("login@example.com", "StrongPass123!")
    assert result["access_token"]
    assert result["refresh_token"]
    assert result["user"]["email"] == "login@example.com"


@pytest.mark.asyncio
async def test_login_unknown_email_raises(db_session):
    svc = AuthService(db_session)
    with pytest.raises(ValueError, match="邮箱或密码错误"):
        await svc.login("nobody@example.com", "AnyPass123!")


@pytest.mark.asyncio
async def test_login_wrong_password_raises(db_session):
    svc = AuthService(db_session)
    await svc.register_student("wrong@example.com", "StrongPass123!", "Test")
    with pytest.raises(ValueError, match="邮箱或密码错误"):
        await svc.login("wrong@example.com", "WrongPass123!")


@pytest.mark.asyncio
async def test_refresh_rotates_token(db_session):
    svc = AuthService(db_session)
    await svc.register_student("refresh@example.com", "StrongPass123!", "Test")
    login_result = await svc.login("refresh@example.com", "StrongPass123!")
    old_refresh = login_result["refresh_token"]

    new_tokens = await svc.refresh(old_refresh)
    assert new_tokens["access_token"] != login_result["access_token"]
    assert new_tokens["refresh_token"] != old_refresh

    # 旧 refresh token 应被撤销,无法再次使用
    with pytest.raises(ValueError, match="已撤销"):
        await svc.refresh(old_refresh)


@pytest.mark.asyncio
async def test_refresh_rejects_invalid_token(db_session):
    svc = AuthService(db_session)
    with pytest.raises(ValueError, match="无效的刷新令牌"):
        await svc.refresh("not-a-real-token")


@pytest.mark.asyncio
async def test_refresh_rejects_expired_token(db_session):
    """过期 refresh token 应被拒绝。"""
    from datetime import datetime, timedelta

    svc = AuthService(db_session)
    await svc.register_student("expired@example.com", "StrongPass123!", "Test")
    login_result = await svc.login("expired@example.com", "StrongPass123!")
    # 直接改 DB 记录把 expires_at 设为过去
    from repositories import RefreshTokenRepository

    token_repo = RefreshTokenRepository(db_session)
    record = await token_repo.get_by_token(login_result["refresh_token"])
    record.expires_at = datetime.utcnow() - timedelta(days=1)
    await db_session.flush()

    with pytest.raises(ValueError, match="已过期"):
        await svc.refresh(login_result["refresh_token"])


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(db_session):
    svc = AuthService(db_session)
    await svc.register_student("logout@example.com", "StrongPass123!", "Test")
    login_result = await svc.login("logout@example.com", "StrongPass123!")
    refresh = login_result["refresh_token"]

    await svc.logout(refresh)

    with pytest.raises(ValueError, match="已撤销"):
        await svc.refresh(refresh)
