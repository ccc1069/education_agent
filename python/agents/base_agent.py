"""
Agent 基类 -- 所有Agent的公共接口和行为。

每个Agent都：
1. 有一个名称和角色描述
2. 连接到EventBus，订阅感兴趣的事件
3. 可以发布事件通知其他Agent
4. 有自己的处理逻辑（子类实现）

面试要点：
- 模板方法模式：基类定义骨架，子类实现细节
- 依赖注入：EventBus通过构造函数注入
- 单一职责原则：每个Agent只关注自己的领域
- 可观测性: handle_event 自动记录处理耗时到 Prometheus
"""

import logging
import time
from abc import ABC, abstractmethod

from core.event_bus import Event, EventBus, EventType
from core.learner_model import LearnerModel

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Agent 基类。

    子类需要实现：
    - subscribed_events: 返回自己订阅的事件类型列表
    - handle_event: 处理接收到的事件
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        learner_models: dict[str, LearnerModel],
    ) -> None:
        self.name = name
        self.event_bus = event_bus
        self.learner_models = learner_models
        self._register_handlers()
        logger.info("[%s] Agent initialized", self.name)

    def _register_handlers(self) -> None:
        """注册事件处理器到EventBus。

        自动包装 handle_event 以记录耗时指标。
        """
        for event_type in self.subscribed_events:
            self.event_bus.subscribe(event_type, self._wrap_handle(event_type))
            logger.debug("[%s] Subscribed to %s", self.name, event_type.value)

    def _wrap_handle(self, event_type: EventType):
        """返回一个包装了指标采集的 handler。"""

        async def wrapped(event: Event) -> None:
            start = time.perf_counter()
            try:
                await self.handle_event(event)
            finally:
                duration = time.perf_counter() - start
                try:
                    from observability.metrics import AGENT_PROCESSING_DURATION

                    AGENT_PROCESSING_DURATION.labels(
                        agent_name=self.name, event_type=event_type.value
                    ).observe(duration)
                except ImportError:
                    pass  # observability 未启用

        return wrapped

    @property
    @abstractmethod
    def subscribed_events(self) -> list[EventType]:
        """子类声明自己订阅哪些事件。"""
        ...

    @abstractmethod
    async def handle_event(self, event: Event) -> None:
        """子类实现事件处理逻辑。

        指标采集由基类的 _wrap_handle 自动完成。
        """
        ...

    async def emit(self, event_type: EventType, learner_id: str, data: dict) -> None:
        """便捷方法：发布事件。"""
        event = Event(
            type=event_type,
            source=self.name,
            learner_id=learner_id,
            data=data,
        )
        await self.event_bus.publish(event)

    def get_learner_model(self, learner_id: str) -> LearnerModel:
        """获取学习者模型，不存在则创建。"""
        if learner_id not in self.learner_models:
            self.learner_models[learner_id] = LearnerModel(learner_id)
        return self.learner_models[learner_id]

