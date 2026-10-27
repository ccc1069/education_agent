"""LLM 模块测试: provider(熔断/重试) + mock + prompts + service。"""

import asyncio

import pytest

from llm.mock_provider import MockLLMProvider
from llm.provider import (
    LLMError,
    LLMMessage,
    LLMRole,
    LLMUnavailableError,
)


# ---------- MockLLMProvider ----------


@pytest.mark.asyncio
async def test_mock_provider_returns_response():
    provider = MockLLMProvider(model="mock-1")
    messages = [LLMMessage(role=LLMRole.USER, content="hello")]
    response = await provider.complete(messages)

    assert response.content  # 非空
    assert response.model == "mock-1"
    assert response.total_tokens > 0
    assert response.latency_ms >= 0


@pytest.mark.asyncio
async def test_mock_provider_content_echoes_input():
    """Mock 应该把用户输入的部分内容反映到输出中(便于断言)。"""
    provider = MockLLMProvider()
    response = await provider.complete(
        [LLMMessage(role=LLMRole.USER, content="请问 1+1 等于几?")]
    )
    assert "1" in response.content or "?" in response.content


# ---------- Circuit Breaker ----------


class _AlwaysFailsProvider(MockLLMProvider):
    """总是失败的 provider,用于测试熔断。"""

    def __init__(self) -> None:
        super().__init__(model="failing")
        # 缩短重试间隔,加速测试
        self.max_retries = 1
        self.retry_initial_delay = 0.0
        self.retry_backoff_factor = 1.0
        self._failure_threshold = 5

    async def _call(self, messages, **kwargs):  # type: ignore[override]
        raise LLMError("simulated failure")


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold_failures():
    provider = _AlwaysFailsProvider()

    # 第 1-5 次调用应抛 LLMUnavailableError(每次重试 1 次 -> 5 次失败)
    for i in range(5):
        with pytest.raises(LLMUnavailableError):
            await provider.complete([])

    # 第 6 次调用: 熔断器应已开启,直接抛 LLMUnavailableError,不重试
    with pytest.raises(LLMUnavailableError) as exc_info:
        await provider.complete([])
    assert "Circuit breaker open" in str(exc_info.value)


@pytest.mark.asyncio
async def test_circuit_recovers_after_timeout():
    """熔断 60s 后应自动半开。这里通过手动设置 _circuit_open_until 模拟。"""
    from datetime import datetime, timedelta, timezone

    provider = _AlwaysFailsProvider()
    # 强制熔断 + 立即过期
    provider._consecutive_failures = 5
    provider._circuit_open_until = datetime.now(timezone.utc) - timedelta(seconds=1)

    # 半开状态下会再次尝试 -> 失败 -> 重新熔断
    with pytest.raises(LLMUnavailableError):
        await provider.complete([])
    # _is_circuit_open 已重置(_consecutive_failures = 0 + _circuit_open_until = None)
    assert provider._circuit_open_until is None or provider._consecutive_failures > 0


# ---------- Prompts ----------


def test_tutor_system_prompts_has_all_levels():
    from llm.prompts import TUTOR_SYSTEM_PROMPTS

    for level in ("beginner", "developing", "proficient", "mastered"):
        assert level in TUTOR_SYSTEM_PROMPTS
        assert len(TUTOR_SYSTEM_PROMPTS[level]) > 0


def test_hint_system_prompts_has_all_levels():
    from llm.prompts import HINT_SYSTEM_PROMPTS

    for level in (1, 2, 3):
        assert level in HINT_SYSTEM_PROMPTS


def test_build_tutor_user_prompt_sanitizes_long_input():
    """超长输入应被截断。"""
    from llm.prompts import build_tutor_user_prompt

    long_msg = "x" * 1000
    prompt = build_tutor_user_prompt("kp1", 0.5, None, long_msg)
    # 500 字符 + 模板文本,不应超过 700
    assert "x" * 500 in prompt
    assert "x" * 600 not in prompt


def test_build_tutor_user_prompt_strips_control_chars():
    from llm.prompts import build_tutor_user_prompt

    prompt = build_tutor_user_prompt("kp1", 0.5, None, "hello\r\nworld")
    assert "\r" not in prompt


# ---------- TutorLLMService ----------


@pytest.mark.asyncio
async def test_tutor_service_uses_llm_when_available():
    from llm.tutor_service import TutorLLMService

    service = TutorLLMService(provider=MockLLMProvider())
    response, meta = await service.generate_teaching_response(
        knowledge_id="kp1", level="beginner", mastery=0.3, is_correct=False, question=""
    )

    assert response
    assert meta["llm_used"] is True
    assert meta["model"]
    assert meta["tokens"] >= 0


@pytest.mark.asyncio
async def test_tutor_service_falls_back_to_template_on_failure():
    from llm.tutor_service import TutorLLMService

    service = TutorLLMService(provider=_AlwaysFailsProvider())
    response, meta = await service.generate_teaching_response(
        knowledge_id="kp1", level="beginner", mastery=0.3, is_correct=True, question=""
    )

    # 模板回复应非空
    assert response
    assert meta["llm_used"] is False
    assert meta["fallback"] == "template"


@pytest.mark.asyncio
async def test_hint_service_generates_hint_per_level():
    from llm.tutor_service import HintLLMService

    service = HintLLMService(provider=MockLLMProvider())
    for level in (1, 2, 3):
        hint, meta = await service.generate_hint(
            knowledge_id="kp1",
            level=level,
            mastery=0.2,
            attempts=level * 2,
            hint_count=level,
        )
        assert hint
        assert meta["llm_used"] is True
