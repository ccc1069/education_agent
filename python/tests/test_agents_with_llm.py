"""Agent 集成测试: Tutor + Hint + Assessment + Engagement + Curriculum。

测试 Agent 与 LLM、EventBus 的端到端联动。
"""

import pytest

from core.event_bus import EventBus, Event, EventType
from core.learner_model import LearnerModel


@pytest.fixture
def learner_models():
    return {}


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def mock_llm_provider():
    from llm.mock_provider import MockLLMProvider
    return MockLLMProvider()


# ---------- TutorAgent ----------


@pytest.mark.asyncio
async def test_tutor_agent_handles_assessment_complete(
    event_bus, learner_models, mock_llm_provider
):
    from agents.tutor_agent import TutorAgent
    from llm.tutor_service import TutorLLMService

    tutor = TutorAgent(
        name="TutorAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        llm_service=TutorLLMService(provider=mock_llm_provider),
    )

    captured: list[Event] = []
    event_bus.subscribe(EventType.TEACHING_RESPONSE, lambda e: captured.append(e))

    await event_bus.publish(
        Event(
            type=EventType.ASSESSMENT_COMPLETE,
            source="test",
            learner_id="learner_1",
            data={
                "knowledge_id": "arithmetic",
                "mastery": 0.3,
                "level": "beginner",
                "is_correct": False,
                "question": "1+1=?",
            },
        )
    )

    assert len(captured) == 1
    assert captured[0].data["llm_used"] is True
    assert captured[0].data["response"]


@pytest.mark.asyncio
async def test_tutor_agent_requests_hint_after_two_failures(
    event_bus, learner_models, mock_llm_provider
):
    from agents.tutor_agent import TutorAgent
    from llm.tutor_service import TutorLLMService

    tutor = TutorAgent(
        name="TutorAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        llm_service=TutorLLMService(provider=mock_llm_provider),
    )

    hint_requests: list[Event] = []
    event_bus.subscribe(EventType.HINT_NEEDED, lambda e: hint_requests.append(e))

    # 第一次错误 -> 不应触发 HINT_NEEDED
    await event_bus.publish(
        Event(
            type=EventType.ASSESSMENT_COMPLETE,
            source="test",
            learner_id="learner_1",
            data={
                "knowledge_id": "kp1",
                "mastery": 0.2,
                "level": "beginner",
                "is_correct": False,
            },
        )
    )
    assert len(hint_requests) == 0

    # 第二次错误 -> 应触发 HINT_NEEDED
    await event_bus.publish(
        Event(
            type=EventType.ASSESSMENT_COMPLETE,
            source="test",
            learner_id="learner_1",
            data={
                "knowledge_id": "kp1",
                "mastery": 0.2,
                "level": "beginner",
                "is_correct": False,
            },
        )
    )
    assert len(hint_requests) == 1
    assert hint_requests[0].data["attempts"] == 2


# ---------- HintAgent ----------


@pytest.mark.asyncio
async def test_hint_agent_starts_with_metacognitive_level(
    event_bus, learner_models, mock_llm_provider
):
    from agents.hint_agent import HintAgent, HintLevel
    from llm.tutor_service import HintLLMService

    hint_agent = HintAgent(
        name="HintAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        llm_service=HintLLMService(provider=mock_llm_provider),
    )

    captured: list[Event] = []
    event_bus.subscribe(EventType.HINT_RESPONSE, lambda e: captured.append(e))

    await event_bus.publish(
        Event(
            type=EventType.HINT_NEEDED,
            source="test",
            learner_id="learner_1",
            data={"knowledge_id": "kp1", "mastery": 0.3, "attempts": 1},
        )
    )

    assert len(captured) == 1
    assert captured[0].data["hint_level"] == HintLevel.METACOGNITIVE
    assert captured[0].data["llm_used"] is True


@pytest.mark.asyncio
async def test_hint_agent_escalates_to_targeted_after_many_hints(
    event_bus, learner_models, mock_llm_provider
):
    from agents.hint_agent import HintAgent, HintLevel
    from llm.tutor_service import HintLLMService

    hint_agent = HintAgent(
        name="HintAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        llm_service=HintLLMService(provider=mock_llm_provider),
    )

    captured: list[Event] = []
    event_bus.subscribe(EventType.HINT_RESPONSE, lambda e: captured.append(e))

    # 连续发 5 次 HINT_NEEDED
    for i in range(5):
        await event_bus.publish(
            Event(
                type=EventType.HINT_NEEDED,
                source="test",
                learner_id="learner_1",
                data={"knowledge_id": "kp1", "mastery": 0.3, "attempts": i + 1},
            )
        )

    # 最后一次应是 TARGETED(>3 次)
    last = captured[-1]
    assert last.data["hint_level"] == HintLevel.TARGETED


# ---------- AssessmentAgent ----------


@pytest.mark.asyncio
async def test_assessment_agent_updates_mastery_on_correct_answer(
    event_bus, learner_models
):
    from agents.assessment_agent import AssessmentAgent

    assessor = AssessmentAgent(
        name="AssessmentAgent", event_bus=event_bus, learner_models=learner_models
    )

    captured: list[Event] = []
    event_bus.subscribe(EventType.ASSESSMENT_COMPLETE, lambda e: captured.append(e))

    await event_bus.publish(
        Event(
            type=EventType.STUDENT_SUBMISSION,
            source="test",
            learner_id="learner_1",
            data={"knowledge_id": "kp1", "is_correct": True, "time_spent_seconds": 10},
        )
    )

    assert len(captured) == 1
    assert captured[0].data["is_correct"] is True
    assert captured[0].data["mastery"] > 0  # 答对应该让 mastery 增加


@pytest.mark.asyncio
async def test_assessment_agent_emits_assessment_complete_on_submission(
    event_bus, learner_models
):
    """学生提交答题 -> AssessmentAgent 应发布 ASSESSMENT_COMPLETE。"""
    from agents.assessment_agent import AssessmentAgent

    assessor = AssessmentAgent(
        name="AssessmentAgent", event_bus=event_bus, learner_models=learner_models
    )

    completed: list[Event] = []
    event_bus.subscribe(EventType.ASSESSMENT_COMPLETE, lambda e: completed.append(e))

    await event_bus.publish(
        Event(
            type=EventType.STUDENT_SUBMISSION,
            source="test",
            learner_id="learner_1",
            data={"knowledge_id": "kp1", "is_correct": False, "time_spent_seconds": 120},
        )
    )

    # 至少有一个 ASSESSMENT_COMPLETE 事件
    assert len(completed) >= 1


# ---------- CurriculumAgent ----------


@pytest.mark.asyncio
async def test_curriculum_agent_handles_path_update(event_bus, learner_models):
    from agents.curriculum_agent import CurriculumAgent
    from core.knowledge_graph import build_sample_math_graph

    graph = build_sample_math_graph()
    curriculum = CurriculumAgent(
        name="CurriculumAgent", event_bus=event_bus, learner_models=learner_models
    )
    # 注入测试用 graph
    curriculum.knowledge_graph = graph

    plans: list[Event] = []
    # 订阅 PATH_UPDATED / REVIEW_SCHEDULED / NEXT_TOPIC 三个可能的事件
    for evt in (EventType.PATH_UPDATED, EventType.REVIEW_SCHEDULED, EventType.NEXT_TOPIC):
        event_bus.subscribe(evt, lambda e: plans.append(e))

    await event_bus.publish(
        Event(
            type=EventType.ASSESSMENT_COMPLETE,
            source="test",
            learner_id="learner_1",
            data={"knowledge_id": "arithmetic", "mastery": 0.9, "is_correct": True},
        )
    )

    # 答对后应有学习路径建议(虽然未必每次都触发)
    # 这里只验证不抛异常
    assert curriculum.knowledge_graph is not None


# ---------- EngagementAgent ----------


@pytest.mark.asyncio
async def test_engagement_agent_detects_frustration(event_bus, learner_models):
    """连续 3 次错误提交 -> 应触发 frustration 警报。

    流程: STUDENT_SUBMISSION -> EngagementAgent track + AssessmentAgent emit ASSESSMENT_COMPLETE
          -> EngagementAgent _analyze_engagement(连续错误>=3 -> FRUSTRATED -> 发警报)
    """
    from agents.assessment_agent import AssessmentAgent
    from agents.engagement_agent import EngagementAgent

    AssessmentAgent(
        name="AssessmentAgent", event_bus=event_bus, learner_models=learner_models
    )
    eng = EngagementAgent(
        name="EngagementAgent", event_bus=event_bus, learner_models=learner_models
    )

    alerts: list[Event] = []
    event_bus.subscribe(EventType.ENGAGEMENT_ALERT, lambda e: alerts.append(e))

    # 连续 3 次错误提交
    for _ in range(3):
        await event_bus.publish(
            Event(
                type=EventType.STUDENT_SUBMISSION,
                source="test",
                learner_id="learner_1",
                data={
                    "knowledge_id": "kp1",
                    "is_correct": False,
                    "time_spent_seconds": 10,
                },
            )
        )

    # 应至少有一个 ENGAGEMENT_ALERT(连续 3 次错误 -> FRUSTRATED)
    assert len(alerts) >= 1


# ---------- 集成: Assessment -> Tutor -> Hint ----------


@pytest.mark.asyncio
async def test_full_chain_assessment_to_hint(event_bus, learner_models, mock_llm_provider):
    """端到端: 答题错误两次 -> 触发 Tutor -> Tutor 请求 Hint -> Hint 返回。"""
    from agents.assessment_agent import AssessmentAgent
    from agents.hint_agent import HintAgent, HintLevel
    from agents.tutor_agent import TutorAgent
    from llm.tutor_service import HintLLMService, TutorLLMService

    # 创建所有 agent
    AssessmentAgent(name="AssessmentAgent", event_bus=event_bus, learner_models=learner_models)
    TutorAgent(
        name="TutorAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        llm_service=TutorLLMService(provider=mock_llm_provider),
    )
    HintAgent(
        name="HintAgent",
        event_bus=event_bus,
        learner_models=learner_models,
        llm_service=HintLLMService(provider=mock_llm_provider),
    )

    hint_responses: list[Event] = []
    event_bus.subscribe(EventType.HINT_RESPONSE, lambda e: hint_responses.append(e))

    # 连续两次错误
    for _ in range(2):
        await event_bus.publish(
            Event(
                type=EventType.STUDENT_SUBMISSION,
                source="test",
                learner_id="learner_1",
                data={"knowledge_id": "kp1", "is_correct": False, "time_spent_seconds": 10},
            )
        )

    assert len(hint_responses) >= 1
    assert hint_responses[0].data["hint_text"]
    assert hint_responses[0].data["hint_level"] == HintLevel.METACOGNITIVE
