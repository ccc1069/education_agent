"""pytest 共享 fixtures。

设计:
- 使用 SQLite in-memory + aiosqlite 做单元测试(无需外部 PostgreSQL)
- Mock LLM provider(避免真实 API 调用)
- FastAPI TestClient with dependency overrides
- 每个测试函数独立数据库 transaction(回滚,避免污染)
"""

from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# 必须在导入应用前设置: 强制 mock LLM + SQLite
os.environ.setdefault("ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-for-prod")
os.environ.setdefault("OPENAI_API_KEY", "")  # 空 -> factory 返回 Mock


@pytest.fixture(scope="session")
def event_loop():
    """session 级 event loop,避免 pytest-asyncio 重复创建。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """每个测试函数独立 SQLite engine(完全隔离)。"""
    from db.base import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """独立 DB session(每个测试一个新事务,结束回滚)。"""
    async_session = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_llm_provider():
    """返回 MockLLMProvider 实例(无外部调用)。"""
    from llm.mock_provider import MockLLMProvider

    return MockLLMProvider(model="mock-test")


@pytest.fixture
def event_bus():
    """空 EventBus。"""
    from core.event_bus import EventBus

    return EventBus()


@pytest.fixture
def learner_models():
    """空 learner_models 字典。"""
    return {}


@pytest_asyncio.fixture
async def app(test_engine):
    """FastAPI 应用实例(测试用,跳过真实 DB 初始化)。"""
    import db.base as db_base

    original_engine = db_base.async_engine
    original_session_local = db_base.AsyncSessionLocal

    db_base.async_engine = test_engine
    test_session_local = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    db_base.AsyncSessionLocal = test_session_local

    from api.main import app as fastapi_app
    from db.session import get_session_dep

    # 覆盖 FastAPI 依赖: 让所有用 Depends(get_session_dep) 的路由使用测试 session
    async def _override_session():
        async with test_session_local() as session:
            try:
                yield session
            finally:
                await session.rollback()

    fastapi_app.dependency_overrides[get_session_dep] = _override_session

    # 跳过 orchestrator.initialize()(避免 LLM/外部依赖)
    from api import orchestrator as orch_module

    original_init = orch_module.AgentOrchestrator.initialize

    async def _stub_initialize(self):
        # 测试用 init_db: 只验证 test_engine 连接
        from sqlalchemy import text

        async with test_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        # 给 orchestrator 一个最小可用的 knowledge_graph(空图谱)
        from core.knowledge_graph import KnowledgeGraph

        self.knowledge_graph = KnowledgeGraph()

    orch_module.AgentOrchestrator.initialize = _stub_initialize

    # 构造一个 orchestrator 实例并附加到 app.state(供路由读取)
    test_orch = orch_module.AgentOrchestrator()
    await test_orch.initialize()
    fastapi_app.state.orchestrator = test_orch

    # 重置任务队列 + 调度器单例(避免跨测试污染)
    from core import rate_limiter as rate_limiter_module
    from core import scheduler as scheduler_module
    from core import task_queue as task_queue_module
    from core import tenant_context as tenant_context_module
    from core import tenant_filter as tenant_filter_module

    rate_limiter_module.reset_rate_limiter_for_test()
    scheduler_module.reset_scheduler_for_test()
    task_queue_module.reset_task_queue_for_test()
    # 注入测试 session 工厂,保证手动触发能写执行历史
    scheduler_module.set_scheduler_session_factory(test_session_local)
    # 安装租户过滤(每个测试独立安装,便于清理)
    tenant_filter_module.install_tenant_filter()
    # 确保默认租户存在(供带 tenant_id=1 的 UserORM 引用)
    from db.models import TenantORM

    async with test_session_local() as session:
        result = await session.execute(select(TenantORM).where(TenantORM.id == 1))
        if result.scalar_one_or_none() is None:
            session.add(TenantORM(id=1, name="Default", slug="default", plan="enterprise"))
            await session.commit()

    yield fastapi_app

    # 还原
    db_base.async_engine = original_engine
    db_base.AsyncSessionLocal = original_session_local
    fastapi_app.dependency_overrides.clear()
    orch_module.AgentOrchestrator.initialize = original_init
    rate_limiter_module.reset_rate_limiter_for_test()
    scheduler_module.reset_scheduler_for_test()
    task_queue_module.reset_task_queue_for_test()
    tenant_filter_module.uninstall_tenant_filter()
    tenant_context_module.set_tenant_id(None)


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """HTTP 客户端(TestClient 的异步版本)。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(test_engine):
    """学生 JWT 头: 在测试 DB 插入学生用户后签 token。"""
    from auth.jwt import create_access_token
    from db.models import LearnerORM, UserORM, UserRole

    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        learner = LearnerORM(public_id="student-test-pubid", name="Student Test")
        session.add(learner)
        await session.flush()
        user = UserORM(
            email="student@test.local",
            password_hash="x",
            role=UserRole.STUDENT,
            learner_id=learner.id,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    token = create_access_token(
        user_id=user_id, email="student@test.local", role="student"
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_headers(test_engine):
    """管理员 JWT 头: 在测试 DB 插入管理员用户后签 token。"""
    from auth.jwt import create_access_token
    from db.models import UserORM, UserRole

    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        user = UserORM(
            email="admin@test.local",
            password_hash="x",
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    token = create_access_token(
        user_id=user_id, email="admin@test.local", role="admin"
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def teacher_headers(test_engine):
    """教师 JWT 头: 在测试 DB 插入教师用户后签 token。"""
    from auth.jwt import create_access_token
    from db.models import UserORM, UserRole

    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        user = UserORM(
            email="teacher@test.local",
            password_hash="x",
            role=UserRole.TEACHER,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    token = create_access_token(
        user_id=user_id, email="teacher@test.local", role="teacher"
    )
    return {"Authorization": f"Bearer {token}"}
