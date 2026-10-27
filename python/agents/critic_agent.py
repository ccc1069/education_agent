"""Critic Agent -- LLM-as-judge 教学回复评估 + 自反思再生成(P2#16a)。

核心职责:
1. 订阅 TutorAgent 的 TEACHING_RESPONSE 事件
2. 用 LLM-as-judge 评估回复质量(4 维度 + overall 1-5 分)
3. 低分(overall <= 3)时触发自反思: 把 critique 作为反馈让 TutorLLM 重新生成
4. 发布 TEACHING_CRITICIZED 事件携带评估结果

设计原则:
- 失败降级: LLM 不可用或 JSON 解析失败时,跳过评估不阻塞主流程
- 单次重生成: 最多重生成一次,避免循环
- 不修改 TutorAgent: 通过事件订阅解耦,CriticAgent 是可选旁路
- 可观测: 携带 critic metadata(分数、模型、token、是否重生成)
- 默认后台评估: 不拖住 /submit 等 HTTP 响应;测试环境同步执行便于断言
"""

import asyncio
import logging
from typing import Any

from config.settings import settings
from llm.critic_service import CriticLLMService, CritiqueResult
from llm.tutor_service import TutorLLMService

from .base_agent import BaseAgent
from core.event_bus import Event, EventType

logger = logging.getLogger(__name__)


class CriticAgent(BaseAgent):
    """LLM-as-judge Critic Agent。

    订阅 TEACHING_RESPONSE,评估后发布 TEACHING_CRITICIZED。
    若评估低分,触发自反思再生成,发布新的 TEACHING_RESPONSE(带 regenerated=True)。
    """

    def __init__(
        self,
        *args,
        critic_service: CriticLLMService | None = None,
        tutor_service: TutorLLMService | None = None,
        run_inline: bool | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.critic_service = critic_service or CriticLLMService()
        self.tutor_service = tutor_service or TutorLLMService()
        # 防止重生成的事件再触发评估形成循环
        self._regenerating: set[str] = set()
        # 生产默认后台,避免 Tutor→Critic→Regen 串行 LLM 拖垮 HTTP
        if run_inline is None:
            run_inline = settings.env.lower() in ("test", "ci")
        self._run_inline = run_inline
        self._bg_tasks: set[asyncio.Task] = set()

    @property
    def subscribed_events(self) -> list[EventType]:
        return [EventType.TEACHING_RESPONSE]

    async def handle_event(self, event: Event) -> None:
        # 跳过自己发布的重生成事件,避免循环
        if event.data.get("regenerated") is True:
            return
        # 跳过 hint 转发(无 LLM 评估意义)
        if event.data.get("teaching_style") == "hint":
            return

        if self._run_inline:
            await self._evaluate_and_maybe_regenerate(event)
            return

        task = asyncio.create_task(
            self._safe_background_evaluate(event),
            name=f"critic-{event.id[:8]}",
        )
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _safe_background_evaluate(self, event: Event) -> None:
        try:
            await self._evaluate_and_maybe_regenerate(event)
        except Exception:
            logger.exception("[%s] background critique failed event=%s", self.name, event.id)

    async def _evaluate_and_maybe_regenerate(self, event: Event) -> None:
        """评估 -> 低分则重生成 -> 发布 TEACHING_CRITICIZED。"""
        learner_id = event.learner_id
        knowledge_id = event.data.get("knowledge_id", "")
        response_text = event.data.get("response", "")
        level = event.data.get("difficulty_level") or event.data.get("level") or "beginner"
        mastery = float(event.data.get("mastery", 0.0))
        is_correct = event.data.get("is_correct")
        question = event.data.get("question", "") or event.data.get("learner_message", "")
        llm_meta = {
            k: event.data[k]
            for k in ("llm_used", "model", "tokens", "latency_ms", "rag_used")
            if k in event.data
        }

        # 1. 评估
        critique = await self.critic_service.evaluate(
            knowledge_id=knowledge_id,
            level=level,
            mastery=mastery,
            is_correct=is_correct,
            teaching_response=response_text,
            learner_message=question,
        )

        if critique is None:
            # LLM 不可用,跳过(不发布 TEACHING_CRITICIZED,避免噪声)
            logger.debug("[%s] critic skipped (LLM unavailable)", self.name)
            return

        # 2. 发布评估结果(无论是否重生成)
        await self.emit(
            EventType.TEACHING_CRITICIZED,
            learner_id,
            self._build_critique_payload(event, critique),
        )

        # 3. 低分 -> 触发自反思再生成
        if critique.needs_regeneration:
            await self._regenerate(
                event=event,
                knowledge_id=knowledge_id,
                level=level,
                mastery=mastery,
                is_correct=is_correct,
                question=question,
                original_response=response_text,
                original_meta=llm_meta,
                critique=critique,
            )

    def _build_critique_payload(self, event: Event, critique: CritiqueResult) -> dict[str, Any]:
        """构造 TEACHING_CRITICIZED 事件 payload。"""
        return {
            "knowledge_id": event.data.get("knowledge_id", ""),
            "teaching_event_id": event.id,
            "overall": critique.overall,
            "scores": critique.scores,
            "critique": critique.critique,
            "needs_regeneration": critique.needs_regeneration,
            "critic_model": critique.model,
            "critic_tokens": critique.tokens,
        }

    async def _regenerate(
        self,
        event: Event,
        knowledge_id: str,
        level: str,
        mastery: float,
        is_correct: bool | None,
        question: str,
        original_response: str,
        original_meta: dict[str, Any],
        critique: CritiqueResult,
    ) -> None:
        """自反思再生成: 把 critique 作为反馈,重新调 TutorLLM。"""
        # 防循环
        if event.id in self._regenerating:
            return
        self._regenerating.add(event.id)
        try:
            new_text, regen_meta = await self.critic_service.regenerate(
                knowledge_id=knowledge_id,
                level=level,
                mastery=mastery,
                is_correct=is_correct,
                original_response=original_response,
                critique=critique.critique,
                learner_message=question,
            )
            # 发布重生成后的 TEACHING_RESPONSE(带 regenerated=True,
            # handle_event 会跳过此事件不再评估)
            payload = {
                "knowledge_id": knowledge_id,
                "response": new_text,
                "teaching_style": event.data.get("teaching_style", "socratic"),
                "difficulty_level": level,
                "citations": event.data.get("citations", []),
                **regen_meta,
                "critic_overall": critique.overall,
                "critic_critique": critique.critique,
            }
            await self.emit(EventType.TEACHING_RESPONSE, event.learner_id, payload)
            logger.info(
                "[%s] regenerated response (overall=%d, learner=%s)",
                self.name,
                critique.overall,
                event.learner_id,
            )
        finally:
            self._regenerating.discard(event.id)
