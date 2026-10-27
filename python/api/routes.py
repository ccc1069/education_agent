"""REST API 路由(业务接口,需认证)。"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit_helpers import write_audit
from auth import CurrentUser, get_current_active_user, require_student
from db.models import UserRole
from db.session import get_session_dep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["education"])


# ---------- Pydantic 请求模型 ----------


class SubmitAnswerRequest(BaseModel):
    """答题请求。learner_id 从 token 推断,不再放 body。"""

    knowledge_id: str
    is_correct: bool
    time_spent_seconds: float = 0.0


class AskQuestionRequest(BaseModel):
    knowledge_id: str
    question: str = Field(min_length=1, max_length=2000)
    debate_mode: bool = False


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    knowledge_id: str = "general"


# ---------- 健康检查(公开) ----------


@router.get("/health")
async def health_check():
    """健康检查(无需认证,供 K8s probe 用)。"""
    return {"status": "ok", "service": "multi-agent-education", "agents": 5}


# ---------- 业务接口(需认证) ----------


@router.post("/submit")
async def submit_answer(
    req: SubmitAnswerRequest,
    request: Request,
    current: CurrentUser = Depends(require_student()),
    session: AsyncSession = Depends(get_session_dep),
):
    """学生提交答题结果。learner_id 来自 token。"""
    orch = request.app.state.orchestrator
    events = await orch.submit_answer(
        current.learner_public_id,
        req.knowledge_id,
        req.is_correct,
        req.time_spent_seconds,
    )
    await write_audit(
        session,
        actor=current.email,
        action="practice.submit",
        target=f"knowledge:{req.knowledge_id}",
        request=request,
        metadata={
            "is_correct": req.is_correct,
            "time_spent_seconds": req.time_spent_seconds,
            "learner_id": current.learner_public_id,
        },
    )
    return {
        "status": "processed",
        "events_triggered": len(events),
        "events": [
            {"type": e.type.value, "source": e.source, "data": e.data} for e in events[-10:]
        ],
    }


@router.post("/question")
async def ask_question(
    req: AskQuestionRequest,
    current: CurrentUser = Depends(require_student()),
    request: Request = None,
):
    """学生提问。"""
    orch = request.app.state.orchestrator
    events = await orch.ask_question(
        current.learner_public_id,
        req.knowledge_id,
        req.question,
        debate_mode=req.debate_mode,
    )
    return {
        "status": "processed",
        "events_triggered": len(events),
        "events": [
            {"type": e.type.value, "source": e.source, "data": e.data} for e in events[-10:]
        ],
    }


@router.post("/message")
async def send_message(
    req: SendMessageRequest,
    current: CurrentUser = Depends(require_student()),
    request: Request = None,
):
    """学生发送消息(对话)。"""
    orch = request.app.state.orchestrator
    events = await orch.send_message(
        current.learner_public_id, req.message, req.knowledge_id
    )
    return {
        "status": "processed",
        "events_triggered": len(events),
        "events": [
            {"type": e.type.value, "source": e.source, "data": e.data} for e in events[-10:]
        ],
    }


@router.get("/progress/{learner_public_id}")
async def get_progress(
    learner_public_id: str,
    current: CurrentUser = Depends(get_current_active_user),
    request: Request = None,
):
    """获取学习者进度。

    权限:
    - 学生只能查自己的进度
    - 教师/管理员可查任意学习者
    """
    if current.role == UserRole.STUDENT and learner_public_id != current.learner_public_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="学生只能查看自己的学习进度",
        )
    orch = request.app.state.orchestrator
    # 若不在缓存,先 load(便于教师/管理员查询任意学生)
    if orch.learner_service.get_cached(learner_public_id) is None:
        await orch.learner_service.load(learner_public_id)
    return orch.get_learner_progress(learner_public_id)


@router.get("/knowledge-graph")
async def get_knowledge_graph(
    current: CurrentUser = Depends(get_current_active_user),
    request: Request = None,
):
    """获取知识图谱结构。所有登录用户可查。"""
    orch = request.app.state.orchestrator
    graph = orch.knowledge_graph
    if graph is None:
        return {"nodes": [], "learning_order": []}
    return {
        "nodes": [
            {
                "id": n.id,
                "name": n.name,
                "difficulty": n.difficulty,
                "prerequisites": n.prerequisites,
                "tags": n.tags,
            }
            for n in graph.nodes.values()
        ],
        "learning_order": graph.topological_sort(),
    }
