"""Debate Agent -- Multi-Agent Debate 多 persona 辩论综合(P2#16b)。

核心职责:
1. 订阅 STUDENT_QUESTION 事件(仅在 data.debate_mode=True 时触发)
2. 启动 2-persona 辩论(socratic vs direct),N 轮互相批评+修订
3. Synthesizer 综合两版最终回复,产出 consensus
4. 发布 DEBATE_CONSENSUS 事件携带最终回复

设计原则:
- 显式触发: 默认不启用,需 debate_mode=True(避免 LLM 成本)
- 旁路解耦: 不修改 TutorAgent,DebateAgent 是可选增强路径
- 失败降级: LLM 不可用时静默跳过
- 可观测: 携带 rounds/personas/tokens metadata
"""

import logging
from typing import Any

from llm.debate_service import DebateLLMService

from .base_agent import BaseAgent
from core.event_bus import Event, EventType

logger = logging.getLogger(__name__)


class DebateAgent(BaseAgent):
    """Multi-Agent Debate Agent。

    订阅 STUDENT_QUESTION,但只在 data.debate_mode=True 时触发辩论。
    辩论完成后发布 DEBATE_CONSENSUS。
    """

    def __init__(
        self,
        *args,
        debate_service: DebateLLMService | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.debate_service = debate_service or DebateLLMService()

    @property
    def subscribed_events(self) -> list[EventType]:
        return [EventType.STUDENT_QUESTION]

    async def handle_event(self, event: Event) -> None:
        # 仅在显式 debate_mode=True 时触发
        if not event.data.get("debate_mode"):
            return

        await self._run_debate(event)

    async def _run_debate(self, event: Event) -> None:
        """运行辩论流程并发布 DEBATE_CONSENSUS。"""
        learner_id = event.learner_id
        knowledge_id = event.data.get("knowledge_id", "general")
        question = event.data.get("question", "") or event.data.get("message", "")
        # 从 learner model 推断 level + mastery(若可获取)
        level = event.data.get("level", "beginner")
        mastery = float(event.data.get("mastery", 0.0))

        if not question:
            logger.debug("[%s] debate skipped: no question", self.name)
            return

        try:
            result = await self.debate_service.run_debate(
                knowledge_id=knowledge_id,
                level=level,
                mastery=mastery,
                question=question,
            )
        except Exception:
            logger.exception("[%s] debate failed", self.name)
            return

        if not result.consensus:
            logger.debug("[%s] debate produced no consensus", self.name)
            return

        payload: dict[str, Any] = {
            "knowledge_id": knowledge_id,
            "question": question,
            "response": result.consensus,
            "teaching_style": "debate_synthesis",
            "difficulty_level": level,
            "socratic_final": result.socratic_final,
            "direct_final": result.direct_final,
            "rounds_completed": len(result.rounds),
            "regenerated": False,
            **result.metadata,
        }

        await self.emit(EventType.DEBATE_CONSENSUS, learner_id, payload)
        logger.info(
            "[%s] debate consensus published (rounds=%d, tokens=%d, learner=%s)",
            self.name,
            len(result.rounds),
            result.metadata.get("total_tokens", 0),
            learner_id,
        )
