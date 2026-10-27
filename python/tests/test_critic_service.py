"""CriticLLMService 单元测试: 评估 + 自反思再生成 + 降级。"""

import json
from typing import Any

import pytest

from llm.critic_service import (
    CriticLLMService,
    CriticParseError,
    _extract_json,
    _normalize_scores,
)
from llm.mock_provider import MockLLMProvider
from llm.provider import LLMError, LLMMessage, LLMProvider, LLMResponse, LLMUnavailableError


# ---------- 测试用可脚本化 Provider ----------


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
    """总是失败的 Provider,用于测试降级。"""

    def __init__(self) -> None:
        super().__init__(name="fail", model="fail-1.0", timeout=1.0, max_retries=1)
        self.retry_initial_delay = 0.0

    async def _call(self, messages, **kwargs):
        raise LLMError("simulated failure")


# ---------- _extract_json / _normalize_scores ----------


def test_extract_json_plain():
    data = _extract_json('{"overall": 4, "critique": "good"}')
    assert data == {"overall": 4, "critique": "good"}


def test_extract_json_with_markdown_fence():
    raw = '```json\n{"overall": 5, "scores": {"clarity": 5}}\n```'
    data = _extract_json(raw)
    assert data["overall"] == 5
    assert data["scores"]["clarity"] == 5


def test_extract_json_with_leading_text():
    raw = 'Here is my evaluation:\n{"overall": 3, "critique": "ok"}\nThanks.'
    data = _extract_json(raw)
    assert data["overall"] == 3


def test_extract_json_empty_raises():
    with pytest.raises(CriticParseError):
        _extract_json("")


def test_extract_json_no_braces_raises():
    with pytest.raises(CriticParseError):
        _extract_json("not json at all")


def test_extract_json_invalid_raises():
    with pytest.raises(CriticParseError):
        _extract_json('{"overall": , "critique": "bad"}')


def test_normalize_scores_full():
    raw = {"pedagogical": 4, "appropriateness": 5, "clarity": 3, "engagement": 4}
    out = _normalize_scores(raw)
    assert out == {"pedagogical": 4, "appropriateness": 5, "clarity": 3, "engagement": 4}


def test_normalize_scores_string_digits():
    raw = {"pedagogical": "4", "clarity": "5"}
    out = _normalize_scores(raw)
    assert out == {"pedagogical": 4, "clarity": 5}


def test_normalize_scores_ignores_garbage():
    raw = {"pedagogical": "abc", "clarity": None, "extra": 99}
    out = _normalize_scores(raw)
    assert out == {}


def test_normalize_scores_non_dict():
    assert _normalize_scores(None) == {}
    assert _normalize_scores("not a dict") == {}
    assert _normalize_scores([1, 2, 3]) == {}


# ---------- CriticLLMService.evaluate ----------


@pytest.mark.asyncio
async def test_evaluate_high_score():
    raw = json.dumps(
        {
            "scores": {
                "pedagogical": 5,
                "appropriateness": 5,
                "clarity": 4,
                "engagement": 5,
            },
            "overall": 5,
            "critique": "优秀,引导得当。",
            "needs_regeneration": False,
        },
        ensure_ascii=False,
    )
    service = CriticLLMService(provider=_ScriptedProvider([raw]))
    result = await service.evaluate(
        knowledge_id="algebra",
        level="beginner",
        mastery=0.3,
        is_correct=False,
        teaching_response="让我问你...",
    )
    assert result is not None
    assert result.overall == 5
    assert result.scores["pedagogical"] == 5
    assert result.needs_regeneration is False
    assert result.tokens == 30
    assert result.model == "scripted-1.0"


@pytest.mark.asyncio
async def test_evaluate_low_score_needs_regeneration():
    raw = json.dumps(
        {
            "scores": {
                "pedagogical": 2,
                "appropriateness": 3,
                "clarity": 2,
                "engagement": 2,
            },
            "overall": 2,
            "critique": "直接给了答案,违反苏格拉底原则。",
            "needs_regeneration": True,
        },
        ensure_ascii=False,
    )
    service = CriticLLMService(provider=_ScriptedProvider([raw]))
    result = await service.evaluate(
        knowledge_id="kp1",
        level="developing",
        mastery=0.5,
        is_correct=False,
        teaching_response="答案是 42。",
    )
    assert result is not None
    assert result.overall == 2
    assert result.needs_regeneration is True
    assert "答案" in result.critique


@pytest.mark.asyncio
async def test_evaluate_overall_inferred_from_scores_when_missing():
    """overall 字段缺失时,用 scores 平均值兜底。"""
    raw = json.dumps(
        {
            "scores": {
                "pedagogical": 4,
                "appropriateness": 4,
                "clarity": 4,
                "engagement": 4,
            },
            "critique": "良好。",
        },
        ensure_ascii=False,
    )
    service = CriticLLMService(provider=_ScriptedProvider([raw]))
    result = await service.evaluate(
        knowledge_id="kp1",
        level="beginner",
        mastery=0.3,
        is_correct=None,
        teaching_response="...",
    )
    assert result is not None
    assert result.overall == 4
    # needs_regeneration 默认由 overall<=3 推断
    assert result.needs_regeneration is False


@pytest.mark.asyncio
async def test_evaluate_returns_none_on_llm_unavailable():
    service = CriticLLMService(provider=_AlwaysFailsProvider())
    result = await service.evaluate(
        knowledge_id="kp1",
        level="beginner",
        mastery=0.3,
        is_correct=False,
        teaching_response="...",
    )
    assert result is None  # 降级跳过


@pytest.mark.asyncio
async def test_evaluate_returns_none_on_invalid_json():
    service = CriticLLMService(provider=_ScriptedProvider(["not a json at all"]))
    result = await service.evaluate(
        knowledge_id="kp1",
        level="beginner",
        mastery=0.3,
        is_correct=False,
        teaching_response="...",
    )
    assert result is None


# ---------- CriticLLMService.regenerate ----------


@pytest.mark.asyncio
async def test_regenerate_returns_new_text():
    service = CriticLLMService(provider=_ScriptedProvider([" regenerated response "]))
    new_text, meta = await service.regenerate(
        knowledge_id="kp1",
        level="beginner",
        mastery=0.3,
        is_correct=False,
        original_response="bad",
        critique="too direct",
    )
    assert new_text == " regenerated response "
    assert meta["regenerated"] is True
    assert meta["llm_used"] is True


@pytest.mark.asyncio
async def test_regenerate_falls_back_to_original_on_failure():
    service = CriticLLMService(provider=_AlwaysFailsProvider())
    new_text, meta = await service.regenerate(
        knowledge_id="kp1",
        level="beginner",
        mastery=0.3,
        is_correct=False,
        original_response="original text",
        critique="bad",
    )
    assert new_text == "original text"
    assert meta["regenerated"] is False
    assert meta["fallback"] == "original"


# ---------- generate_teaching_with_self_reflection ----------


@pytest.mark.asyncio
async def test_self_reflection_high_score_no_regeneration():
    """高分(overall=5)时不重生成。"""
    critique_json = json.dumps(
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
    provider = _ScriptedProvider([critique_json])
    service = CriticLLMService(provider=provider)

    final_text, final_meta, critique = await service.generate_teaching_with_self_reflection(
        knowledge_id="kp1",
        level="beginner",
        mastery=0.3,
        is_correct=False,
        question="什么是方程?",
        initial_response="原回复",
        initial_meta={"llm_used": True, "model": "mock"},
    )
    assert final_text == "原回复"
    assert critique is not None
    assert critique.overall == 5
    assert final_meta["regenerated"] is False
    assert final_meta["critic"]["overall"] == 5
    # 只调了 1 次 LLM(评估),没重生成
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_self_reflection_low_score_triggers_regeneration():
    """低分(overall=2)时触发重生成。"""
    critique_json = json.dumps(
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
    provider = _ScriptedProvider([critique_json, "regenerated text"])
    service = CriticLLMService(provider=provider)

    final_text, final_meta, critique = await service.generate_teaching_with_self_reflection(
        knowledge_id="kp1",
        level="beginner",
        mastery=0.3,
        is_correct=False,
        question="什么是方程?",
        initial_response="答案是 x=3。",
        initial_meta={"llm_used": True, "model": "mock"},
    )
    assert final_text == "regenerated text"
    assert critique.overall == 2
    assert final_meta["regenerated"] is True
    assert "critic" in final_meta
    assert final_meta["critic"]["overall"] == 2
    # 调了 2 次 LLM(评估 + 重生成)
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_self_reflection_skips_when_critic_unavailable():
    """Critic LLM 不可用时,跳过评估,返回原回复。"""
    service = CriticLLMService(provider=_AlwaysFailsProvider())
    final_text, final_meta, critique = await service.generate_teaching_with_self_reflection(
        knowledge_id="kp1",
        level="beginner",
        mastery=0.3,
        is_correct=False,
        question="q",
        initial_response="原回复",
        initial_meta={"llm_used": True},
    )
    assert final_text == "原回复"
    assert critique is None
    assert "critic" not in final_meta
