"""TaskQueue + SchedulerService 单元测试。"""

import asyncio

import pytest
import pytest_asyncio

from core.scheduler import (
    SchedulerService,
    get_scheduler,
    reset_scheduler_for_test,
)
from core.task_queue import (
    DeadLetter,
    Task,
    TaskQueue,
    get_task_queue,
    reset_task_queue_for_test,
)


# ---------- TaskQueue: 基础执行 ----------


@pytest.mark.asyncio
async def test_queue_executes_task_successfully():
    queue = TaskQueue(num_workers=2)
    await queue.start()

    result_holder: list[int] = []

    async def add_one(x: int) -> int:
        result_holder.append(x)
        return x + 1

    await queue.enqueue("test_add", add_one, 10)
    # 等待 worker 处理
    await asyncio.sleep(0.1)

    assert result_holder == [10]
    assert queue.stats["succeeded"] == 1
    await queue.stop()


@pytest.mark.asyncio
async def test_queue_retries_on_failure():
    """任务失败时按指数退避重试。"""
    queue = TaskQueue(num_workers=1)
    await queue.start()

    call_count = 0

    async def flaky_task():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError(f"fail #{call_count}")

    # max_retries=3,backoff_base=0.01(加快测试)
    await queue.enqueue(
        "flaky", flaky_task, max_retries=3, backoff_base=0.01
    )
    # 等待重试完成: 0.01 + 0.02 = 0.03s + 处理时间
    await asyncio.sleep(0.2)

    assert call_count == 3
    assert queue.stats["succeeded"] == 1
    assert queue.stats["retried"] == 2
    await queue.stop()


@pytest.mark.asyncio
async def test_queue_dead_letter_after_max_retries():
    """超过 max_retries 进入死信队列。"""
    queue = TaskQueue(num_workers=1)
    await queue.start()

    async def always_fail():
        raise RuntimeError("permanent failure")

    await queue.enqueue(
        "doomed", always_fail, max_retries=2, backoff_base=0.01
    )
    await asyncio.sleep(0.3)

    assert queue.stats["failed"] == 1
    assert len(queue.dead_letters) == 1
    dl = queue.dead_letters[0]
    assert dl.task.name == "doomed"
    assert "permanent failure" in dl.last_error
    await queue.stop()


@pytest.mark.asyncio
async def test_queue_concurrent_workers():
    """多 worker 并发处理多个任务。"""
    queue = TaskQueue(num_workers=4)
    await queue.start()

    completed: list[int] = []
    lock = asyncio.Lock()

    async def slow_task(i: int):
        await asyncio.sleep(0.05)
        async with lock:
            completed.append(i)

    for i in range(8):
        await queue.enqueue(f"task_{i}", slow_task, i)

    # 8 个任务 * 0.05s / 4 workers ≈ 0.1s
    await asyncio.sleep(0.3)
    assert len(completed) == 8
    assert queue.stats["succeeded"] == 8
    await queue.stop()


@pytest.mark.asyncio
async def test_queue_stop_graceful():
    """stop 后 worker 退出,新任务不入队。"""
    queue = TaskQueue(num_workers=1)
    await queue.start()
    await queue.stop()

    with pytest.raises(RuntimeError, match="not started"):
        await queue.enqueue("x", lambda: None)


@pytest.mark.asyncio
async def test_queue_stats_track_all_states():
    queue = TaskQueue(num_workers=1)
    await queue.start()

    async def success():
        pass

    async def fail():
        raise ValueError()

    await queue.enqueue("s1", success, max_retries=0)
    await queue.enqueue("f1", fail, max_retries=0)
    await asyncio.sleep(0.2)

    stats = queue.stats
    assert stats["enqueued"] == 2
    assert stats["succeeded"] == 1
    assert stats["failed"] == 1
    assert stats["running"] is True
    await queue.stop()


@pytest.mark.asyncio
async def test_queue_clear_dead_letters():
    queue = TaskQueue(num_workers=1)
    await queue.start()

    async def fail():
        raise ValueError()

    await queue.enqueue("f", fail, max_retries=0)
    await asyncio.sleep(0.1)
    assert len(queue.dead_letters) == 1

    queue.clear_dead_letters()
    assert len(queue.dead_letters) == 0
    await queue.stop()


# ---------- 全局单例 ----------


@pytest.mark.asyncio
async def test_get_task_queue_singleton():
    reset_task_queue_for_test()
    q1 = get_task_queue()
    q2 = get_task_queue()
    assert q1 is q2
    reset_task_queue_for_test()


# ---------- SchedulerService: 任务注册 ----------


def test_scheduler_register_cron():
    scheduler = SchedulerService()

    async def task():
        pass

    scheduler.register_cron("test_cron", task, "0 8 * * *")
    tasks = scheduler.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["name"] == "test_cron"
    assert tasks[0]["type"] == "cron"
    assert tasks[0]["expr"] == "0 8 * * *"


def test_scheduler_register_interval():
    scheduler = SchedulerService()

    async def task():
        pass

    scheduler.register_interval("test_interval", task, seconds=60)
    tasks = scheduler.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["name"] == "test_interval"
    assert tasks[0]["type"] == "interval"
    assert tasks[0]["seconds"] == 60


def test_scheduler_register_oneoff():
    from datetime import datetime, timedelta

    scheduler = SchedulerService()

    async def task():
        pass

    run_at = datetime.utcnow() + timedelta(hours=1)
    scheduler.register_oneoff("test_oneoff", task, run_at)
    tasks = scheduler.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["name"] == "test_oneoff"
    assert tasks[0]["type"] == "oneoff"


def test_scheduler_replace_existing():
    """同名任务注册两次,后者替换前者。"""
    scheduler = SchedulerService()

    async def task():
        pass

    scheduler.register_interval("dup", task, seconds=60)
    scheduler.register_interval("dup", task, seconds=120)
    tasks = scheduler.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["seconds"] == 120


def test_scheduler_get_scheduler_singleton():
    reset_scheduler_for_test()
    s1 = get_scheduler()
    s2 = get_scheduler()
    assert s1 is s2
    reset_scheduler_for_test()


# ---------- SchedulerService: 实际执行(无 DB) ----------


@pytest.mark.asyncio
async def test_scheduler_trigger_now_executes_task():
    """trigger_now 同步执行任务并返回结果。"""
    scheduler = SchedulerService(session_factory=None)

    executed: list[bool] = []

    async def task():
        executed.append(True)
        return {"done": True}

    result = await scheduler.trigger_now("manual_test", task)
    assert result["status"] == "success"
    assert executed == [True]


@pytest.mark.asyncio
async def test_scheduler_trigger_now_handles_failure():
    scheduler = SchedulerService(session_factory=None)

    async def fail_task():
        raise ValueError("boom")

    result = await scheduler.trigger_now("manual_fail", fail_task)
    assert result["status"] == "failed"
