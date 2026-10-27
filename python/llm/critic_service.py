"""LLM-as-judge Critic 服务: 评估教学回复 + 自反思再生成。

设计:
- evaluate(): 调 LLM 对 TutorAgent 的回复打分(4 维度 + overall + critique)
- regenerate(): 把 critique 作为反馈,调 LLM 重新生成回复
- LLM 不可用时降级: 返回 None(跳过 critic 环节,不阻塞主流程)
- 严格 JSON 解析: 容忍 markdown 包裹与多余空白
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from llm.factory import get_llm_provider
from llm.prompts import (
    CRITIC_SYSTEM_PROMPT,
    build_critic_user_prompt,
    build_regeneration_user_prompt,
    build_tutor_user_prompt,
    TUTOR_SYSTEM_PROMPTS,
)
from llm.provider import LLMMessage, LLMProvider, LLMRole, LLMUnavailableError

logger = logging.getLogger(__name__)


class CriticParseError(Exception):
    """Critic LLM 返回的 JSON 解析失败。"""


@dataclass
class CritiqueResult:
    """Critic 评估结果。"""

    scores: dict[str, int]
    overall: int
    critique: str
    needs_regeneration: bool
    model: str
    tokens: int
    latency_ms: float


def _extract_json(text: str) -> dict[str, Any]:
    """从 LLM 输出中提取 JSON(容忍 ```json 包裹和前后空白)。"""
    if not text:
        raise CriticParseError("empty critic response")
    cleaned = text.strip()
    # 去除 markdown 代码块包裹
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    # 截取第一个 { 到最后一个 }(防止模型输出多余文本)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise CriticParseError(f"no JSON object found in: {cleaned[:200]!r}")
    payload = cleaned[start : end + 1]
    try:
        return json.loads(payload)
    except json.JSONDecodeError as e:
        raise CriticParseError(f"invalid JSON: {e}") from e


def _normalize_scores(raw: Any) -> dict[str, int]:
    """规范化 scores 字段为 dict[str, int]。"""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key in ("pedagogical", "appropriateness", "clarity", "engagement"):
        val = raw.get(key)
        if isinstance(val, (int, float)):
            out[key] = int(val)
        elif isinstance(val, str) and val.isdigit():
            out[key] = int(val)
    return out


class CriticLLMService:
    """LLM-as-judge 评估服务。

    用法:
        service = CriticLLMService()
        result = await service.evaluate(
            knowledge_id="algebra-basics",
            level="beginner",
            mastery=0.3,
            is_correct=False,
            teaching_response="让我问你...",
        )
        if result.needs_regeneration:
            new_text = await service.regenerate(..., critique=result.critique)
    """

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or get_llm_provider()

    async def evaluate(
        self,
        knowledge_id: str,
        level: str,
        mastery: float,
        is_correct: bool | None,
        teaching_response: str,
        learner_message: str = "",
    ) -> CritiqueResult | None:
        """评估教学回复。返回 None 表示 LLM 不可用(降级跳过)。"""
        system_prompt = CRITIC_SYSTEM_PROMPT
        user_prompt = build_critic_user_prompt(
            knowledge_id, level, mastery, is_correct, teaching_response, learner_message
        )
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
            LLMMessage(role=LLMRole.USER, content=user_prompt),
        ]

        try:
            response = await self.provider.complete(
                messages, temperature=0.2, max_tokens=300
            )
        except LLMUnavailableError as e:
            logger.warning("Critic LLM unavailable, skipping: %s", e)
            return None

        try:
            data = _extract_json(response.content)
        except CriticParseError as e:
            logger.warning("Critic JSON parse failed: %s; raw=%r", e, response.content[:200])
            return None

        scores = _normalize_scores(data.get("scores"))
        overall_raw = data.get("overall")
        if isinstance(overall_raw, (int, float)):
            overall = int(overall_raw)
        elif isinstance(overall_raw, str) and overall_raw.isdigit():
            overall = int(overall_raw)
        else:
            # 用 scores 平均值兜底
            overall = sum(scores.values()) // len(scores) if scores else 3

        critique = str(data.get("critique", ""))[:500]
        needs_reg = bool(data.get("needs_regeneration", overall <= 3))

        return CritiqueResult(
            scores=scores,
            overall=overall,
            critique=critique,
            needs_regeneration=needs_reg,
            model=response.model,
            tokens=response.total_tokens,
            latency_ms=response.latency_ms,
        )

    async def regenerate(
        self,
        knowledge_id: str,
        level: str,
        mastery: float,
        is_correct: bool | None,
        original_response: str,
        critique: str,
        learner_message: str = "",
        rag_context: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """根据 critique 重新生成教学回复。返回 (new_text, metadata)。

        失败时降级到原回复(避免阻断主流程)。
        """
        system_prompt = TUTOR_SYSTEM_PROMPTS.get(level, TUTOR_SYSTEM_PROMPTS["beginner"])
        user_prompt = build_regeneration_user_prompt(
            knowledge_id,
            level,
            mastery,
            is_correct,
            original_response,
            critique,
            learner_message,
        )
        if rag_context:
            user_prompt = f"{rag_context}\n\n{user_prompt}"

        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
            LLMMessage(role=LLMRole.USER, content=user_prompt),
        ]

        try:
            response = await self.provider.complete(
                messages, temperature=0.6, max_tokens=400
            )
            metadata = {
                "llm_used": True,
                "model": response.model,
                "tokens": response.total_tokens,
                "latency_ms": response.latency_ms,
                "regenerated": True,
                "rag_used": bool(rag_context),
            }
            return response.content, metadata
        except LLMUnavailableError as e:
            logger.warning("Critic regenerate LLM unavailable, keeping original: %s", e)
            return original_response, {
                "llm_used": False,
                "fallback": "original",
                "error": str(e),
                "regenerated": False,
                "rag_used": bool(rag_context),
            }

    async def generate_teaching_with_self_reflection(
        self,
        knowledge_id: str,
        level: str,
        mastery: float,
        is_correct: bool | None,
        question: str,
        initial_response: str,
        initial_meta: dict[str, Any],
        rag_context: str | None = None,
    ) -> tuple[str, dict[str, Any], CritiqueResult | None]:
        """完整自反思链(LangGraph): 评估 -> (低分则重生成) -> 返回最终回复。

        返回 (final_text, final_meta, critique)。
        critique 为 None 表示 LLM 不可用或解析失败,跳过了评估。
        """
        from llm.critic_graph import build_critic_reflection_graph

        graph = build_critic_reflection_graph(self)
        final = await graph.ainvoke(
            {
                "knowledge_id": knowledge_id,
                "level": level,
                "mastery": mastery,
                "is_correct": is_correct,
                "question": question,
                "initial_response": initial_response,
                "initial_meta": initial_meta,
                "rag_context": rag_context,
                "critique": None,
                "final_text": initial_response,
                "final_meta": initial_meta,
            }
        )
        return (
            str(final.get("final_text", initial_response)),
            dict(final.get("final_meta") or initial_meta),
            final.get("critique"),
        )
