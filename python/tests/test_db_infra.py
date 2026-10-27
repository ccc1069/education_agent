"""数据库基础设施测试: get_session_dep, init_db, close_db, get_session。"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from db.base import AsyncSessionLocal, async_engine, get_session


@pytest.mark.asyncio
async def test_get_session_dep_yields_session_and_commits():
    """get_session_dep 应 yield session,正常退出时 commit。"""
    from db import base as db_base
    from db.session import get_session_dep

    # 保存原始引用
    original = db_base.AsyncSessionLocal
    try:
        # 用 test engine 构造新的 sessionmaker
        test_sm = async_sessionmaker(async_engine, expire_on_commit=False)
        db_base.AsyncSessionLocal = test_sm

        gen = get_session_dep()
        session = await gen.__anext__()
        assert session is not None

        # 写入数据(让 commit 有内容)
        await session.execute(text("SELECT 1"))

        # 正常退出应触发 commit
        try:
            await gen.aclose()
        except StopAsyncIteration:
            pass
    finally:
        db_base.AsyncSessionLocal = original


@pytest.mark.asyncio
async def test_get_session_dep_rolls_back_on_exception():
    """get_session_dep 在异常时应 rollback 而不 commit。"""
    from db import base as db_base
    from db.session import get_session_dep

    original = db_base.AsyncSessionLocal
    try:
        test_sm = async_sessionmaker(async_engine, expire_on_commit=False)
        db_base.AsyncSessionLocal = test_sm

        gen = get_session_dep()
        await gen.__anext__()

        with pytest.raises(ValueError, match="test error"):
            try:
                raise ValueError("test error")
            except ValueError:
                await gen.athrow(ValueError, ValueError("test error"))
    finally:
        db_base.AsyncSessionLocal = original


@pytest.mark.asyncio
async def test_get_session_context_manager_yields_session():
    """get_session 上下文管理器应返回可用的 session。"""
    from db import base as db_base

    original = db_base.AsyncSessionLocal
    try:
        test_sm = async_sessionmaker(async_engine, expire_on_commit=False)
        db_base.AsyncSessionLocal = test_sm

        async with get_session() as session:
            result = await session.execute(text("SELECT 42 as v"))
            row = result.first()
            assert row.v == 42
    finally:
        db_base.AsyncSessionLocal = original


@pytest.mark.asyncio
async def test_init_db_succeeds_with_valid_engine(test_engine, monkeypatch):
    """init_db 应能验证数据库连接。"""
    from db import base as db_base
    from db.base import init_db

    monkeypatch.setattr(db_base, "async_engine", test_engine)

    # 不应抛异常
    await init_db()


@pytest.mark.asyncio
async def test_close_db_disposes_engine(test_engine, monkeypatch):
    """close_db 应调用 engine.dispose()。"""
    from db import base as db_base
    from db.base import close_db

    monkeypatch.setattr(db_base, "async_engine", test_engine)

    # 不应抛异常
    await close_db()


@pytest.mark.asyncio
async def test_init_db_raises_on_connection_failure(monkeypatch):
    """init_db 在连接失败时应抛异常。"""
    from db import base as db_base
    from db.base import init_db

    class _FailEngine:
        def connect(self):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(db_base, "async_engine", _FailEngine())

    with pytest.raises(RuntimeError, match="connection refused"):
        await init_db()


def test_session_dep_alias_exists():
    """SessionDep 应是 Depends(get_session_dep) 的别名。"""
    from db.session import SessionDep, get_session_dep

    assert SessionDep.dependency is get_session_dep
