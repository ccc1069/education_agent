"""第 6 天：并发状态更新与锁的保护范围。

仅使用 Python 标准库，不调用模型或数据库。
前两组通过 Event 刻意让两个任务都读到旧值，以稳定复现更新丢失。
第三组使用同一把 asyncio.Lock 保护完整读改写过程。
"""

import asyncio


async def run_case(title, lock_scope, expected):
    print(f"\n=== {title} ===")
    state = {"learner_id": "student_A", "attempts": 5}
    lock = asyncio.Lock()
    both_read = asyncio.Event()
    readers = 0
    print("初始次数：5；任务 A 和 B 各处理一道题；正确累计应为 7。")

    def read_state(name):
        current = state["attempts"]
        print(f"  {name} 读取：{current}")
        return current

    def write_back(name, current):
        updated = current + 1
        state["attempts"] = updated
        print(f"  {name} 根据旧值 {current} 加一，写入：{updated}")

    async def handle_answer(name):
        nonlocal readers

        if lock_scope == "whole":
            async with lock:
                print(f"  {name} 获得锁")
                current = read_state(name)
                # 即使此处让出执行权，另一个任务也无法进入临界区读取。
                await asyncio.sleep(0)
                write_back(name, current)
            print(f"  {name} 已释放锁")
            return

        current = read_state(name)
        readers += 1
        if readers == 2:
            both_read.set()
        # 实验同步点：保证两个任务都读完旧值后，再进行写回。
        await both_read.wait()

        if lock_scope == "write_only":
            async with lock:
                print(f"  {name} 获得写入锁，但已读到的旧值仍是 {current}")
                write_back(name, current)
        else:
            write_back(name, current)

    await asyncio.gather(handle_answer("任务 A"), handle_answer("任务 B"))
    actual = state["attempts"]
    print(f"最终次数：{actual}")
    if actual == 7:
        print("结果：两次更新均被保留。")
    else:
        print("结果：丢失一次更新；两个任务都使用旧值 5 算出了 6。")
    assert actual == expected, f"实验结果与设计不符：{actual} != {expected}"


async def main():
    print("三组实验各自从 5 开始，不会互相累积。")
    print("前两组刻意安排读写交错，不表示所有不加锁代码每次都会冲突。")
    await run_case("实验 1：不加锁", "none", expected=6)
    await run_case("实验 2：只保护写入", "write_only", expected=6)
    await run_case("实验 3：保护读取、计算、写入", "whole", expected=7)


if __name__ == "__main__":
    asyncio.run(main())
