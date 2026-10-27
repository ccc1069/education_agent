"""第 4 天：用标准库演示并发等待和异常隔离。

这是简化教学示例，不会启动项目服务或修改数据库。
运行：python -X utf8 python/scripts/lesson04_eventbus_concurrency.py
"""

import asyncio
import time


async def tutor(event, log):
    log("Tutor 开始处理")
    await asyncio.sleep(2)
    log("Tutor 处理完成")


async def engagement(event, log):
    log("Engagement 开始处理")
    raise RuntimeError("模拟学习状态监测失败")


async def audit(event, log):
    log("Audit 开始处理")
    await asyncio.sleep(0.5)
    log("Audit 处理完成")


async def safe_handle(handler, event, log):
    try:
        await handler(event, log)
    except Exception as exc:
        log(f"{handler.__name__} 失败，异常已捕获：{exc}")


async def run_demo(parallel):
    mode = "并发执行" if parallel else "串行执行"
    print(f"\n--- {mode} ---", flush=True)
    started = time.perf_counter()

    def log(message):
        elapsed = time.perf_counter() - started
        print(f"[{elapsed:.2f}s] {message}", flush=True)

    event = {"type": "assessment.complete", "learner_id": "demo"}
    handlers = [tutor, engagement, audit]

    if parallel:
        await asyncio.gather(
            *(safe_handle(handler, event, log) for handler in handlers)
        )
    else:
        for handler in handlers:
            await safe_handle(handler, event, log)

    log("发布调用正常结束；这不代表所有处理函数都成功")


async def main():
    print("实验会依次运行并发版和串行版，预计共约 4.5 秒。")
    await run_demo(parallel=True)
    await run_demo(parallel=False)


if __name__ == "__main__":
    asyncio.run(main())
