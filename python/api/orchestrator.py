"""Agent 编排器 -- 初始化所有 Agent 并连接到 EventBus。

职责:
1. 创建 EventBus(注入事件持久化 callback)
2. 创建 LearnerModelService(缓存 + DB 同步)
3. 初始化 7 个 Agent（5 核心 + Critic/Debate，注入 service.cache）
4. 提供 API 层调用接口,处理 load -> publish -> save 的完整流程
"""

import logging

from agents import (
    AssessmentAgent,
    CriticAgent,
    CurriculumAgent,
    DebateAgent,
    EngagementAgent,
    HintAgent,
    TutorAgent,
)
from config.settings import settings
from core.event_bus import Event, EventBus, EventType
from core.knowledge_graph import build_sample_math_graph
from db.base import AsyncSessionLocal, init_db
from repositories import KnowledgeGraphRepository
from services import EventPersistenceService, LearnerModelService

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Agent 编排器: 管理所有 Agent、共享状态和持久化。"""

    def __init__(self) -> None:
        self.learner_service = LearnerModelService()
        self.event_persistence = EventPersistenceService()
        self.event_bus = EventBus(persist_callback=self.event_persistence)

        # 用 service 的缓存 dict 作为 Agent 的共享状态
        self.learner_models = self.learner_service.cache

        # 知识图谱(启动时从 DB 加载,空则种子)
        self.knowledge_graph = None  # 延迟初始化

        self.assessment = AssessmentAgent(
            name="AssessmentAgent",
            event_bus=self.event_bus,
            learner_models=self.learner_models,
        )
        self.tutor = TutorAgent(
            name="TutorAgent",
            event_bus=self.event_bus,
            learner_models=self.learner_models,
        )
        self.curriculum = CurriculumAgent(
            name="CurriculumAgent",
            event_bus=self.event_bus,
            learner_models=self.learner_models,
        )
        self.hint = HintAgent(
            name="HintAgent",
            event_bus=self.event_bus,
            learner_models=self.learner_models,
        )
        self.engagement = EngagementAgent(
            name="EngagementAgent",
            event_bus=self.event_bus,
            learner_models=self.learner_models,
        )
        # P2#16a: CriticAgent 旁路评估 Tutor 的回复(LLM-as-judge + 自反思)
        self.critic = CriticAgent(
            name="CriticAgent",
            event_bus=self.event_bus,
            learner_models=self.learner_models,
        )
        # P2#16b: DebateAgent 多 persona 辩论(显式 debate_mode=True 触发)
        self.debate = DebateAgent(
            name="DebateAgent",
            event_bus=self.event_bus,
            learner_models=self.learner_models,
        )

    async def initialize(self) -> None:
        """启动时调用: 验证 DB + 加载知识图谱。"""
        await init_db()
        await self._load_or_seed_knowledge_graph()
        logger.info("AgentOrchestrator initialized with 7 agents (incl. CriticAgent, DebateAgent)")

    async def _load_or_seed_knowledge_graph(self) -> None:
        """从 DB 加载知识图谱;若空则种子并写回。"""
        async with AsyncSessionLocal() as session:
            kg_repo = KnowledgeGraphRepository(session)
            graph = await kg_repo.load_full_graph()
            if not graph.nodes:
                logger.info("Knowledge graph empty in DB, seeding sample math graph...")
                sample = build_sample_math_graph()
                count = await kg_repo.seed_from_domain_graph(sample)
                await session.commit()
                self.knowledge_graph = sample
                logger.info("Seeded %d knowledge nodes", count)
            else:
                self.knowledge_graph = graph
                logger.info("Loaded knowledge graph with %d nodes", len(graph.nodes))

        # 同步到 CurriculumAgent(它在 __init__ 时用了 sample graph,这里覆盖)
        self.curriculum.knowledge_graph = self.knowledge_graph

    async def submit_answer(
        self, learner_id: str, knowledge_id: str, is_correct: bool, time_spent: float = 0
    ) -> list[Event]:
        """学生提交答案 -> 触发完整的 Agent 处理链。"""
        # 1. 预加载学习者模型到缓存
        model = await self.learner_service.load(learner_id)

        # 2. 记录答题(append-only)
        await self.learner_service.record_submission(
            learner_id, knowledge_id, is_correct, time_spent
        )

        # 3. 发布事件,触发 Agent 处理链(同步使用缓存)
        event = Event(
            type=EventType.STUDENT_SUBMISSION,
            source="api",
            learner_id=learner_id,
            data={
                "knowledge_id": knowledge_id,
                "is_correct": is_correct,
                "time_spent_seconds": time_spent,
            },
        )
        await self.event_bus.publish(event)

        # 4. 持久化修改后的模型
        await self.learner_service.save(model)

        # 5. 返回事件历史
        return self.event_bus.get_history(learner_id=learner_id, limit=20)

    async def ask_question(
        self,
        learner_id: str,
        knowledge_id: str,
        question: str,
        debate_mode: bool = False,
    ) -> list[Event]:
        """学生提问 -> 触发 Assessment + Tutor 处理；debate_mode 时启用 DebateAgent。"""
        model = await self.learner_service.load(learner_id)
        event = Event(
            type=EventType.STUDENT_QUESTION,
            source="api",
            learner_id=learner_id,
            data={
                "knowledge_id": knowledge_id,
                "question": question,
                "debate_mode": debate_mode,
            },
        )
        await self.event_bus.publish(event)
        await self.learner_service.save(model)
        return self.event_bus.get_history(learner_id=learner_id, limit=20)

    async def send_message(
        self, learner_id: str, message: str, knowledge_id: str = "general"
    ) -> list[Event]:
        """学生发送消息 -> 触发 Tutor 对话。"""
        model = await self.learner_service.load(learner_id)
        event = Event(
            type=EventType.STUDENT_MESSAGE,
            source="api",
            learner_id=learner_id,
            data={"message": message, "knowledge_id": knowledge_id},
        )
        await self.event_bus.publish(event)
        await self.learner_service.save(model)
        return self.event_bus.get_history(learner_id=learner_id, limit=20)

    def get_learner_progress(self, learner_id: str) -> dict:
        """获取学习者进度。

        progress 为 knowledge_id -> mastery 映射(与前端 ProgressPage / MSW 约定一致)。
        overall 为聚合统计,弱/强知识点列表一并返回。
        """
        model = self.learner_service.get_cached(learner_id)
        if model is None:
            return {"learner_id": learner_id, "status": "no_data"}
        return {
            "learner_id": learner_id,
            "progress": {
                kid: state.mastery for kid, state in model.knowledge_states.items()
            },
            "overall": model.get_overall_progress(),
            "weak_points": [
                {"id": s.knowledge_id, "mastery": s.mastery}
                for s in model.get_weak_points()
            ],
            "strong_points": [
                {"id": s.knowledge_id, "mastery": s.mastery}
                for s in model.get_strong_points()
            ],
        }

    async def record_practice_answer(
        self,
        learner_id: str,
        knowledge_id: str,
        is_correct: bool,
        time_spent: float = 0,
    ) -> dict:
        """练习题作答: 只更新 BKT 掌握度并落库,不触发 Tutor/Critic LLM 链。

        学习页 /submit 仍走完整 Agent 事件链;题库练习只需进度可见即可。
        """
        model = await self.learner_service.load(learner_id)
        await self.learner_service.record_submission(
            learner_id, knowledge_id, is_correct, time_spent
        )
        state = model.update_mastery(knowledge_id, is_correct)
        await self.learner_service.save(model)

        # 通知 Curriculum 等订阅方,但不走 Assessment→Tutor 的教学回复
        await self.event_bus.publish(
            Event(
                type=EventType.MASTERY_UPDATED,
                source="api.practice",
                learner_id=learner_id,
                data={
                    "knowledge_id": knowledge_id,
                    "mastery": state.mastery,
                    "level": state.level.value,
                    "attempts": state.attempts,
                    "streak": state.streak,
                    "is_correct": is_correct,
                },
            )
        )
        return {
            "knowledge_id": knowledge_id,
            "mastery": state.mastery,
            "level": state.level.value,
            "attempts": state.attempts,
        }
