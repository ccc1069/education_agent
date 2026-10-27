"""DebateAgent 单元测试: 订阅 STUDENT_QUESTION + debate_mode 触发辩论。

覆盖:
- 订阅 STUDENT_QUESTION
- debate_mode=False: 不触发
- debate_mode=True: 触发辩论,发布 DEBATE_CONSENSUS
- LLM 全失败: 静默跳过
- 空 question: 不触发
"""

from typing import Any

import pytest

from agents.debate_agent import DebateAgent
from core.event_bus import EventBus, Event, EventType
from llm.debate_service import DebateLLMService, DebateResult, DebateRound
from llm.provider import LLMError, LLMMessage, LLMProvider, LLMResponse


class _ScriptedProvider(LLMProvider):
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


class _StubDebateService(DebateLLMService):
    """绕过真实 LLM,直接返回预设 DebateResult。"""

    def __init__(self, result: DebateResult) -> None:
        # 不调用父类 __init__,跳过 provider 初始化
        self._stub_result = result

    async def run_debate(self, **kwargs):  # type: ignore[override]
        return self._stub_result


@pytest.fixture
def learner_models():
    return {}


@pytest.fixture
def event_bus():
    return EventBus()


def _make_question_event(
    question: str = "什么是方程?",
    debate_mode: bool = True,
    knowledge_id: str = "algebra",
    level: str = "beginner",
) -> Event:
    return Event(
        type=EventType.STUDENT_QUESTION,
        source="api",
        learner_id="learner_1",
        data={
            "knowledge_id": knowledge_id,
            "question": question,
            "debate_mode": debate_mode,
            "level": level,
            "mastery": 0.3,
        },
    )


def _make_debate_result(consensus: str = "consensus-text") -> DebateResult:
    return DebateResult(
        consensus=consensus,
        rounds=[
            DebateRound(
                round_num=1,
                socratic_response="s-r1",
                direct_response="d-r1",
                socratic_critique_of_direct="cs",
                direct_critique_of_socratic="cd",
            )
        ],
        socratic_final="s-final",
        direct_final="d-final",
        metadata={
            "llm_used": True,
            "llm_calls": 7,
            "total_tokens": 210,
            "rounds": 2,
        },
    )


# ---------- 订阅事件 ----------


def test_debate_subscribes_to_student_question():
    bus = EventBus()
    DebateAgent(
        name="DebateAgent",
        event_bus=bus,
        learner_models={},
        debate_service=_StubDebateService(_make_debate_result()),
    )
    assert EventType.STUDENT_QUESTION in bus._subscribers


# ---------- debate_mode=False: 不触发 ----------


@pytest.mark.asyncio
async def test_debate_mode_false_does_not_trigger(event_bus, learner_models):
    captured: list[Event] = []
    event_bus.subscribe(EventType.DEBATE_CONSENSUS, lambda e: captured.append(e))

    agent = DebateAgent(
        name="DebateAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        debate_service=_StubDebateService(_make_debate_result()),
    )

    await event_bus.publish(_make_question_event(debate_mode=False))

    assert len(captured) == 0


# ---------- debate_mode=True: 触发辩论 ----------


@pytest.mark.asyncio
async def test_debate_mode_true_triggers_debate(event_bus, learner_models):
    captured: list[Event] = []
    event_bus.subscribe(EventType.DEBATE_CONSENSUS, lambda e: captured.append(e))

    DebateAgent(
        name="DebateAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        debate_service=_StubDebateService(_make_debate_result()),
    )

    await event_bus.publish(_make_question_event())

    assert len(captured) == 1
    payload = captured[0].data
    assert payload["response"] == "consensus-text"
    assert payload["teaching_style"] == "debate_synthesis"
    assert payload["socratic_final"] == "s-final"
    assert payload["direct_final"] == "d-final"
    assert payload["rounds_completed"] == 1
    assert payload["llm_used"] is True
    assert captured[0].source == "DebateAgent"


# ---------- 空 question: 不触发 ----------


@pytest.mark.asyncio
async def test_empty_question_does_not_trigger(event_bus, learner_models):
    captured: list[Event] = []
    event_bus.subscribe(EventType.DEBATE_CONSENSUS, lambda e: captured.append(e))

    DebateAgent(
        name="DebateAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        debate_service=_StubDebateService(_make_debate_result()),
    )

    await event_bus.publish(_make_question_event(question=""))

    assert len(captured) == 0


# ---------- 空 consensus: 不发布 ----------


@pytest.mark.asyncio
async def test_empty_consensus_does_not_publish(event_bus, learner_models):
    captured: list[Event] = []
    event_bus.subscribe(EventType.DEBATE_CONSENSUS, lambda e: captured.append(e))

    empty_result = DebateResult(
        consensus="",
        rounds=[],
        socratic_final="",
        direct_final="",
        metadata={"llm_used": False, "error": "all failed"},
    )
    DebateAgent(
        name="DebateAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        debate_service=_StubDebateService(empty_result),
    )

    await event_bus.publish(_make_question_event())

    assert len(captured) == 0  # 空 consensus,不发布


# ---------- LLM 全失败: 静默跳过(通过真实 service) ----------


@pytest.mark.asyncio
async def test_debate_silent_when_llm_unavailable(event_bus, learner_models):
    captured: list[Event] = []
    event_bus.subscribe(EventType.DEBATE_CONSENSUS, lambda e: captured.append(e))

    DebateAgent(
        name="DebateAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        debate_service=DebateLLMService(provider=_AlwaysFailsProvider()),
    )

    # 不应抛异常
    await event_bus.publish(_make_question_event())

    assert len(captured) == 0


# ---------- 注入 service 被使用 ----------


@pytest.mark.asyncio
async def test_debate_uses_injected_service(event_bus, learner_models):
    result = _make_debate_result(consensus="injected-consensus")
    service = _StubDebateService(result)

    captured: list[Event] = []
    event_bus.subscribe(EventType.DEBATE_CONSENSUS, lambda e: captured.append(e))

    DebateAgent(
        name="DebateAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        debate_service=service,
    )

    await event_bus.publish(_make_question_event())

    assert len(captured) == 1
    assert captured[0].data["response"] == "injected-consensus"


# ---------- 端到端: 真实 DebateLLMService + ScriptedProvider ----------


@pytest.mark.asyncio
async def test_debate_agent_end_to_end_with_real_service(event_bus, learner_models):
    """端到端: DebateAgent + 真实 DebateLLMService + ScriptedProvider(rounds=1)。"""
    responses = [
        "socratic-r1",
        "direct-r1",
        "synthesis-final",
    ]
    provider = _ScriptedProvider(responses)
    service = DebateLLMService(provider=provider, rounds=1)

    captured: list[Event] = []
    event_bus.subscribe(EventType.DEBATE_CONSENSUS, lambda e: captured.append(e))

    DebateAgent(
        name="DebateAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        debate_service=service,
    )

    await event_bus.publish(_make_question_event())

    assert len(captured) == 1
    assert captured[0].data["response"] == "synthesis-final"
    assert captured[0].data["socratic_final"] == "socratic-r1"
    assert captured[0].data["direct_final"] == "direct-r1"
    assert captured[0].data["rounds_completed"] == 1
    assert captured[0].data["llm_used"] is True
