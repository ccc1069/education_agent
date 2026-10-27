"""第 5 天：对比集中编排与事件订阅。

纯标准库教学示例；角色用确定性函数模拟，不调用模型或项目数据库。
两种方式都遵守同一要求：Critic 明确通过后，才能交付回复。
"""

import argparse
import asyncio
from collections import defaultdict


async def assess(question):
    print("  Assessment：读取示例学生状态，掌握度 40%")
    return {"question": question, "mastery": 0.4, "level": "beginner"}


async def teach(assessment):
    print("  Tutor：生成候选回复（暂不交给学生）")
    return f"关于“{assessment['question']}”，你能先说说已经理解了哪一步吗？"


async def check(response, args):
    print("  Critic：检查候选回复")
    if args.fail_critic:
        raise TimeoutError("模拟 Critic 超时")
    # 固定的教学开关只用于验证路由，不代表真实教学质量评分。
    return {"approved": not args.reject, "response": response}


async def audit(assessment):
    print(f"  Audit：记录评估结果，等级={assessment['level']}")


def deliver(review):
    print(f"  交给学生：{review['response']}")


async def run_centralized(args):
    """总控函数明确指定调用顺序；加入 Audit 要在流程中加入调用。"""
    print("\n=== 集中编排 ===")
    assessment = await assess(args.question)
    if args.with_audit:
        await audit(assessment)
    response = await teach(assessment)
    try:
        review = await check(response, args)
    except TimeoutError as exc:
        print(f"  审核失败：{exc}；没有交付候选回复")
        return None
    if not review["approved"]:
        print("  审核不通过：没有交付候选回复")
        return None
    deliver(review)
    return review["response"]


class EventBus:
    """仅用于实验的进程内总线，异常隔离方式与项目类似。"""

    def __init__(self):
        self.handlers = defaultdict(list)

    def subscribe(self, event_type, handler):
        self.handlers[event_type].append(handler)

    async def publish(self, event_type, data):
        print(f"  发布事件：{event_type}")
        await asyncio.gather(
            *(self.safe_handle(handler, data) for handler in self.handlers[event_type])
        )

    async def safe_handle(self, handler, data):
        try:
            await handler(data)
        except Exception as exc:
            print(f"  {handler.__name__} 失败：{exc}；异常已记录")


async def run_events(args):
    """处理函数发布结果，订阅配置连接下一步；Audit 作为额外订阅者。"""
    print("\n=== 事件订阅 ===")
    bus = EventBus()
    deliveries = []

    async def assessment_handler(question):
        assessment = await assess(question)
        await bus.publish("assessment.complete", assessment)

    async def tutor_handler(assessment):
        response = await teach(assessment)
        await bus.publish("teaching.candidate", response)

    async def critic_handler(response):
        review = await check(response, args)
        if review["approved"]:
            await bus.publish("teaching.approved", review)
        else:
            print("  审核不通过：不发布 teaching.approved")

    async def delivery_handler(review):
        deliver(review)
        deliveries.append(review["response"])

    # 协作关系由订阅配置确定；事件发布者不直接调用下游角色。
    bus.subscribe("student.question", assessment_handler)
    bus.subscribe("assessment.complete", tutor_handler)
    bus.subscribe("teaching.candidate", critic_handler)
    bus.subscribe("teaching.approved", delivery_handler)

    if args.with_audit:
        bus.subscribe("assessment.complete", audit)

    await bus.publish("student.question", args.question)
    if not deliveries:
        print("  分发已结束，但没有获准交付的回复；不能据此判断业务成功")
    return deliveries[0] if deliveries else None


async def main(args):
    if args.mode in ("both", "centralized"):
        await run_centralized(args)
    if args.mode in ("both", "events"):
        await run_events(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("both", "centralized", "events"), default="both")
    parser.add_argument("--question", default="为什么一元二次方程可能有两个解？")
    parser.add_argument("--with-audit", action="store_true", help="加入记录评估结果的 Audit")
    parser.add_argument("--fail-critic", action="store_true", help="模拟审核超时")
    parser.add_argument("--reject", action="store_true", help="模拟审核不通过")
    args = parser.parse_args()
    if not args.question.strip():
        parser.error("question 不能为空")
    asyncio.run(main(args))
