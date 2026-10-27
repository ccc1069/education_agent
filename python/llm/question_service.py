"""LLM 题目生成服务: 生成 + 答案校验 + 难度评估。

设计:
- 优先调用 LLM 生成结构化题目(JSON schema)
- LLM 失败时降级到模板题目(保持服务可用)
- Mock provider 返回 JSON 字符串供解析
- 记录 token 消耗到响应 metadata
"""

import json
import logging
from typing import Any

from llm.factory import get_llm_provider
from llm.prompts import (
    QUESTION_GENERATION_SYSTEM_PROMPT,
    QUESTION_VERIFY_SYSTEM_PROMPT,
    build_question_generation_user_prompt,
    build_question_verify_user_prompt,
)
from llm.provider import LLMMessage, LLMProvider, LLMRole, LLMUnavailableError

logger = logging.getLogger(__name__)


class QuestionParseError(Exception):
    """LLM 输出无法解析为合法题目 JSON。"""


class QuestionLLMService:
    """题目生成的 LLM 服务。

    设计:
    - 优先调用 LLM 生成符合 schema 的 JSON
    - 解析失败时降级到模板题目
    - 支持 RAG context 注入(检索教材辅助命题)
    """

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or get_llm_provider()

    async def generate_question(
        self,
        knowledge_id: str,
        question_type: str,
        difficulty: int,
        rag_context: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """生成一道题目。

        Returns:
            (question_payload, metadata)
            question_payload: {content: dict, answer: str, analysis: str}
            metadata: {llm_used, model, tokens, latency_ms, rag_used}
        """
        user_prompt = build_question_generation_user_prompt(
            knowledge_id, question_type, difficulty, rag_context
        )
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=QUESTION_GENERATION_SYSTEM_PROMPT),
            LLMMessage(role=LLMRole.USER, content=user_prompt),
        ]

        try:
            response = await self.provider.complete(
                messages, temperature=0.7, max_tokens=500
            )
            payload = self._parse_question_json(response.content, question_type)
            metadata = {
                "llm_used": True,
                "model": response.model,
                "tokens": response.total_tokens,
                "latency_ms": response.latency_ms,
                "rag_used": bool(rag_context),
            }
            return payload, metadata
        except LLMUnavailableError as e:
            logger.warning("LLM unavailable for question gen, fallback to template: %s", e)
            payload = self._template_question(knowledge_id, question_type, difficulty)
            return payload, {
                "llm_used": False,
                "fallback": "template",
                "error": str(e),
                "rag_used": bool(rag_context),
            }
        except QuestionParseError as e:
            logger.warning("LLM output unparseable, fallback to template: %s", e)
            payload = self._template_question(knowledge_id, question_type, difficulty)
            return payload, {
                "llm_used": True,
                "fallback": "template",
                "error": f"parse_error: {e}",
                "rag_used": bool(rag_context),
            }

    async def verify_answer(
        self,
        question_stem: str,
        reference_answer: str,
        student_answer: str,
    ) -> tuple[bool, str, dict[str, Any]]:
        """校验学生答案。

        Returns:
            (is_correct, feedback, metadata)
        """
        user_prompt = build_question_verify_user_prompt(
            question_stem, reference_answer, student_answer
        )
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=QUESTION_VERIFY_SYSTEM_PROMPT),
            LLMMessage(role=LLMRole.USER, content=user_prompt),
        ]

        try:
            response = await self.provider.complete(
                messages, temperature=0.0, max_tokens=150
            )
            is_correct, feedback = self._parse_verify_json(response.content)
            metadata = {
                "llm_used": True,
                "model": response.model,
                "tokens": response.total_tokens,
                "latency_ms": response.latency_ms,
            }
            return is_correct, feedback, metadata
        except (LLMUnavailableError, QuestionParseError) as e:
            logger.warning("LLM verify failed, fallback to exact match: %s", e)
            is_correct = student_answer.strip() == reference_answer.strip()
            return is_correct, "自动判定(严格匹配)" if not is_correct else "正确", {
                "llm_used": False,
                "fallback": "exact_match",
                "error": str(e),
            }

    def _parse_question_json(
        self, content: str, question_type: str
    ) -> dict[str, Any]:
        """解析 LLM 输出为题目 payload。

        Returns:
            {content: dict, answer: str, analysis: str}
        """
        text = content.strip()
        # 去除 markdown code fence
        if text.startswith("```"):
            lines = text.split("\n")
            # 去掉首行 ``` 和末行 ```
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise QuestionParseError(f"invalid JSON: {e}") from e

        if not isinstance(data, dict):
            raise QuestionParseError(f"expected object, got {type(data).__name__}")

        # 按 schema 校验
        if question_type == "multiple_choice":
            return self._validate_multiple_choice(data)
        elif question_type == "fill_blank":
            return self._validate_fill_blank(data)
        elif question_type == "true_false":
            return self._validate_true_false(data)
        elif question_type == "open_ended":
            return self._validate_open_ended(data)
        else:
            raise QuestionParseError(f"unsupported question_type: {question_type}")

    def _validate_multiple_choice(self, data: dict[str, Any]) -> dict[str, Any]:
        stem = str(data.get("stem", "")).strip()
        options = data.get("options", [])
        answer_key = str(data.get("answer_key", "")).strip()
        analysis = str(data.get("analysis", "")).strip()

        if not stem:
            raise QuestionParseError("missing stem")
        if not isinstance(options, list) or len(options) < 2:
            raise QuestionParseError("options must be a list with at least 2 items")
        if not answer_key:
            raise QuestionParseError("missing answer_key")

        normalized_options = []
        keys = set()
        for opt in options:
            if not isinstance(opt, dict):
                raise QuestionParseError("option must be object")
            key = str(opt.get("key", "")).strip()
            text = str(opt.get("text", "")).strip()
            if not key or not text:
                raise QuestionParseError("option missing key/text")
            if key in keys:
                raise QuestionParseError(f"duplicate option key: {key}")
            keys.add(key)
            normalized_options.append({"key": key, "text": text})

        if answer_key not in keys:
            raise QuestionParseError(
                f"answer_key '{answer_key}' not in options {sorted(keys)}"
            )

        return {
            "content": {
                "stem": stem,
                "options": normalized_options,
                "answer_key": answer_key,
            },
            "answer": answer_key,
            "analysis": analysis,
        }

    def _validate_fill_blank(self, data: dict[str, Any]) -> dict[str, Any]:
        stem = str(data.get("stem", "")).strip()
        answer = str(data.get("answer", "")).strip()
        analysis = str(data.get("analysis", "")).strip()
        if not stem:
            raise QuestionParseError("missing stem")
        if not answer:
            raise QuestionParseError("missing answer")
        return {
            "content": {"stem": stem},
            "answer": answer,
            "analysis": analysis,
        }

    def _validate_true_false(self, data: dict[str, Any]) -> dict[str, Any]:
        stem = str(data.get("stem", "")).strip()
        answer = data.get("answer")
        analysis = str(data.get("analysis", "")).strip()
        if not stem:
            raise QuestionParseError("missing stem")
        if not isinstance(answer, bool):
            raise QuestionParseError("answer must be boolean")
        return {
            "content": {"stem": stem},
            "answer": "true" if answer else "false",
            "analysis": analysis,
        }

    def _validate_open_ended(self, data: dict[str, Any]) -> dict[str, Any]:
        stem = str(data.get("stem", "")).strip()
        reference_answer = str(data.get("reference_answer", "")).strip()
        analysis = str(data.get("analysis", "")).strip()
        if not stem:
            raise QuestionParseError("missing stem")
        if not reference_answer:
            raise QuestionParseError("missing reference_answer")
        return {
            "content": {"stem": stem, "reference_answer": reference_answer},
            "answer": reference_answer,
            "analysis": analysis,
        }

    def _parse_verify_json(self, content: str) -> tuple[bool, str]:
        """解析答案校验 JSON。"""
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise QuestionParseError(f"invalid verify JSON: {e}") from e

        if not isinstance(data, dict):
            raise QuestionParseError("verify output must be object")
        is_correct = bool(data.get("is_correct", False))
        feedback = str(data.get("feedback", "")).strip() or ("正确" if is_correct else "错误")
        return is_correct, feedback

    def _template_question(
        self, knowledge_id: str, question_type: str, difficulty: int
    ) -> dict[str, Any]:
        """LLM 不可用时的兜底题目模板。"""
        kid = (knowledge_id or "此知识点")[:64]
        if question_type == "multiple_choice":
            return {
                "content": {
                    "stem": f"关于「{kid}」的难度 {difficulty} 选择题(模板)",
                    "options": [
                        {"key": "A", "text": "选项 A"},
                        {"key": "B", "text": "选项 B"},
                        {"key": "C", "text": "选项 C"},
                        {"key": "D", "text": "选项 D"},
                    ],
                    "answer_key": "A",
                },
                "answer": "A",
                "analysis": f"考查 {kid} 的基础概念。",
            }
        elif question_type == "fill_blank":
            return {
                "content": {"stem": f"{kid}的核心概念是 ___(模板)"},
                "answer": "概念",
                "analysis": f"考查 {kid} 的定义。",
            }
        elif question_type == "true_false":
            return {
                "content": {"stem": f"掌握 {kid} 即可解决所有相关问题。(模板)"},
                "answer": "false",
                "analysis": "知识点需结合具体情境应用。",
            }
        else:  # open_ended
            return {
                "content": {
                    "stem": f"请用自己的话解释 {kid} 并举例。(模板)",
                    "reference_answer": f"{kid} 的定义 + 应用示例",
                },
                "answer": f"{kid} 的定义 + 应用示例",
                "analysis": "考查概念理解与举例能力。",
            }
