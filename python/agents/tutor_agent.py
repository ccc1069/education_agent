"""
Tutor Agent(教学Agent)-- 苏格拉底式提问教学。

核心职责:
1. 根据学生水平采用苏格拉底式提问,引导而非告知
2. 根据Assessment结果动态调整教学难度
3. 当学生卡住时,请求Hint Agent提供分级提示

LLM 集成(P0#3):
- 优先调用 LLM 生成自然语言教学回复
- LLM 不可用时降级到模板回复
- 响应中携带 llm_used 标记和 token 消耗

RAG 集成(P2#14):
- 可选注入 rag_service,生成回复前检索教材片段
- 检索结果作为 context 注入到 LLM prompt
- 响应 metadata 携带 rag_used 标记 + citations 列表
"""

import logging
from typing import Any

from llm.prompts import build_citations, build_rag_context
from llm.tutor_service import TutorLLMService

from .base_agent import BaseAgent
from core.event_bus import Event, EventType

logger = logging.getLogger(__name__)

SOCRATIC_PROMPTS = {
    "beginner": (
        "你是一位耐心的数学老师,学生刚开始学习这个知识点。\n"
        "请用最简单的语言和例子帮助学生理解概念。\n"
        "不要直接给答案,而是:\n"
        "1. 先问学生对相关基础概念是否了解\n"
        "2. 用生活化的类比帮助理解\n"
        "3. 给一个最简单的例题让学生尝试"
    ),
    "developing": (
        "你是一位苏格拉底式的数学老师,学生正在学习中。\n"
        "请通过提问引导学生思考:\n"
        "1. 问学生已经知道哪些相关知识\n"
        "2. 引导学生发现问题的关键步骤\n"
        "3. 当学生卡住时,给一个关键提示而非答案"
    ),
    "proficient": (
        "你是一位挑战型的数学老师,学生已经比较熟练。\n"
        "请:\n"
        "1. 提出更深层的思考问题(为什么?还有其他方法吗?)\n"
        "2. 引导学生发现知识点之间的联系\n"
        "3. 给出变式题目拓展思维"
    ),
    "mastered": (
        "你是一位高级数学导师,学生已掌握此知识点。\n"
        "请:\n"
        "1. 引导学生总结归纳方法论\n"
        "2. 布置综合性、跨知识点的挑战题\n"
        "3. 鼓励学生尝试教别人(费曼学习法)"
    ),
}


class TutorAgent(BaseAgent):
    """教学Agent:采用苏格拉底式提问教学法。"""

    def __init__(
        self,
        *args,
        llm_service: TutorLLMService | None = None,
        rag_service: Any | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._student_attempts: dict[str, int] = {}
        self.llm_service = llm_service or TutorLLMService()
        self.rag_service = rag_service  # 可选,无则不启用 RAG

    async def _retrieve_rag_context(self, knowledge_id: str, query: str = "") -> tuple[str, list]:
        """检索教材片段并构造 prompt context 段。

        Returns:
            (rag_context_str, citations_list)
        """
        if self.rag_service is None:
            return "", []
        try:
            query_text = query or knowledge_id
            chunks = await self.rag_service.search(
                query=query_text, top_k=3, min_score=0.7
            )
            if not chunks:
                return "", []
            chunk_dicts = [
                {
                    "content": c.content,
                    "document_title": c.document_title,
                    "document_id": c.document_id,
                    "chunk_id": c.chunk_id,
                    "score": c.score,
                }
                for c in chunks
            ]
            return build_rag_context(chunk_dicts), build_citations(chunk_dicts)
        except Exception as e:
            logger.warning("RAG retrieval failed, continuing without context: %s", e)
            return "", []

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.ASSESSMENT_COMPLETE,
            EventType.STUDENT_MESSAGE,
            EventType.HINT_RESPONSE,
            EventType.ENGAGEMENT_ALERT,
        ]

    async def handle_event(self, event: Event) -> None:
        if event.type == EventType.ASSESSMENT_COMPLETE:
            await self._handle_assessment(event)
        elif event.type == EventType.STUDENT_MESSAGE:
            await self._handle_student_message(event)
        elif event.type == EventType.HINT_RESPONSE:
            await self._handle_hint_response(event)
        elif event.type == EventType.ENGAGEMENT_ALERT:
            await self._handle_engagement_alert(event)

    async def _handle_assessment(self, event: Event) -> None:
        """根据评估结果调整教学策略。"""
        learner_id = event.learner_id
        knowledge_id = event.data.get("knowledge_id", "")
        mastery = event.data.get("mastery", 0.0)
        level = event.data.get("level", "beginner")
        is_correct = event.data.get("is_correct")

        if is_correct is False:
            attempt_key = f"{learner_id}:{knowledge_id}"
            attempts = self._student_attempts.get(attempt_key, 0) + 1
            self._student_attempts[attempt_key] = attempts

            if attempts >= 2:
                await self.emit(
                    EventType.HINT_NEEDED,
                    learner_id,
                    {
                        "knowledge_id": knowledge_id,
                        "mastery": mastery,
                        "attempts": attempts,
                        "level": level,
                    },
                )
                return

        rag_context, citations = await self._retrieve_rag_context(
            knowledge_id, query=event.data.get("question", "")
        )
        response, llm_meta = await self.llm_service.generate_teaching_response(
            knowledge_id=knowledge_id,
            level=level,
            mastery=mastery,
            is_correct=is_correct,
            question=event.data.get("question", ""),
            rag_context=rag_context or None,
        )

        await self.emit(
            EventType.TEACHING_RESPONSE,
            learner_id,
            {
                "knowledge_id": knowledge_id,
                "response": response,
                "teaching_style": "socratic",
                "difficulty_level": level,
                "prompt_template_used": level,
                "citations": citations,
                **llm_meta,
            },
        )

    async def _handle_student_message(self, event: Event) -> None:
        """处理学生消息。"""
        learner_id = event.learner_id
        message = event.data.get("message", "")
        knowledge_id = event.data.get("knowledge_id", "general")

        model = self.get_learner_model(learner_id)
        state = model.get_state(knowledge_id)

        rag_context, citations = await self._retrieve_rag_context(knowledge_id, query=message)
        response, llm_meta = await self.llm_service.generate_teaching_response(
            knowledge_id=knowledge_id,
            level=state.level.value,
            mastery=state.mastery,
            is_correct=None,
            question=message,
            rag_context=rag_context or None,
        )

        await self.emit(
            EventType.TEACHING_RESPONSE,
            learner_id,
            {
                "knowledge_id": knowledge_id,
                "response": response,
                "teaching_style": "socratic",
                "difficulty_level": state.level.value,
                "citations": citations,
                **llm_meta,
            },
        )

    async def _handle_hint_response(self, event: Event) -> None:
        """转发Hint Agent的回复给学生。"""
        await self.emit(
            EventType.TEACHING_RESPONSE,
            event.learner_id,
            {
                "knowledge_id": event.data.get("knowledge_id", ""),
                "response": event.data.get("hint_text", ""),
                "teaching_style": "hint",
                "hint_level": event.data.get("hint_level", 1),
            },
        )

    async def _handle_engagement_alert(self, event: Event) -> None:
        """响应Engagement Agent的警报,调整教学难度。"""
        alert_type = event.data.get("alert_type", "")
        if alert_type == "frustration":
            await self.emit(
                EventType.DIFFICULTY_ADJUSTED,
                event.learner_id,
                {
                    "action": "decrease",
                    "reason": "检测到学生挫败感",
                    "message": "我注意到你可能遇到了困难,让我们换一个角度来看这个问题,从更简单的地方开始。",
                },
            )
        elif alert_type == "boredom":
            await self.emit(
                EventType.DIFFICULTY_ADJUSTED,
                event.learner_id,
                {
                    "action": "increase",
                    "reason": "检测到学生可能感到无聊",
                    "message": "看起来这对你来说太简单了!让我给你一个更有挑战性的问题。",
                },
            )
