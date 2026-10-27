"""APScheduler 封装: 注册 cron/interval 任务,优雅启停。

设计:
- 单例 SchedulerService,在 FastAPI lifespan 中启动/停止
- 支持注册: cron 表达式任务 / 间隔任务 / 一次性延迟任务
- 任务执行历史持久化到 task_executions 表
- 与 TaskQueue 集成: 调度器只负责"到点入队",执行由 worker 池完成
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.task_queue import TaskFunc, get_task_queue
from db.models import TaskExecutionORM

logger = logging.getLogger(__name__)


class SchedulerService:
    """APScheduler 封装。"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self._session_factory = session_factory
        self._registered: dict[str, dict[str, Any]] = {}

    @property
    def scheduler(self) -> AsyncIOScheduler:
        return self._scheduler

    def register_cron(
        self,
        name: str,
        func: TaskFunc,
        cron_expr: str,
        max_retries: int = 3,
        coalesce: bool = True,
    ) -> None:
        """注册 cron 表达式任务。

        Args:
            name: 任务名(唯一,用于查询)
            func: 异步任务函数
            cron_expr: cron 表达式(分 时 日 月 周),如 "0 8 * * *" 每天 8 点
            max_retries: 入队后失败的重试次数
            coalesce: 错过多次执行是否只补一次
        """
        self._remove_existing(name)
        trigger = CronTrigger.from_crontab(cron_expr, timezone="Asia/Shanghai")
        self._scheduler.add_job(
            self._enqueue_with_history,
            trigger=trigger,
            id=name,
            args=[name, func, max_retries],
            replace_existing=True,
            coalesce=coalesce,
            max_instances=1,
        )
        self._registered[name] = {
            "type": "cron",
            "expr": cron_expr,
            "max_retries": max_retries,
        }
        logger.info("cron_task_registered: name=%s expr=%s", name, cron_expr)

    def register_interval(
        self,
        name: str,
        func: TaskFunc,
        seconds: int,
        max_retries: int = 3,
    ) -> None:
        """注册固定间隔任务。"""
        self._remove_existing(name)
        trigger = IntervalTrigger(seconds=seconds)
        self._scheduler.add_job(
            self._enqueue_with_history,
            trigger=trigger,
            id=name,
            args=[name, func, max_retries],
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self._registered[name] = {
            "type": "interval",
            "seconds": seconds,
            "max_retries": max_retries,
        }
        logger.info("interval_task_registered: name=%s seconds=%d", name, seconds)

    def register_oneoff(
        self,
        name: str,
        func: TaskFunc,
        run_at: datetime,
        max_retries: int = 3,
    ) -> None:
        """注册一次性延迟任务。"""
        self._remove_existing(name)
        trigger = DateTrigger(run_date=run_at)
        self._scheduler.add_job(
            self._enqueue_with_history,
            trigger=trigger,
            id=name,
            args=[name, func, max_retries],
            replace_existing=True,
        )
        self._registered[name] = {
            "type": "oneoff",
            "run_at": run_at.isoformat(),
            "max_retries": max_retries,
        }
        logger.info("oneoff_task_registered: name=%s run_at=%s", name, run_at)

    def _remove_existing(self, name: str) -> None:
        """移除同名任务(若存在)。

        APScheduler 3.11+: 未启动时 replace_existing 不立即生效,
        需手动从 _pending_jobs 移除以避免重复。
        """
        try:
            existing = self._scheduler.get_job(name)
            if existing is not None:
                self._scheduler.remove_job(name)
        except Exception:
            pass
        # 同时清理 _pending_jobs(防止未启动调度器累积)
        pending = getattr(self._scheduler, "_pending_jobs", None)
        if pending:
            self._scheduler._pending_jobs = [
                (j, s, r) for (j, s, r) in pending if j.id != name
            ]

    async def trigger_now(
        self,
        name: str,
        func: TaskFunc,
        max_retries: int = 3,
        triggered_by: str = "manual",
    ) -> dict[str, Any]:
        """手动触发任务(立即入队,不经过调度器触发)。"""
        return await self._enqueue_with_history(
            name, func, max_retries, triggered_by=triggered_by
        )

    async def _enqueue_with_history(
        self,
        name: str,
        func: TaskFunc,
        max_retries: int = 3,
        triggered_by: str = "scheduler",
    ) -> dict[str, Any]:
        """同步执行任务并记录执行历史(供调度器/手动触发共用)。

        设计权衡: 简化状态机,这里同步执行任务并直接写回结果。
        长耗时任务应由 API 路由直接 enqueue 到 TaskQueue,不走这里。
        """
        if self._session_factory is None:
            # 无 DB session: 直接执行,不记录历史
            start = datetime.now(timezone.utc)
            try:
                await func()
                return {
                    "name": name,
                    "status": "success",
                    "duration_ms": int(
                        (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    ),
                }
            except Exception as e:
                logger.exception("scheduled_task_failed: name=%s", name)
                return {
                    "name": name,
                    "status": "failed",
                    "error": f"{type(e).__name__}: {e}"[:2000],
                }

        # 有 DB session: 同步执行 + 记录历史
        from repositories import TaskExecutionRepository

        async with self._session_factory() as session:
            repo = TaskExecutionRepository(session)
            execution = TaskExecutionORM(
                task_name=name,
                status="running",
                triggered_by=triggered_by,
            )
            session.add(execution)
            await session.commit()
            await session.refresh(execution)
            exec_id = execution.id

        start = datetime.now(timezone.utc)
        error_msg: str | None = None
        status_result = "success"
        task_result: Any = None

        try:
            task_result = await func(self._session_factory)
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"[:2000]
            status_result = "failed"
            logger.exception("scheduled_task_failed: name=%s", name)
        finally:
            completed = datetime.now(timezone.utc)
            duration_ms = int((completed - start).total_seconds() * 1000)
            meta: dict[str, Any] = {}
            if isinstance(task_result, dict):
                meta = task_result
            elif task_result is not None:
                meta = {"result": str(task_result)[:500]}
            async with self._session_factory() as session:
                from sqlalchemy import update

                await session.execute(
                    update(TaskExecutionORM)
                    .where(TaskExecutionORM.id == exec_id)
                    .values(
                        status=status_result,
                        completed_at=completed,
                        duration_ms=duration_ms,
                        error_message=error_msg,
                        metadata_=meta,
                    )
                )
                await session.commit()

        out: dict[str, Any] = {
            "id": exec_id,
            "name": name,
            "status": status_result,
            "duration_ms": duration_ms,
        }
        if error_msg:
            out["error"] = error_msg
        if isinstance(task_result, dict):
            out["result"] = task_result
        return out

    def start(self) -> None:
        """启动调度器。"""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("scheduler_started: tasks=%d", len(self._registered))

    async def stop(self, wait: bool = True) -> None:
        """停止调度器。"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("scheduler_stopped")

    def list_tasks(self) -> list[dict[str, Any]]:
        """列出已注册任务。"""
        jobs = self._scheduler.get_jobs()
        result = []
        for job in jobs:
            info = self._registered.get(job.id, {})
            # APScheduler 3.11+: 未启动调度器时 next_run_time 不可用
            next_run = getattr(job, "next_run_time", None)
            result.append(
                {
                    "name": job.id,
                    "next_run_at": next_run.isoformat() if next_run else None,
                    "trigger": str(job.trigger),
                    **info,
                }
            )
        return result


# 全局单例
_scheduler: SchedulerService | None = None


def get_scheduler() -> SchedulerService:
    """获取全局调度器单例。"""
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerService()
    return _scheduler


def set_scheduler_session_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """注入 DB session 工厂(供 lifespan 调用)。"""
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerService(session_factory=session_factory)
    else:
        _scheduler._session_factory = session_factory


def reset_scheduler_for_test() -> None:
    """测试用: 重置单例。"""
    global _scheduler
    if _scheduler is not None and _scheduler._scheduler.running:
        try:
            _scheduler._scheduler.shutdown(wait=False)
        except Exception:
            pass
    _scheduler = None
