"""进程内异步任务队列: 重试 + 指数退避 + 死信 + 并发控制。

设计:
- 基于 asyncio.Queue + worker 协程
- 每个任务带: name, func, args, retries, max_retries, backoff_base
- 重试: 失败后 sleep(backoff_base * 2^attempt) 后重新入队
- 超过 max_retries 进入死信队列(供排查)
- 并发: 可配置 worker 数量(默认 4)

注意: 这是单进程队列,适合中小规模。生产环境大规模建议换 Celery + Redis broker。
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# 任务函数签名: 接受任意参数,返回任意结果(可 await)
TaskFunc = Callable[..., Awaitable[Any]]


@dataclass
class Task:
    """任务实例。"""

    name: str
    func: TaskFunc
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    retries: int = 0
    max_retries: int = 3
    backoff_base: float = 1.0  # 秒
    triggered_by: str = "scheduler"
    created_at: float = field(default_factory=time.time)

    def invoke(self) -> Awaitable[Any]:
        return self.func(*self.args, **self.kwargs)


@dataclass
class DeadLetter:
    """死信: 重试耗尽后保留。"""

    task: Task
    last_error: str
    failed_at: float = field(default_factory=time.time)


class TaskQueue:
    """异步任务队列。"""

    def __init__(self, num_workers: int = 4) -> None:
        self._queue: asyncio.Queue[Task | None] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._num_workers = num_workers
        self._dead_letters: list[DeadLetter] = []
        self._running = False
        self._stats = {
            "enqueued": 0,
            "succeeded": 0,
            "failed": 0,
            "retried": 0,
        }

    async def start(self) -> None:
        """启动 worker。"""
        if self._running:
            return
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self._num_workers)
        ]
        logger.info("task_queue_started: workers=%d", self._num_workers)

    async def stop(self, timeout: float = 5.0) -> None:
        """优雅停止: 发送 sentinel,等待 worker 退出。"""
        if not self._running:
            return
        self._running = False
        # 每个 worker 一个 sentinel (None)
        for _ in self._workers:
            await self._queue.put(None)
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._workers, return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            for w in self._workers:
                w.cancel()
        self._workers = []
        logger.info("task_queue_stopped")

    async def enqueue(
        self,
        name: str,
        func: TaskFunc,
        *args: Any,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        triggered_by: str = "manual",
        **kwargs: Any,
    ) -> None:
        """入队一个任务。"""
        if not self._running:
            raise RuntimeError("TaskQueue not started, call start() first")
        task = Task(
            name=name,
            func=func,
            args=args,
            kwargs=kwargs,
            max_retries=max_retries,
            backoff_base=backoff_base,
            triggered_by=triggered_by,
        )
        await self._queue.put(task)
        self._stats["enqueued"] += 1
        logger.info("task_enqueued: name=%s triggered_by=%s", name, triggered_by)

    async def _worker_loop(self, worker_id: int) -> None:
        """worker 协程: 循环取任务执行。"""
        while self._running:
            task = await self._queue.get()
            if task is None:  # sentinel
                self._queue.task_done()
                return
            try:
                await self._execute_with_retry(task, worker_id)
            except Exception:
                logger.exception("worker_unexpected_error: worker=%d", worker_id)
            finally:
                self._queue.task_done()

    async def _execute_with_retry(self, task: Task, worker_id: int) -> None:
        """执行任务,失败则重试。"""
        last_error: str = ""
        for attempt in range(task.max_retries + 1):
            try:
                start = time.time()
                result = await task.invoke()
                duration = (time.time() - start) * 1000
                self._stats["succeeded"] += 1
                logger.info(
                    "task_success: name=%s worker=%d attempt=%d duration_ms=%.0f",
                    task.name,
                    worker_id,
                    attempt,
                    duration,
                )
                return result
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                tb = traceback.format_exc()
                if attempt < task.max_retries:
                    backoff = task.backoff_base * (2 ** attempt)
                    logger.warning(
                        "task_retry: name=%s attempt=%d/%d backoff=%.1fs err=%s",
                        task.name,
                        attempt + 1,
                        task.max_retries,
                        backoff,
                        last_error,
                    )
                    self._stats["retried"] += 1
                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        "task_failed: name=%s attempts=%d err=%s\n%s",
                        task.name,
                        attempt + 1,
                        last_error,
                        tb,
                    )
                    self._stats["failed"] += 1
                    self._dead_letters.append(DeadLetter(task=task, last_error=last_error))
                    return

    @property
    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "queue_size": self._queue.qsize(),
            "dead_letters": len(self._dead_letters),
            "running": self._running,
        }

    @property
    def dead_letters(self) -> list[DeadLetter]:
        return list(self._dead_letters)

    def clear_dead_letters(self) -> None:
        self._dead_letters.clear()


# 全局单例(进程内)
_queue: TaskQueue | None = None


def get_task_queue() -> TaskQueue:
    """获取全局任务队列单例。"""
    global _queue
    if _queue is None:
        _queue = TaskQueue(num_workers=4)
    return _queue


def reset_task_queue_for_test() -> None:
    """测试用: 重置单例。"""
    global _queue
    _queue = None
