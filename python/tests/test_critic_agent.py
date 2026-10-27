"""CriticAgent 单元测试: 订阅 TEACHING_RESPONSE -> 评估 -> 低分重生成 -> 发布事件。

覆盖:
- 订阅 TEACHING_RESPONSE 事件
- 高分: 发布 TEACHING_CRITICIZED,不重生成
- 低分: 发布 TEACHING_CRITICIZED + 新的 TEACHING_RESPONSE(regenerated=True)
- LLM 不可用: 静默跳过,不阻塞主流程
- 跳过 regenerated=True 的重生成事件(防循环)
- 跳过 hint 转发(teaching_style="hint")
"""

import json
from typing import Any

import pytest

from agents.critic_agent import CriticAgent
from core.event_bus import EventBus, Event, EventType
from llm.critic_service import CriticLLMService
from llm.provider import LLMError, LLMMessage, LLMProvider, LLMResponse


class _ScriptedProvider(LLMProvider):
    """按预设顺序返回响应的 Provider,测试用。"""

    def __init__(self, responses: list[str]) -> None:
        super().__init__(name="scripted", model="scripted-1.0", timeout=1.0, max_retries=1)
        self._responses = list(responses)
        self._index = 0
        self.calls: list[list[LLMMessage]] = []

    async def _call(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        self.calls.append(messages)
        if self._index >= len(self._responses):
            raise LLMError("no more scripted responses")
        content = self._responses[self._index]
        self._index += 1
        return LLMResponse(
            content=content,
            model=self.model,
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            finish_reason="stop",
            latency_ms=5.0,
        )


class _AlwaysFailsProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(name="fail", model="fail-1.0", timeout=1.0, max_retries=1)
        self.retry_initial_delay = 0.0

    async def _call(self, messages, **kwargs):
        raise LLMError("simulated failure")


@pytest.fixture
def learner_models():
    return {}


@pytest.fixture
def event_bus():
    return EventBus()


def _make_critic_event(
    response: str = "原回复",
    level: str = "beginner",
    knowledge_id: str = "kp1",
    is_correct: bool | None = False,
    mastery: float = 0.3,
    teaching_style: str = "socratic",
    question: str = "1+1=?",
    regenerated: bool = False,
) -> Event:
    return Event(
        type=EventType.TEACHING_RESPONSE,
        source="TutorAgent",
        learner_id="learner_1",
        data={
            "knowledge_id": knowledge_id,
            "response": response,
            "difficulty_level": level,
            "teaching_style": teaching_style,
            "mastery": mastery,
            "is_correct": is_correct,
            "question": question,
            "llm_used": True,
            "model": "mock",
            "tokens": 100,
            "regenerated": regenerated,
        },
    )


def _high_score_json() -> str:
    return json.dumps(
        {
            "scores": {
                "pedagogical": 5,
                "appropriateness": 5,
                "clarity": 5,
                "engagement": 5,
            },
            "overall": 5,
            "critique": "优秀。",
            "needs_regeneration": False,
        },
        ensure_ascii=False,
    )


def _low_score_json() -> str:
    return json.dumps(
        {
            "scores": {
                "pedagogical": 2,
                "appropriateness": 2,
                "clarity": 2,
                "engagement": 2,
            },
            "overall": 2,
            "critique": "直接给答案,违反教学原则。",
            "needs_regeneration": True,
        },
        ensure_ascii=False,
    )


# ---------- 订阅事件 ----------


def test_critic_subscribes_to_teaching_response():
    """CriticAgent 应订阅 TEACHING_RESPONSE。"""
    bus = EventBus()
    critic = CriticAgent(
        name="CriticAgent",
        event_bus=bus,
        learner_models={},
        critic_service=CriticLLMService(provider=_ScriptedProvider([])),
    )
    # _subscribers 在 BaseAgent._register_handlers 中填充
    assert EventType.TEACHING_RESPONSE in bus._subscribers
    assert len(bus._subscribers[EventType.TEACHING_RESPONSE]) >= 1


# ---------- 高分: 评估但不重生成 ----------


@pytest.mark.asyncio
async def test_critic_high_score_publishes_criticism_only(event_bus, learner_models):
    """高分: 只发布 TEACHING_CRITICIZED,不重生成新的 TEACHING_RESPONSE。"""
    provider = _ScriptedProvider([_high_score_json()])
    critic = CriticAgent(
        name="CriticAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        critic_service=CriticLLMService(provider=provider),
    )

    criticized: list[Event] = []
    new_teaching: list[Event] = []
    event_bus.subscribe(EventType.TEACHING_CRITICIZED, lambda e: criticized.append(e))

    # 只抓 CriticAgent 发布的新 TEACHING_RESPONSE(排除原始事件)
    async def _capture_teaching(event: Event):
        if event.source == "CriticAgent":
            new_teaching.append(event)

    event_bus.subscribe(EventType.TEACHING_RESPONSE, _capture_teaching)

    await event_bus.publish(_make_critic_event())

    assert len(criticized) == 1
    assert criticized[0].data["overall"] == 5
    assert criticized[0].data["needs_regeneration"] is False
    # 不应再发布新的 TEACHING_RESPONSE
    assert len(new_teaching) == 0
    # 只调了 1 次 LLM(评估)
    assert len(provider.calls) == 1


# ---------- 低分: 重生成 ----------


@pytest.mark.asyncio
async def test_critic_low_score_regenerates(event_bus, learner_models):
    """低分: 发布 TEACHING_CRITICIZED + 新的 TEACHING_RESPONSE(regenerated=True)。"""
    provider = _ScriptedProvider([_low_score_json(), "regenerated response"])
    critic = CriticAgent(
        name="CriticAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        critic_service=CriticLLMService(provider=provider),
    )

    criticized: list[Event] = []
    new_teaching: list[Event] = []
    event_bus.subscribe(EventType.TEACHING_CRITICIZED, lambda e: criticized.append(e))

    # CriticAgent 自己会发布 TEACHING_RESPONSE (regenerated=True),
    # 但它已订阅 TEACHING_RESPONSE -> 会被自己处理 -> handle_event 跳过 regenerated=True
    # 我们用独立 handler 抓新增的 TEACHING_RESPONSE
    async def _capture_teaching(event: Event):
        if event.source == "CriticAgent":
            new_teaching.append(event)

    event_bus.subscribe(EventType.TEACHING_RESPONSE, _capture_teaching)

    await event_bus.publish(_make_critic_event(response="答案是 42。"))

    # 1. 评估事件
    assert len(criticized) == 1
    assert criticized[0].data["overall"] == 2
    assert criticized[0].data["needs_regeneration"] is True

    # 2. 重生成的新 TEACHING_RESPONSE
    assert len(new_teaching) == 1
    assert new_teaching[0].data["response"] == "regenerated response"
    assert new_teaching[0].data["regenerated"] is True
    assert new_teaching[0].data["critic_overall"] == 2

    # 3. 调了 2 次 LLM(评估 + 重生成)
    assert len(provider.calls) == 2


# ---------- LLM 不可用: 静默跳过 ----------


@pytest.mark.asyncio
async def test_critic_silent_when_llm_unavailable(event_bus, learner_models):
    """LLM 不可用时不发布任何事件,不阻塞。"""
    critic = CriticAgent(
        name="CriticAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        critic_service=CriticLLMService(provider=_AlwaysFailsProvider()),
    )

    events: list[Event] = []
    event_bus.subscribe(EventType.TEACHING_CRITICIZED, lambda e: events.append(e))

    # 不应抛异常
    await event_bus.publish(_make_critic_event())

    assert len(events) == 0  # 静默跳过


# ---------- 跳过 regenerated=True 事件(防循环) ----------


@pytest.mark.asyncio
async def test_critic_skips_regenerated_events(event_bus, learner_models):
    """带 regenerated=True 的事件应被跳过,避免循环。"""
    provider = _ScriptedProvider([_high_score_json()])
    critic = CriticAgent(
        name="CriticAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        critic_service=CriticLLMService(provider=provider),
    )

    criticized: list[Event] = []
    event_bus.subscribe(EventType.TEACHING_CRITICIZED, lambda e: criticized.append(e))

    await event_bus.publish(_make_critic_event(regenerated=True))

    assert len(criticized) == 0
    assert len(provider.calls) == 0  # 没调 LLM


# ---------- 跳过 hint 转发 ----------


@pytest.mark.asyncio
async def test_critic_skips_hint_style_responses(event_bus, learner_models):
    """teaching_style='hint' 的转发事件不评估(无意义)。"""
    provider = _ScriptedProvider([_high_score_json()])
    critic = CriticAgent(
        name="CriticAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        critic_service=CriticLLMService(provider=provider),
    )

    criticized: list[Event] = []
    event_bus.subscribe(EventType.TEACHING_CRITICIZED, lambda e: criticized.append(e))

    await event_bus.publish(_make_critic_event(teaching_style="hint"))

    assert len(criticized) == 0
    assert len(provider.calls) == 0


# ---------- 评估事件 payload 完整性 ----------


@pytest.mark.asyncio
async def test_criticism_payload_contains_required_fields(event_bus, learner_models):
    """TEACHING_CRITICIZED 事件应包含所有约定字段。"""
    provider = _ScriptedProvider([_high_score_json()])
    critic = CriticAgent(
        name="CriticAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        critic_service=CriticLLMService(provider=provider),
    )

    captured: list[Event] = []
    event_bus.subscribe(EventType.TEACHING_CRITICIZED, lambda e: captured.append(e))

    await event_bus.publish(_make_critic_event(knowledge_id="algebra-basics"))

    assert len(captured) == 1
    payload = captured[0].data
    assert payload["knowledge_id"] == "algebra-basics"
    assert payload["overall"] == 5
    assert "scores" in payload
    assert "pedagogical" in payload["scores"]
    assert "critique" in payload
    assert "needs_regeneration" in payload
    assert "critic_model" in payload
    assert "critic_tokens" in payload
    assert "teaching_event_id" in payload


# ---------- CriticLLMService 注入 ----------


@pytest.mark.asyncio
async def test_critic_uses_injected_service(event_bus, learner_models):
    """注入的 critic_service 应被使用,不创建新的。"""
    provider = _ScriptedProvider([_high_score_json()])
    service = CriticLLMService(provider=provider)
    critic = CriticAgent(
        name="CriticAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        critic_service=service,
    )

    await event_bus.publish(_make_critic_event())
    # 验证注入的 provider 被调用
    assert len(provider.calls) == 1
