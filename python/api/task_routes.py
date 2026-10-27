"""任务调度管理 API: 仅管理员。

- GET /api/v1/admin/tasks: 列出已注册任务 + 调度器状态
- GET /api/v1/admin/tasks/history: 任务执行历史
- POST /api/v1/admin/tasks/trigger/{name}: 手动触发某任务
- POST /api/v1/admin/tasks/{name}/run: 同步执行某任务并返回结果
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, get_current_active_user
from db.models import UserRole
from db.session import get_session_dep
from repositories import TaskExecutionRepository
from tasks import TASK_REGISTRY, get_task_func, get_task_names

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/tasks", tags=["admin-tasks"])


# ---------- Pydantic 模型 ----------


class TaskInfo(BaseModel):
    name: str
    description: str
    category: str


class TaskListResponse(BaseModel):
    registered: list[dict[str, Any]]
    queue_stats: dict[str, Any]


class TaskExecutionInfo(BaseModel):
    id: int
    task_name: str
    status: str
    started_at: str | None
    completed_at: str | None
    duration_ms: int
    error_message: str | None
    metadata: dict[str, Any]
    triggered_by: str


class TriggerResponse(BaseModel):
    task_name: str
    status: str
    result: dict[str, Any] | None
    error: str | None


# ---------- 权限 ----------


def _require_admin(current: CurrentUser) -> None:
    if current.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员可管理任务",
        )


# ---------- 路由 ----------


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    current: CurrentUser = Depends(get_current_active_user),
):
    """列出已注册任务 + 队列状态(管理员)。"""
    _require_admin(current)
    from core.scheduler import get_scheduler
    from core.task_queue import get_task_queue

    scheduler = get_scheduler()
    queue = get_task_queue()

    registered = [
        {
            "name": name,
            "description": info["description"],
            "category": info["category"],
        }
        for name, info in TASK_REGISTRY.items()
    ]
    # 加上调度器中已注册的 cron/interval 信息
    scheduled = scheduler.list_tasks()
    scheduled_map = {t["name"]: t for t in scheduled}
    for r in registered:
        if r["name"] in scheduled_map:
            r["schedule"] = scheduled_map[r["name"]]

    return {
        "registered": registered,
        "queue_stats": queue.stats,
    }


@router.get("/history", response_model=list[TaskExecutionInfo])
async def list_task_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    task_name: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """查询任务执行历史(管理员)。"""
    _require_admin(current)
    repo = TaskExecutionRepository(session)
    rows = await repo.list_recent(
        limit=limit,
        offset=offset,
        task_name=task_name,
        status=status_filter,
    )
    return [await repo.to_dict(r) for r in rows]


@router.post("/trigger/{task_name}", response_model=TriggerResponse)
async def trigger_task(
    task_name: str,
    current: CurrentUser = Depends(get_current_active_user),
):
    """手动触发任务: 立即执行并写入执行历史(演示闭环)。

    四个内置任务均为短耗时,同步跑完再返回,保证历史页立刻可见。
    """
    _require_admin(current)
    if task_name not in TASK_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_name}' not registered. Available: {get_task_names()}",
        )
    from core.scheduler import get_scheduler, set_scheduler_session_factory
    from db.base import AsyncSessionLocal

    # 确保 lifespan 重置后仍有 session 工厂(写执行历史)
    set_scheduler_session_factory(AsyncSessionLocal)
    func = get_task_func(task_name)
    scheduler = get_scheduler()
    try:
        outcome = await scheduler.trigger_now(
            task_name,
            func,
            triggered_by=f"manual:{current.email}",
        )
    except Exception as e:
        logger.exception("task_trigger_failed: %s", task_name)
        return {
            "task_name": task_name,
            "status": "failed",
            "result": None,
            "error": str(e),
        }
    return {
        "task_name": task_name,
        "status": outcome.get("status", "success"),
        "result": outcome.get("result"),
        "error": outcome.get("error"),
    }


@router.post("/{task_name}/run", response_model=TriggerResponse)
async def run_task_sync(
    task_name: str,
    current: CurrentUser = Depends(get_current_active_user),
):
    """同步执行任务并返回结果(适合短耗时任务,如统计)。

    会阻塞直到任务完成。
    """
    _require_admin(current)
    if task_name not in TASK_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_name}' not registered. Available: {get_task_names()}",
        )
    # 延迟导入: 让测试 fixture 替换 db.base.AsyncSessionLocal 后能取到最新引用
    from db.base import AsyncSessionLocal as _session_factory

    func = get_task_func(task_name)
    try:
        result = await func(_session_factory)
    except Exception as e:
        logger.exception("task_run_failed: %s", task_name)
        return {
            "task_name": task_name,
            "status": "failed",
            "result": None,
            "error": str(e),
        }
    return {
        "task_name": task_name,
        "status": "success",
        "result": result,
        "error": None,
    }


@router.get("/queue/stats", response_model=dict)
async def get_queue_stats(
    current: CurrentUser = Depends(get_current_active_user),
):
    """获取任务队列实时统计(管理员)。"""
    _require_admin(current)
    from core.task_queue import get_task_queue

    return get_task_queue().stats


@router.get("/queue/dead-letters", response_model=list[dict])
async def get_dead_letters(
    current: CurrentUser = Depends(get_current_active_user),
):
    """获取死信队列(重试耗尽的任务,管理员)。"""
    _require_admin(current)
    from core.task_queue import get_task_queue

    queue = get_task_queue()
    return [
        {
            "task_name": dl.task.name,
            "last_error": dl.last_error,
            "failed_at": dl.failed_at,
            "triggered_by": dl.task.triggered_by,
        }
        for dl in queue.dead_letters
    ]
