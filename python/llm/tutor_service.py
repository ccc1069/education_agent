"""LLM 教学服务: 封装 Tutor 和 Hint 的 LLM 调用 + 模板降级。"""

import logging
from typing import Any

from llm.factory import get_llm_provider
from llm.prompts import (
    HINT_SYSTEM_PROMPTS,
    TUTOR_SYSTEM_PROMPTS,
    build_hint_user_prompt,
    build_rag_context,
    build_tutor_user_prompt,
)
from llm.provider import LLMProvider, LLMUnavailableError, LLMMessage, LLMRole

logger = logging.getLogger(__name__)


class TutorLLMService:
    """Tutor Agent 的 LLM 服务。

    设计:
    - 优先调用 LLM 生成苏格拉底式回复
    - LLM 失败时降级到模板回复(保持服务可用)
    - 记录 token 消耗到响应 metadata
    - 支持 RAG context 注入(把检索到的教材片段塞进 user prompt)
    """

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or get_llm_provider()

    async def generate_teaching_response(
        self,
        knowledge_id: str,
        level: str,
        mastery: float,
        is_correct: bool | None,
        question: str = "",
        recent_attempts: list[dict[str, Any]] | None = None,
        rag_context: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """生成教学回复。返回 (response_text, metadata)。

        Args:
            rag_context: RAG 检索得到的参考资料段(可选,已格式化)
        """
        system_prompt = TUTOR_SYSTEM_PROMPTS.get(level, TUTOR_SYSTEM_PROMPTS["beginner"])
        user_prompt = build_tutor_user_prompt(
            knowledge_id, mastery, is_correct, question, recent_attempts
        )
        if rag_context:
            user_prompt = f"{rag_context}\n\n{user_prompt}"

        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
            LLMMessage(role=LLMRole.USER, content=user_prompt),
        ]

        try:
            response = await self.provider.complete(messages, temperature=0.7, max_tokens=400)
            metadata = {
                "llm_used": True,
                "model": response.model,
                "tokens": response.total_tokens,
                "latency_ms": response.latency_ms,
                "rag_used": bool(rag_context),
            }
            return response.content, metadata
        except LLMUnavailableError as e:
            logger.warning("LLM unavailable, falling back to template: %s", e)
            return self._template_response(knowledge_id, mastery, is_correct, question), {
                "llm_used": False,
                "fallback": "template",
                "error": str(e),
                "rag_used": bool(rag_context),
            }

    def _template_response(
        self,
        knowledge_id: str,
        mastery: float,
        is_correct: bool | None,
        question: str,
    ) -> str:
        """LLM 不可用时的兜底模板(保留原模板逻辑)。"""
        if is_correct is True:
            return (
                f"很好!你在「{knowledge_id}」上的表现不错。当前掌握度:{mastery:.0%}。\n"
                f"让我问你一个更深入的问题:你能用自己的话解释一下这个概念吗?"
            )
        elif is_correct is False:
            return (
                f"没关系,让我们一起来分析「{knowledge_id}」。\n"
                f"先不看答案,我想问你几个问题:\n"
                f"1. 你觉得这道题考查的是什么知识点?\n"
                f"2. 你做题的时候卡在了哪一步?\n"
                f"3. 能不能先试试用最简单的数字代入看看?"
            )
        else:
            return (
                f"好的,关于「{knowledge_id}」,你的问题是:{question}\n"
                f"在我回答之前,让我先问你:你对这个知识点已经了解了哪些内容?"
            )


class HintLLMService:
    """Hint Agent 的 LLM 服务。"""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or get_llm_provider()

    async def generate_hint(
        self,
        knowledge_id: str,
        level: int,
        mastery: float,
        attempts: int,
        hint_count: int,
        rag_context: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """生成分级提示。返回 (hint_text, metadata)。"""
        system_prompt = HINT_SYSTEM_PROMPTS.get(level, HINT_SYSTEM_PROMPTS[1])
        user_prompt = build_hint_user_prompt(knowledge_id, mastery, attempts, hint_count)
        if rag_context:
            user_prompt = f"{rag_context}\n\n{user_prompt}"

        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
            LLMMessage(role=LLMRole.USER, content=user_prompt),
        ]

        try:
            response = await self.provider.complete(messages, temperature=0.5, max_tokens=300)
            metadata = {
                "llm_used": True,
                "model": response.model,
                "tokens": response.total_tokens,
                "latency_ms": response.latency_ms,
                "rag_used": bool(rag_context),
            }
            return response.content, metadata
        except LLMUnavailableError as e:
            logger.warning("LLM unavailable for hint, falling back to template: %s", e)
            return self._template_hint(knowledge_id, level), {
                "llm_used": False,
                "fallback": "template",
                "error": str(e),
                "rag_used": bool(rag_context),
            }

    def _template_hint(self, knowledge_id: str, level: int) -> str:
        """LLM 不可用时的兜底模板。"""
        if level == 1:
            return (
                f"💡 关于「{knowledge_id}」的提示:\n"
                f"想一想,这道题的题目里有哪些关键信息?你有没有全部用上?"
            )
        elif level == 2:
            return (
                f"📝 关于「{knowledge_id}」的引导提示:\n"
                f"这道题的关键是理解{knowledge_id}的核心概念。\n"
                f"试着回忆一下相关的公式或定义,然后一步步来。"
            )
        else:
            return (
                f"📖 关于「{knowledge_id}」的详细解答:\n"
                f"让我来帮你梳理一下解题思路。\n"
                f"这次我会给你更详细的指导,但请你一定要自己重做一遍。"
            )
