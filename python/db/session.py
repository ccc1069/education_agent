"""FastAPI 依赖: 注入 AsyncSession。"""

from typing import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import AsyncSessionLocal


async def get_session_dep() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖: 每个请求一个 session,提交或回滚。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# 便于在路由中显式声明依赖
SessionDep = Depends(get_session_dep)
