"""教师后台路由: 班级管理 + 作业 + 学情看板。

权限:
- 班级/作业写操作: 教师创建班级、布置作业;管理员全权
- 学生: 通过邀请码加入班级、查看自己所在班级
- 列表: 教师只看自己的;管理员看全部
- 看板/详情: 教师只能看自己创建的班级;管理员可看任意班级
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit_helpers import write_audit
from auth import CurrentUser, get_current_active_user
from db.models import UserRole
from db.session import get_session_dep
from services import (
    AssignmentService,
    ClassService,
    TeacherDashboardService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teacher", tags=["teacher"])


# ---------- 班级请求/响应模型 ----------


class CreateClassRequest(BaseModel):
    """创建班级请求。"""

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)


class JoinClassRequest(BaseModel):
    """学生通过邀请码加入班级。"""

    invite_code: str = Field(min_length=1, max_length=16)


class CreateAssignmentRequest(BaseModel):
    """布置作业请求。"""

    title: str = Field(min_length=1, max_length=256)
    class_id: int
    question_ids: list[int] = Field(min_length=1)
    description: str = Field(default="", max_length=2000)
    due_at: datetime | None = Field(default=None)


class UpdateAssignmentStatusRequest(BaseModel):
    """作业状态迁移请求。"""

    new_status: str = Field(description="published / closed / archived")


class UpdateAssignmentRequest(BaseModel):
    """编辑作业内容(不含状态)。"""

    title: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=2000)
    question_ids: list[int] = Field(default_factory=list)
    due_at: datetime | None = Field(default=None)
    class_id: int | None = Field(default=None, description="仅草稿可换班")


class ClassSummary(BaseModel):
    """班级列表项。"""

    id: int
    name: str
    description: str
    teacher_id: int
    invite_code: str
    is_active: bool
    member_count: int
    created_at: str | None
    updated_at: str | None


class ClassDetail(ClassSummary):
    """班级详情(含成员列表)。"""

    members: list[dict[str, Any]]


class MemberInfo(BaseModel):
    """班级成员信息。"""

    learner_id: int
    public_id: str | None
    name: str | None
    joined_at: str | None


class AssignmentSummary(BaseModel):
    """作业列表项。"""

    id: int
    title: str
    description: str
    class_id: int
    teacher_id: int
    question_ids: list[int]
    status: str
    due_at: str | None
    created_at: str | None
    updated_at: str | None
    class_name: str | None = None


class DashboardResponse(BaseModel):
    """班级学情看板。"""

    class_id: int
    class_name: str
    member_count: int
    total_states: int
    avg_mastery: float
    weak_knowledge_ids: list[dict[str, Any]]
    interventions: list[dict[str, Any]]


# ---------- 权限检查 ----------


def _require_teacher_or_admin(current: CurrentUser) -> None:
    """教师/管理员才能操作。"""
    if current.role not in (UserRole.TEACHER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers and admins can perform this action",
        )


def _require_class_owner(cls: dict[str, Any] | None, current: CurrentUser) -> None:
    """教师只能操作自己创建的班级(管理员豁免)。"""
    if cls is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Class not found"
        )
    if current.role != UserRole.ADMIN and cls["teacher_id"] != current.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the class teacher can perform this action",
        )


# ---------- 班级路由 ----------


@router.post(
    "/classes",
    response_model=ClassSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_class(
    req: CreateClassRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """创建班级(教师/管理员)。自动生成 8 位邀请码。"""
    _require_teacher_or_admin(current)
    service = ClassService(session)
    try:
        result = await service.create_class(
            name=req.name,
            teacher_id=current.id,
            description=req.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await write_audit(
        session,
        actor=current.email,
        action="class.create",
        target=f"class:{result['id']}",
        request=request,
        metadata={"name": result.get("name"), "invite_code": result.get("invite_code")},
    )
    return result


@router.get("/classes", response_model=list[ClassSummary])
async def list_my_classes(
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """列出班级: 教师看自己的,管理员看全部。"""
    _require_teacher_or_admin(current)
    service = ClassService(session)
    if current.role == UserRole.ADMIN:
        return await service.list_all_classes()
    return await service.list_teacher_classes(current.id)


@router.get("/classes/{class_id}", response_model=ClassDetail)
async def get_class(
    class_id: int,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """获取班级详情(含成员列表)。教师只能看自己的班级。"""
    _require_teacher_or_admin(current)
    service = ClassService(session)
    cls = await service.get_class(class_id)
    _require_class_owner(cls, current)
    members = await service.list_members(class_id)
    cls["members"] = members
    return cls


@router.post("/classes/join", response_model=dict)
async def join_class_by_invite_code(
    req: JoinClassRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """学生通过邀请码加入班级。

    需要学生已绑定 learner profile(由 require_student 检查)。
    """
    if current.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅学生可通过邀请码加入班级",
        )
    if not current.learner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student has no learner profile",
        )
    service = ClassService(session)
    try:
        result = await service.add_member_by_invite_code(
            invite_code=req.invite_code, learner_id=current.learner_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await write_audit(
        session,
        actor=current.email,
        action="class.join",
        target=f"class:{result.get('class_id', req.invite_code)}",
        request=request,
        metadata={"invite_code": req.invite_code, "learner_id": current.learner_id},
    )
    return result


@router.get("/classes/{class_id}/members", response_model=list[MemberInfo])
async def list_class_members(
    class_id: int,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """列出班级成员(教师/管理员)。"""
    _require_teacher_or_admin(current)
    service = ClassService(session)
    cls = await service.get_class(class_id)
    _require_class_owner(cls, current)
    return await service.list_members(class_id)


@router.post(
    "/classes/{class_id}/members/{learner_id}/delete",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    class_id: int,
    learner_id: int,
    request: Request,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """教师移除学生(仅自己创建的班级)。"""
    _require_teacher_or_admin(current)
    service = ClassService(session)
    cls = await service.get_class(class_id)
    _require_class_owner(cls, current)
    removed = await service.remove_member(class_id, learner_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in this class",
        )
    await write_audit(
        session,
        actor=current.email,
        action="class.member_remove",
        target=f"class:{class_id}:learner:{learner_id}",
        request=request,
    )
    return None


@router.post("/classes/{class_id}/archive", response_model=dict)
async def archive_class(
    class_id: int,
    request: Request,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """归档班级(is_active=False)。归档后学生无法通过邀请码加入。"""
    _require_teacher_or_admin(current)
    service = ClassService(session)
    cls = await service.get_class(class_id)
    _require_class_owner(cls, current)
    archived = await service.archive_class(class_id)
    if not archived:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Class not found"
        )
    await write_audit(
        session,
        actor=current.email,
        action="class.archive",
        target=f"class:{class_id}",
        request=request,
    )
    return {"class_id": class_id, "is_active": False}


# ---------- 班级学情看板 ----------


@router.get("/classes/{class_id}/dashboard", response_model=DashboardResponse)
async def get_class_dashboard(
    class_id: int,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """班级学情看板: 平均掌握度 + 薄弱知识点 + 干预推荐。

    - 平均掌握度: 全班所有 KnowledgeState 的 mastery 平均
    - 薄弱知识点: avg(mastery) < 0.4 的知识点(Top 10)
    - 干预推荐: mastery < 0.2 且 attempts >= 3 的学生(Top 20)
    """
    _require_teacher_or_admin(current)
    service = TeacherDashboardService(session)
    cls_service = ClassService(session)
    cls = await cls_service.get_class(class_id)
    _require_class_owner(cls, current)
    dashboard = await service.get_class_dashboard(class_id)
    if dashboard is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Class not found"
        )
    return dashboard


# ---------- 作业路由 ----------


@router.post(
    "/assignments",
    response_model=AssignmentSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_assignment(
    req: CreateAssignmentRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """布置作业(draft 状态)。校验题目已发布且教师拥有该班级。"""
    _require_teacher_or_admin(current)
    service = AssignmentService(session)
    try:
        result = await service.create_assignment(
            title=req.title,
            class_id=req.class_id,
            teacher_id=current.id,
            question_ids=req.question_ids,
            description=req.description,
            due_at=req.due_at,
            allow_cross_teacher=current.role == UserRole.ADMIN,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await write_audit(
        session,
        actor=current.email,
        action="assignment.create",
        target=f"assignment:{result['id']}",
        request=request,
        metadata={
            "title": result.get("title"),
            "class_id": result.get("class_id"),
            "status": result.get("status"),
        },
    )
    return result


@router.get("/assignments", response_model=list[AssignmentSummary])
async def list_my_assignments(
    status_filter: str | None = Query(default=None, alias="status"),
    class_id: int | None = Query(default=None),
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """列出作业: 教师看自己的,管理员看全部(可按状态/班级过滤)。"""
    _require_teacher_or_admin(current)
    service = AssignmentService(session)
    if class_id is not None:
        if current.role != UserRole.ADMIN:
            cls_service = ClassService(session)
            cls = await cls_service.get_class(class_id)
            _require_class_owner(cls, current)
        return await service.list_class_assignments(class_id, status=status_filter)
    if current.role == UserRole.ADMIN:
        return await service.list_all_assignments(status=status_filter)
    return await service.list_teacher_assignments(current.id, status=status_filter)


@router.get("/assignments/mine", response_model=list[AssignmentSummary])
async def list_student_assignments(
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """学生查看所在班级中已发布/已关闭的作业。"""
    if current.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅学生可查看班级作业列表",
        )
    if not current.learner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student has no learner profile",
        )
    service = AssignmentService(session)
    return await service.list_learner_assignments(current.learner_id)


@router.get("/assignments/{assignment_id}", response_model=AssignmentSummary)
async def get_assignment(
    assignment_id: int,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """获取作业详情。"""
    _require_teacher_or_admin(current)
    service = AssignmentService(session)
    a = await service.get_assignment(assignment_id)
    if a is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
        )
    if current.role != UserRole.ADMIN and a["teacher_id"] != current.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assignment teacher can view it",
        )
    return a


@router.post("/assignments/{assignment_id}", response_model=AssignmentSummary)
async def update_assignment(
    assignment_id: int,
    req: UpdateAssignmentRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """编辑作业标题/说明/题目/截止时间;草稿还可换班。"""
    _require_teacher_or_admin(current)
    service = AssignmentService(session)
    existing = await service.get_assignment(assignment_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
        )
    if current.role != UserRole.ADMIN and existing["teacher_id"] != current.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assignment teacher can edit it",
        )
    try:
        result = await service.update_assignment(
            assignment_id,
            title=req.title,
            description=req.description,
            question_ids=req.question_ids,
            due_at=req.due_at,
            class_id=req.class_id,
            allow_cross_teacher=current.role == UserRole.ADMIN,
            teacher_id=current.id,
        )
    except ValueError as e:
        detail = str(e)
        code = (
            status.HTTP_404_NOT_FOUND
            if detail == "Assignment not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail)
    await write_audit(
        session,
        actor=current.email,
        action="assignment.update",
        target=f"assignment:{assignment_id}",
        request=request,
        metadata={
            "title": result.get("title"),
            "question_count": len(result.get("question_ids") or []),
        },
    )
    return result


@router.post("/assignments/{assignment_id}/status", response_model=AssignmentSummary)
async def update_assignment_status(
    assignment_id: int,
    req: UpdateAssignmentStatusRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """作业状态迁移: draft -> published -> closed -> archived。"""
    _require_teacher_or_admin(current)
    service = AssignmentService(session)
    existing = await service.get_assignment(assignment_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
        )
    if current.role != UserRole.ADMIN and existing["teacher_id"] != current.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assignment teacher can change its status",
        )
    try:
        result = await service.update_status(assignment_id, req.new_status)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
        )
    action = (
        "assignment.publish"
        if req.new_status == "published"
        else "assignment.status_change"
    )
    await write_audit(
        session,
        actor=current.email,
        action=action,
        target=f"assignment:{assignment_id}",
        request=request,
        metadata={
            "from": existing.get("status"),
            "to": req.new_status,
        },
    )
    return result


@router.post(
    "/assignments/{assignment_id}/delete", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_assignment(
    assignment_id: int,
    request: Request,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """删除作业(仅 draft 状态可删)。"""
    _require_teacher_or_admin(current)
    service = AssignmentService(session)
    existing = await service.get_assignment(assignment_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
        )
    if current.role != UserRole.ADMIN and existing["teacher_id"] != current.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assignment teacher can delete it",
        )
    try:
        deleted = await service.delete_assignment(assignment_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
        )
    await write_audit(
        session,
        actor=current.email,
        action="assignment.delete",
        target=f"assignment:{assignment_id}",
        request=request,
        metadata={"title": existing.get("title")},
    )
    return None
