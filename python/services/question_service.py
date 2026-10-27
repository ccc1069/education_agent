"""QuestionService: 题目生成 + 题库管理 + 答案校验。

职责:
1. generate_question: LLM 生成 -> embedding 去重 -> 落库(draft 状态)
2. list_questions: 多条件过滤
3. review_question: 状态机迁移(draft -> review -> published / rejected)
4. verify_answer: LLM 校验学生答案
5. delete_question: 删除题目
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import QuestionORM
from llm.question_service import QuestionLLMService
from rag import EmbeddingProvider, ScoredChunk, cosine_similarity, get_embedding_provider
from repositories import QuestionRepository

logger = logging.getLogger(__name__)


# 合法状态机迁移
VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"review", "archived"},
    "review": {"published", "rejected", "draft"},
    "published": {"archived"},
    "rejected": {"draft", "archived"},
    "archived": {"draft"},
}

VALID_QUESTION_TYPES = {
    "multiple_choice",
    "fill_blank",
    "true_false",
    "open_ended",
}


class QuestionService:
    """题目生成与题库管理服务。"""

    def __init__(
        self,
        session: AsyncSession,
        llm_service: QuestionLLMService | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.session = session
        self.repo = QuestionRepository(session)
        self.llm_service = llm_service or QuestionLLMService()
        self.embedding_provider = embedding_provider or get_embedding_provider()

    async def generate_question(
        self,
        knowledge_id: str,
        question_type: str,
        difficulty: int,
        created_by: int | None = None,
        rag_service: Any | None = None,
        dedup_threshold: float = 0.92,
    ) -> dict[str, Any]:
        """生成题目: LLM 出题 -> embedding 去重 -> 落库 draft 状态。

        Args:
            knowledge_id: 知识点 ID
            question_type: multiple_choice / fill_blank / true_false / open_ended
            difficulty: 1-5
            created_by: 创建者 user_id
            rag_service: 可选,检索教材辅助命题
            dedup_threshold: 相似度阈值,>= 该值视为重复(返回已存在的题目)

        Returns:
            含 id / question_id / is_duplicate 及完整详情字段的 dict
        """
        if question_type not in VALID_QUESTION_TYPES:
            raise ValueError(f"unsupported question_type: {question_type}")
        if not (1 <= difficulty <= 5):
            raise ValueError("difficulty must be in [1, 5]")
        if not knowledge_id or not knowledge_id.strip():
            raise ValueError("knowledge_id cannot be empty")

        rag_context = await self._retrieve_rag_context(knowledge_id, rag_service)
        payload, llm_meta = await self.llm_service.generate_question(
            knowledge_id=knowledge_id,
            question_type=question_type,
            difficulty=difficulty,
            rag_context=rag_context or None,
        )

        # 计算 embedding 用于去重;失败则跳过去重,仍允许落库
        embedding_text = self._embedding_text(payload["content"], question_type)
        embedding: list[float] | None
        try:
            embedding = await self.embedding_provider.embed(embedding_text)
        except Exception as e:
            logger.warning("embedding failed, skip dedup: %s", e)
            embedding = None
            llm_meta = {**(llm_meta or {}), "embedding_skipped": True, "embedding_error": str(e)}

        if embedding is not None:
            existing = await self._find_duplicate(embedding, dedup_threshold)
            if existing is not None:
                logger.info(
                    "Question duplicate detected: existing_id=%d knowledge_id=%s",
                    existing.id,
                    knowledge_id,
                )
                return self._generate_result_dict(
                    existing, is_duplicate=True, llm_meta=llm_meta
                )

        question = QuestionORM(
            knowledge_id=knowledge_id,
            question_type=question_type,
            difficulty=difficulty,
            content=payload["content"],
            answer=payload["answer"],
            analysis=payload["analysis"],
            status="draft",
            content_embedding=embedding,
            created_by=created_by,
            metadata_={},
        )
        await self.repo.add(question)
        await self.session.commit()

        logger.info(
            "Question generated: id=%d knowledge_id=%s type=%s difficulty=%d",
            question.id,
            knowledge_id,
            question_type,
            difficulty,
        )
        return self._generate_result_dict(
            question, is_duplicate=False, llm_meta=llm_meta
        )

    def _generate_result_dict(
        self,
        q: QuestionORM,
        *,
        is_duplicate: bool,
        llm_meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """生成接口回包: 兼容 question_id,同时带 id 与完整详情字段。"""
        d = self._to_dict(q, include_answer=True)
        d["question_id"] = q.id
        d["is_duplicate"] = is_duplicate
        d["llm_meta"] = llm_meta or {}
        return d

    async def _retrieve_rag_context(
        self, knowledge_id: str, rag_service: Any | None
    ) -> str:
        """可选: 检索教材辅助命题。"""
        if rag_service is None:
            return ""
        try:
            from llm.prompts import build_rag_context

            chunks = await rag_service.search(
                query=knowledge_id, top_k=2, min_score=0.7
            )
            if not chunks:
                return ""
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
            return build_rag_context(chunk_dicts)
        except Exception as e:
            logger.warning("RAG retrieval failed for question gen: %s", e)
            # PG 在语句失败后整段事务 aborted,必须 rollback 才能继续写库/查重
            try:
                await self.session.rollback()
            except Exception:
                pass
            return ""

    def _embedding_text(self, content: dict[str, Any], question_type: str) -> str:
        """从题目 content 中提取用于 embedding 的文本。"""
        stem = str(content.get("stem", ""))
        if question_type == "multiple_choice":
            options = content.get("options", [])
            opt_text = " ".join(
                f"{o.get('key','')} {o.get('text','')}" for o in options
            )
            return f"{stem} {opt_text}".strip()
        return stem

    async def _find_duplicate(
        self, embedding: list[float], threshold: float
    ) -> QuestionORM | None:
        """遍历已有题目 embedding,找相似度 >= threshold 的。"""
        if not embedding:
            return None
        existing = await self.repo.get_all_embeddings()
        for q in existing:
            if not q.content_embedding:
                continue
            score = cosine_similarity(embedding, q.content_embedding)
            if score >= threshold:
                return q
        return None

    async def list_questions(
        self,
        status: str | None = None,
        knowledge_id: str | None = None,
        question_type: str | None = None,
        difficulty: int | None = None,
        created_by: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """列出题目(简化返回)。"""
        questions = await self.repo.list_questions(
            status=status,
            knowledge_id=knowledge_id,
            question_type=question_type,
            difficulty=difficulty,
            created_by=created_by,
            limit=limit,
            offset=offset,
        )
        return [self._to_dict(q) for q in questions]

    async def get_question(
        self, question_id: int, include_answer: bool = False
    ) -> dict[str, Any] | None:
        """获取单个题目详情。

        Args:
            include_answer: True 时返回 answer/analysis(教师/管理员或答题校验后)
        """
        q = await self.repo.get_by_id(question_id)
        if q is None:
            return None
        return self._to_dict(q, include_answer=include_answer)

    async def review_question(
        self,
        question_id: int,
        new_status: str,
        reviewer_id: int | None = None,
    ) -> dict[str, Any] | None:
        """审核题目: 状态机迁移。

        合法迁移:
        - draft -> review / archived
        - review -> published / rejected / draft
        - published -> archived
        - rejected -> draft / archived
        - archived -> draft
        """
        q = await self.repo.get_by_id(question_id)
        if q is None:
            return None
        if new_status not in VALID_TRANSITIONS.get(q.status, set()):
            raise ValueError(
                f"invalid transition: {q.status} -> {new_status}"
            )
        await self.repo.update_status(question_id, new_status, reviewer_id=reviewer_id)
        await self.session.commit()
        logger.info(
            "Question reviewed: id=%d %s -> %s", question_id, q.status, new_status
        )
        refreshed = await self.repo.get_by_id(question_id)
        return self._to_dict(refreshed, include_answer=True) if refreshed else None

    async def verify_answer(
        self, question_id: int, student_answer: str
    ) -> dict[str, Any] | None:
        """校验学生答案(只允许 published 题目)。"""
        q = await self.repo.get_by_id(question_id)
        if q is None:
            return None
        if q.status != "published":
            raise ValueError(f"question not published (status={q.status})")

        is_correct, feedback, llm_meta = await self.llm_service.verify_answer(
            question_stem=self._embedding_text(q.content, q.question_type),
            reference_answer=q.answer,
            student_answer=student_answer,
        )
        return {
            "question_id": question_id,
            "knowledge_id": q.knowledge_id,
            "is_correct": is_correct,
            "feedback": feedback,
            "reference_answer": q.answer,
            "llm_meta": llm_meta,
        }

    async def delete_question(self, question_id: int) -> bool:
        """删除题目(仅 draft / rejected / archived 状态可删)。"""
        q = await self.repo.get_by_id(question_id)
        if q is None:
            return False
        if q.status in ("review", "published"):
            raise ValueError(
                f"cannot delete question in status={q.status}, archive first"
            )
        await self.repo.delete(q)
        await self.session.commit()
        logger.info("Question deleted: id=%d", question_id)
        return True

    def _to_dict(
        self, q: QuestionORM, include_answer: bool = False
    ) -> dict[str, Any]:
        """ORM 转 dict。学生视角不返回答案。"""
        d: dict[str, Any] = {
            "id": q.id,
            "knowledge_id": q.knowledge_id,
            "question_type": q.question_type,
            "difficulty": q.difficulty,
            "content": q.content,
            "status": q.status,
            "created_by": q.created_by,
            "created_at": q.created_at.isoformat() if q.created_at else None,
            "updated_at": q.updated_at.isoformat() if q.updated_at else None,
        }
        if include_answer:
            d["answer"] = q.answer
            d["analysis"] = q.analysis
        return d
