"""题目库路由: 生成 + 审核 + 答题校验。

权限:
- 生成题目: 教师/管理员
- 审核题目(状态迁移): 教师/管理员
- 删除题目: 教师/管理员(且仅 draft/rejected/archived 状态)
- 列表/详情(不含答案): 所有认证用户
- 答题校验: 所有认证用户(仅 published 题目)
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit_helpers import write_audit
from auth import CurrentUser, get_current_active_user
from db.models import UserRole
from db.session import get_session_dep
from services import QuestionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/questions", tags=["questions"])


# ---------- Pydantic 请求模型 ----------


class GenerateQuestionRequest(BaseModel):
    """题目生成请求。"""

    knowledge_id: str = Field(min_length=1, max_length=64)
    question_type: str = Field(
        default="multiple_choice",
        description="multiple_choice / fill_blank / true_false / open_ended",
    )
    difficulty: int = Field(default=3, ge=1, le=5)
    use_rag: bool = Field(
        default=False, description="是否检索教材辅助命题(需已上传文档)"
    )


class VerifyAnswerRequest(BaseModel):
    """答案校验请求。"""

    student_answer: str = Field(min_length=1, max_length=2000)


class ReviewQuestionRequest(BaseModel):
    """题目审核请求(状态迁移)。"""

    new_status: str = Field(
        description="review / published / rejected / draft / archived"
    )


class QuestionSummary(BaseModel):
    """题目列表项(不含答案)。"""

    id: int
    knowledge_id: str
    question_type: str
    difficulty: int
    content: dict[str, Any]
    status: str
    created_by: int | None
    created_at: str | None
    updated_at: str | None


class QuestionDetail(QuestionSummary):
    """题目详情。教师/管理员含答案;学生视角 answer/analysis 为空。"""

    answer: str | None = None
    analysis: str | None = None


# ---------- 权限检查 ----------


def _require_staff(current: CurrentUser) -> None:
    """教师/管理员才能操作。"""
    if current.role not in (UserRole.TEACHER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers and admins can perform this action",
        )


def _get_rag_service(session: AsyncSession) -> Any | None:
    """惰性加载 RAGService(避免无文档时也要初始化)。"""
    try:
        from services import RAGService

        return RAGService(session)
    except Exception as e:
        logger.warning("Failed to init RAGService for question gen: %s", e)
        return None


# ---------- 路由 ----------


@router.post(
    "/generate",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def generate_question(
    req: GenerateQuestionRequest,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """生成题目(教师/管理员)。

    - LLM 出题 -> embedding 去重 -> 落库(draft 状态)
    - 高相似度(>=0.92)视为重复,返回已存在的题目
    - use_rag=true 时检索教材辅助命题(失败则降级为普通出题)
    - 返回字段含 id(与 question_id 同值)及完整详情,便于前端直接展示
    """
    _require_staff(current)
    service = QuestionService(session)
    rag_service = _get_rag_service(session) if req.use_rag else None
    try:
        result = await service.generate_question(
            knowledge_id=req.knowledge_id,
            question_type=req.question_type,
            difficulty=req.difficulty,
            created_by=current.id,
            rag_service=rag_service,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("question generate failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"题目生成失败: {e}",
        )
    return result


@router.get("", response_model=list[QuestionSummary])
async def list_questions(
    status_filter: str | None = Query(default=None, alias="status"),
    knowledge_id: str | None = Query(default=None),
    question_type: str | None = Query(default=None),
    difficulty: int | None = Query(default=None, ge=1, le=5),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """列出题目(所有认证用户,不含答案)。"""
    service = QuestionService(session)
    return await service.list_questions(
        status=status_filter,
        knowledge_id=knowledge_id,
        question_type=question_type,
        difficulty=difficulty,
        limit=limit,
        offset=offset,
    )


@router.get("/{question_id}", response_model=QuestionDetail)
async def get_question(
    question_id: int,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """获取题目详情。

    - 学生: 仅 published,且不含答案
    - 教师/管理员: 任意状态,含答案与解析
    """
    service = QuestionService(session)
    staff = current.role in (UserRole.TEACHER, UserRole.ADMIN)
    q = await service.get_question(question_id, include_answer=staff)
    if q is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Question not found"
        )
    if current.role == UserRole.STUDENT and q["status"] != "published":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Question not available for students",
        )
    return q


@router.post("/{question_id}/status", response_model=QuestionDetail)
async def review_question(
    question_id: int,
    req: ReviewQuestionRequest,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """审核题目: 状态机迁移(教师/管理员)。

    合法迁移路径:
    - draft -> review / archived
    - review -> published / rejected / draft
    - published -> archived
    - rejected -> draft / archived
    - archived -> draft
    """
    _require_staff(current)
    service = QuestionService(session)
    try:
        result = await service.review_question(
            question_id=question_id,
            new_status=req.new_status,
            reviewer_id=current.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Question not found"
        )
    return result


@router.post("/{question_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: int,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """删除题目(教师/管理员,仅 draft/rejected/archived 状态可删)。"""
    _require_staff(current)
    service = QuestionService(session)
    try:
        deleted = await service.delete_question(question_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Question not found"
        )
    return None


@router.post("/{question_id}/check", response_model=dict)
async def check_answer(
    question_id: int,
    req: VerifyAnswerRequest,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
    request: Request = None,
):
    """校验学生答案(仅 published 题目)。

    若当前用户绑定了学习者身份,同步更新 BKT 掌握度(不触发 Tutor LLM)。
    """
    service = QuestionService(session)
    try:
        result = await service.verify_answer(
            question_id=question_id,
            student_answer=req.student_answer,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Question not found"
        )

    if current.learner_public_id and request is not None:
        orch = request.app.state.orchestrator
        mastery = await orch.record_practice_answer(
            current.learner_public_id,
            result["knowledge_id"],
            bool(result["is_correct"]),
        )
        result["mastery"] = mastery

    await write_audit(
        session,
        actor=current.email,
        action="practice.submit",
        target=f"question:{question_id}",
        request=request,
        metadata={
            "knowledge_id": result.get("knowledge_id"),
            "is_correct": result.get("is_correct"),
            "learner_id": current.learner_public_id,
        },
    )
    return result
