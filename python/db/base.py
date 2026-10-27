"""SQLAlchemy 异步引擎 + Base 声明类 + Session 工厂。"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config.settings import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    pass


def _build_engine() -> AsyncEngine:
    """根据 driver 选择合适的 pool 参数。

    SQLite(测试用)不支持 pool_size/max_overflow,需要 StaticPool。
    PostgreSQL(asyncpg)使用 QueuePool + 连接池参数。
    """
    url = settings.database_url
    is_sqlite = url.startswith("sqlite")

    if is_sqlite:
        # SQLite: 用 StaticPool 让 :memory: 跨连接共享
        from sqlalchemy.pool import StaticPool

        return create_async_engine(
            url,
            echo=settings.db_echo,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )

    return create_async_engine(
        url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,
        future=True,
    )


async_engine: AsyncEngine = _build_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    autoflush=False,
    class_=AsyncSession,
)


async def init_db() -> None:
    """应用启动时调用:验证连接 + 日志。"""
    try:
        async with async_engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("Database connection established: %s", settings.database_url)
    except Exception as e:
        logger.error("Database connection failed: %s", e)
        raise


async def close_db() -> None:
    """应用关闭时调用:释放连接池。"""
    await async_engine.dispose()
    logger.info("Database connection pool disposed")


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """获取异步 Session 的上下文管理器(用于非 FastAPI 场景,如脚本、Worker)。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
