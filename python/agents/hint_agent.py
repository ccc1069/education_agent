"""
Hint Agent(提示Agent)-- 分级提示策略。

核心职责:
1. 收到提示请求后,根据学生尝试次数和mastery决定提示级别
2. 三级提示: 暗示(Metacognitive) -> 引导(Scaffolding) -> 直接答案(Targeted)
3. 目标: 85%的情况使用暗示或引导,仅15%给直接答案

LLM 集成(P0#3):
- 优先调用 LLM 生成个性化分级提示
- LLM 不可用时降级到模板提示

RAG 集成(P2#14):
- 可选注入 rag_service,生成提示前检索教材
- 检索结果作为 context 注入 LLM prompt
"""

import logging
from typing import Any

from llm.prompts import build_citations, build_rag_context
from llm.tutor_service import HintLLMService

from .base_agent import BaseAgent
from core.event_bus import Event, EventType

logger = logging.getLogger(__name__)


class HintLevel:
    METACOGNITIVE = 1  # 暗示: 引导学生反思思路
    SCAFFOLDING = 2  # 引导: 给出关键步骤提示
    TARGETED = 3  # 直接: 给出答案或具体解法


HINT_TEMPLATES = {
    HintLevel.METACOGNITIVE: {
        "description": "元认知暗示 - 引导学生反思自己的思考过程",
        "templates": [
            "想一想,这道题的题目里有哪些关键信息?你有没有全部用上?",
            "你能把这道题和之前学过的哪个类型联系起来吗?",
            "试试从结果反推,如果答案是XX,那过程应该是什么样的?",
            "画个图或者列个表,把已知条件整理一下,也许能看出规律。",
            "这道题有没有更简单的特殊情况?先从特殊情况入手试试。",
        ],
    },
    HintLevel.SCAFFOLDING: {
        "description": "脚手架引导 - 给出关键步骤但不给答案",
        "templates": [
            "这道题的关键是用到{concept}。你记得{concept}的公式/定义吗?",
            "第一步: 先{step1}。第二步: 然后{step2}。你试试看能不能完成。",
            "提示: 答案和{hint_value}有关。试着从这个方向思考。",
            "这道题和{similar_problem}很像。回忆一下那道题是怎么做的?",
        ],
    },
    HintLevel.TARGETED: {
        "description": "直接提示 - 给出具体解法(仅在多次尝试后使用)",
        "templates": [
            "好的,这道题的解法是: {solution_steps}。\n关键点是{key_point}。\n建议你自己重新做一遍,确保理解了。",
        ],
    },
}


class HintAgent(BaseAgent):
    """提示Agent: 实现分级提示策略。"""

    def __init__(
        self,
        *args,
        llm_service: HintLLMService | None = None,
        rag_service: Any | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._hint_history: dict[str, int] = {}
        self.llm_service = llm_service or HintLLMService()
        self.rag_service = rag_service  # 可选

    async def _retrieve_rag_context(self, knowledge_id: str) -> tuple[str, list]:
        """检索教材片段。"""
        if self.rag_service is None:
            return "", []
        try:
            chunks = await self.rag_service.search(
                query=knowledge_id, top_k=2, min_score=0.7
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
            logger.warning("RAG retrieval failed for hint, continuing without: %s", e)
            return "", []

    @property
    def subscribed_events(self) -> list[EventType]:
        return [EventType.HINT_NEEDED]

    async def handle_event(self, event: Event) -> None:
        if event.type == EventType.HINT_NEEDED:
            await self._provide_hint(event)

    def _determine_hint_level(
        self, learner_id: str, knowledge_id: str, mastery: float, attempts: int
    ) -> int:
        """
        决定提示级别的策略。

        规则:
        - 第1-2次尝试 -> Level 1(元认知暗示)
        - 第3-4次尝试 -> Level 2(脚手架引导)
        - 第5次及以上 -> Level 3(直接提示)
        - mastery极低(< 0.15) 且 attempts >= 3 -> 提前升级到 Level 3

        目标: 85%使用Level 1-2,15%使用Level 3
        """
        key = f"{learner_id}:{knowledge_id}"
        hint_count = self._hint_history.get(key, 0)

        if mastery < 0.15 and attempts >= 3:
            return HintLevel.TARGETED

        if hint_count <= 1:
            return HintLevel.METACOGNITIVE
        elif hint_count <= 3:
            return HintLevel.SCAFFOLDING
        else:
            return HintLevel.TARGETED

    async def _provide_hint(self, event: Event) -> None:
        """生成并发送分级提示。"""
        learner_id = event.learner_id
        knowledge_id = event.data.get("knowledge_id", "")
        mastery = event.data.get("mastery", 0.0)
        attempts = event.data.get("attempts", 1)

        level = self._determine_hint_level(learner_id, knowledge_id, mastery, attempts)

        key = f"{learner_id}:{knowledge_id}"
        self._hint_history[key] = self._hint_history.get(key, 0) + 1

        rag_context, citations = await self._retrieve_rag_context(knowledge_id)
        hint_text, llm_meta = await self.llm_service.generate_hint(
            knowledge_id=knowledge_id,
            level=level,
            mastery=mastery,
            attempts=attempts,
            hint_count=self._hint_history[key],
            rag_context=rag_context or None,
        )

        level_names = {
            HintLevel.METACOGNITIVE: "metacognitive",
            HintLevel.SCAFFOLDING: "scaffolding",
            HintLevel.TARGETED: "targeted",
        }

        logger.info(
            "[HintAgent] learner=%s, kp=%s, level=%s (%d/%d)",
            learner_id,
            knowledge_id,
            level_names[level],
            self._hint_history[key],
            attempts,
        )

        await self.emit(
            EventType.HINT_RESPONSE,
            learner_id,
            {
                "knowledge_id": knowledge_id,
                "hint_level": level,
                "hint_level_name": level_names[level],
                "hint_text": hint_text,
                "hint_count": self._hint_history[key],
                "description": HINT_TEMPLATES[level]["description"],
                "citations": citations,
                **llm_meta,
            },
        )
