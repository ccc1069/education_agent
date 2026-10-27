"""ClassService + AssignmentService + TeacherDashboardService。

职责:
1. ClassService: 创建班级 + 邀请码 + 成员管理
2. AssignmentService: 布置作业 + 状态机 + 查询
3. TeacherDashboardService: 班级学情看板 + 干预推荐
"""

import logging
import secrets
import string
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AssignmentORM,
    ClassMemberORM,
    ClassORM,
    KnowledgeStateORM,
    LearnerORM,
    SubmissionORM,
)
from repositories import (
    AssignmentRepository,
    ClassRepository,
    LearnerRepository,
    QuestionRepository,
)

logger = logging.getLogger(__name__)

# 邀请码: 8 位大写字母数字,避免歧义字符
_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_INVITE_CODE_LEN = 8

# 作业状态机
ASSIGNMENT_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"published", "archived"},
    "published": {"closed", "archived"},
    "closed": {"archived"},
    "archived": set(),
}


def _generate_invite_code() -> str:
    """生成 8 位邀请码(无歧义字符)。"""
    return "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(_INVITE_CODE_LEN))


class ClassService:
    """班级管理服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ClassRepository(session)

    async def create_class(
        self,
        name: str,
        teacher_id: int,
        description: str = "",
    ) -> dict[str, Any]:
        """创建班级(自动生成唯一邀请码)。"""
        if not name or not name.strip():
            raise ValueError("Class name cannot be empty")

        # 重试 3 次防邀请码碰撞
        for _ in range(3):
            invite_code = _generate_invite_code()
            existing = await self.repo.get_by_invite_code(invite_code)
            if existing is None:
                break
        else:
            raise RuntimeError("Failed to generate unique invite code")

        cls = ClassORM(
            name=name.strip(),
            description=description,
            teacher_id=teacher_id,
            invite_code=invite_code,
            is_active=True,
        )
        await self.repo.add(cls)
        await self.session.commit()
        logger.info("Class created: id=%d teacher=%s code=%s", cls.id, teacher_id, invite_code)
        result = self._to_dict(cls)
        result["member_count"] = 0
        return result

    async def list_teacher_classes(self, teacher_id: int) -> list[dict[str, Any]]:
        """列出教师的所有班级。"""
        classes = await self.repo.list_by_teacher(teacher_id)
        result = []
        for c in classes:
            d = self._to_dict(c)
            d["member_count"] = await self._count_members(c.id)
            result.append(d)
        return result

    async def list_all_classes(self) -> list[dict[str, Any]]:
        """列出全部班级(管理员)。"""
        classes = await self.repo.list_all()
        result = []
        for c in classes:
            d = self._to_dict(c)
            d["member_count"] = await self._count_members(c.id)
            result.append(d)
        return result

    async def get_class(self, class_id: int) -> dict[str, Any] | None:
        """获取班级详情(含成员数)。"""
        c = await self.repo.get_by_id(class_id)
        if c is None:
            return None
        d = self._to_dict(c)
        d["member_count"] = await self._count_members(class_id)
        return d

    async def list_members(self, class_id: int) -> list[dict[str, Any]]:
        """列出班级成员(含 learner 公开信息)。"""
        members = await self.repo.list_members(class_id)
        if not members:
            return []
        learner_ids = [m.learner_id for m in members]
        learner_repo = LearnerRepository(self.session)
        learners: dict[int, LearnerORM] = {}
        for lid in learner_ids:
            l = await learner_repo.get_by_id(lid)
            if l is not None:
                learners[l.id] = l

        return [
            {
                "learner_id": m.learner_id,
                "public_id": learners.get(m.learner_id).public_id if learners.get(m.learner_id) else None,
                "name": learners.get(m.learner_id).name if learners.get(m.learner_id) else None,
                "joined_at": m.joined_at.isoformat() if m.joined_at else None,
            }
            for m in members
        ]

    async def add_member_by_invite_code(
        self, invite_code: str, learner_id: int
    ) -> dict[str, Any]:
        """学生通过邀请码加入班级。

        注: 角色检查由路由层负责(仅 STUDENT 可调用)。本方法只做班级存在性 + 幂等性检查。
        """
        cls = await self.repo.get_by_invite_code(invite_code)
        if cls is None:
            raise ValueError("Invalid invite code")
        if not cls.is_active:
            raise ValueError("Class is not active")

        if await self.repo.is_member(cls.id, learner_id):
            return {
                "class_id": cls.id,
                "already_member": True,
                "name": cls.name,
                "invite_code": cls.invite_code,
            }

        await self.repo.add_member(cls.id, learner_id)
        await self.session.commit()
        logger.info("Member added: class=%d learner=%d", cls.id, learner_id)
        return {
            "class_id": cls.id,
            "already_member": False,
            "name": cls.name,
            "invite_code": cls.invite_code,
        }

    async def remove_member(self, class_id: int, learner_id: int) -> bool:
        """教师移除学生。"""
        removed = await self.repo.remove_member(class_id, learner_id)
        if removed:
            await self.session.commit()
        return removed

    async def archive_class(self, class_id: int) -> bool:
        """归档班级(is_active=False)。"""
        c = await self.repo.get_by_id(class_id)
        if c is None:
            return False
        c.is_active = False
        await self.session.commit()
        return True

    async def _count_members(self, class_id: int) -> int:
        result = await self.session.execute(
            select(func.count(ClassMemberORM.id)).where(
                ClassMemberORM.class_id == class_id
            )
        )
        return result.scalar_one() or 0

    def _to_dict(self, c: ClassORM) -> dict[str, Any]:
        return {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "teacher_id": c.teacher_id,
            "invite_code": c.invite_code,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }


class AssignmentService:
    """作业管理服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AssignmentRepository(session)
        self.question_repo = QuestionRepository(session)

    async def create_assignment(
        self,
        title: str,
        class_id: int,
        teacher_id: int,
        question_ids: list[int],
        description: str = "",
        due_at: Any | None = None,
        *,
        allow_cross_teacher: bool = False,
    ) -> dict[str, Any]:
        """布置作业(draft 状态)。

        校验:
        - title 非空
        - 至少 1 个题目
        - 题目必须存在且为 published 状态
        - 教师必须是班级的创建者(管理员可设 allow_cross_teacher=True)
        """
        if not title or not title.strip():
            raise ValueError("Assignment title cannot be empty")
        if not question_ids:
            raise ValueError("At least one question is required")

        # 校验题目存在且 published
        for qid in question_ids:
            q = await self.question_repo.get_by_id(qid)
            if q is None:
                raise ValueError(f"Question {qid} not found")
            if q.status != "published":
                raise ValueError(f"Question {qid} not published (status={q.status})")

        # 校验班级归属(管理员可代管任意班级)
        class_repo = ClassRepository(self.session)
        cls = await class_repo.get_by_id(class_id)
        if cls is None:
            raise ValueError("Class not found")
        if cls.teacher_id != teacher_id and not allow_cross_teacher:
            raise ValueError("Only class teacher can create assignments")

        assignment = AssignmentORM(
            title=title.strip(),
            description=description,
            class_id=class_id,
            teacher_id=cls.teacher_id,  # 归属仍记为班级任课教师
            question_ids=list(question_ids),
            status="draft",
            due_at=due_at,
        )
        await self.repo.add(assignment)
        await self.session.commit()
        logger.info(
            "Assignment created: id=%d class=%d teacher=%d questions=%d",
            assignment.id,
            class_id,
            teacher_id,
            len(question_ids),
        )
        return self._to_dict(assignment)

    async def list_learner_assignments(
        self, learner_id: int, *, statuses: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """学生可见作业: 所在班级中已发布/已关闭的作业。"""
        class_repo = ClassRepository(self.session)
        class_ids = await class_repo.list_class_ids_for_learner(learner_id)
        if not class_ids:
            return []
        status_filter = statuses or ["published", "closed"]
        assignments = await self.repo.list_by_classes(class_ids)
        name_by_id: dict[int, str] = {}
        for cid in class_ids:
            cls = await class_repo.get_by_id(cid)
            if cls is not None:
                name_by_id[cid] = cls.name
        result: list[dict[str, Any]] = []
        for a in assignments:
            if a.status not in status_filter:
                continue
            d = self._to_dict(a)
            d["class_name"] = name_by_id.get(a.class_id)
            result.append(d)
        return result

    async def list_class_assignments(
        self, class_id: int, status: str | None = None
    ) -> list[dict[str, Any]]:
        assignments = await self.repo.list_by_class(class_id, status=status)
        return [self._to_dict(a) for a in assignments]

    async def list_teacher_assignments(
        self, teacher_id: int, status: str | None = None
    ) -> list[dict[str, Any]]:
        assignments = await self.repo.list_by_teacher(teacher_id, status=status)
        return [self._to_dict(a) for a in assignments]

    async def list_all_assignments(
        self, status: str | None = None
    ) -> list[dict[str, Any]]:
        """列出全部作业(管理员)。"""
        assignments = await self.repo.list_all(status=status)
        return [self._to_dict(a) for a in assignments]

    async def get_assignment(self, assignment_id: int) -> dict[str, Any] | None:
        a = await self.repo.get_by_id(assignment_id)
        if a is None:
            return None
        return self._to_dict(a)

    async def update_assignment(
        self,
        assignment_id: int,
        *,
        title: str,
        description: str = "",
        question_ids: list[int] | None = None,
        due_at: Any | None = None,
        class_id: int | None = None,
        allow_cross_teacher: bool = False,
        teacher_id: int | None = None,
    ) -> dict[str, Any]:
        """编辑作业内容。

        - draft: 可改标题/说明/题目/截止/班级;题目可为空(待补充)
        - published / closed: 可改标题/说明/题目/截止;不可换班;至少 1 题
        - archived: 不可改
        """
        a = await self.repo.get_by_id(assignment_id)
        if a is None:
            raise ValueError("Assignment not found")
        if a.status == "archived":
            raise ValueError("cannot edit archived assignment")
        if not title or not title.strip():
            raise ValueError("Assignment title cannot be empty")

        ids = list(question_ids) if question_ids is not None else list(a.question_ids or [])
        if a.status != "draft" and not ids:
            raise ValueError("At least one question is required")
        for qid in ids:
            q = await self.question_repo.get_by_id(qid)
            if q is None:
                raise ValueError(f"Question {qid} not found")
            if q.status != "published":
                raise ValueError(f"Question {qid} not published (status={q.status})")

        new_class_id = a.class_id
        if class_id is not None and class_id != a.class_id:
            if a.status != "draft":
                raise ValueError("cannot change class after publish")
            class_repo = ClassRepository(self.session)
            cls = await class_repo.get_by_id(class_id)
            if cls is None:
                raise ValueError("Class not found")
            if not cls.is_active:
                raise ValueError("Class is not active")
            owner = teacher_id if teacher_id is not None else a.teacher_id
            if cls.teacher_id != owner and not allow_cross_teacher:
                raise ValueError("Only class teacher can assign to this class")
            new_class_id = class_id

        updated = await self.repo.update_fields(
            assignment_id,
            title=title.strip(),
            description=description or "",
            question_ids=ids,
            due_at=due_at,
            class_id=new_class_id if new_class_id != a.class_id else None,
        )
        await self.session.commit()
        if updated is None:
            raise ValueError("Assignment not found")
        logger.info("Assignment updated: id=%d status=%s", assignment_id, updated.status)
        return self._to_dict(updated)

    async def update_status(
        self, assignment_id: int, new_status: str
    ) -> dict[str, Any] | None:
        """状态机迁移: draft -> published -> closed -> archived。"""
        a = await self.repo.get_by_id(assignment_id)
        if a is None:
            return None
        if new_status not in ASSIGNMENT_TRANSITIONS.get(a.status, set()):
            raise ValueError(
                f"invalid transition: {a.status} -> {new_status}"
            )
        if new_status == "published" and not (a.question_ids or []):
            raise ValueError("cannot publish assignment without questions")
        await self.repo.update_status(assignment_id, new_status)
        await self.session.commit()
        refreshed = await self.repo.get_by_id(assignment_id)
        return self._to_dict(refreshed) if refreshed else None

    async def delete_assignment(self, assignment_id: int) -> bool:
        """删除作业(仅 draft 状态可删)。"""
        a = await self.repo.get_by_id(assignment_id)
        if a is None:
            return False
        if a.status != "draft":
            raise ValueError(
                f"cannot delete assignment in status={a.status}, archive instead"
            )
        await self.repo.delete(a)
        await self.session.commit()
        return True

    def _to_dict(self, a: AssignmentORM) -> dict[str, Any]:
        return {
            "id": a.id,
            "title": a.title,
            "description": a.description,
            "class_id": a.class_id,
            "teacher_id": a.teacher_id,
            "question_ids": a.question_ids or [],
            "status": a.status,
            "due_at": a.due_at.isoformat() if a.due_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        }


class TeacherDashboardService:
    """教师班级学情看板 + 干预推荐。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.class_repo = ClassRepository(session)

    async def get_class_dashboard(self, class_id: int) -> dict[str, Any] | None:
        """班级学情看板: 成员数 + 平均掌握度 + 薄弱知识点。"""
        cls = await self.class_repo.get_by_id(class_id)
        if cls is None:
            return None

        members = await self.class_repo.list_members(class_id)
        learner_ids = [m.learner_id for m in members]

        if not learner_ids:
            return {
                "class_id": class_id,
                "class_name": cls.name,
                "member_count": 0,
                "total_states": 0,
                "avg_mastery": 0.0,
                "weak_knowledge_ids": [],
                "interventions": [],
            }

        # 平均掌握度: 取这些 learner 在所有知识点的 mastery 平均
        mastery_result = await self.session.execute(
            select(
                func.count(KnowledgeStateORM.id),
                func.avg(KnowledgeStateORM.mastery),
            ).where(KnowledgeStateORM.learner_id.in_(learner_ids))
        )
        row = mastery_result.one()
        total_states = row[0] or 0
        avg_mastery = float(row[1]) if row[1] is not None else 0.0

        # 薄弱知识点: mastery < 0.4 的知识点(按出现频次降序)
        weak_result = await self.session.execute(
            select(
                KnowledgeStateORM.knowledge_id,
                func.avg(KnowledgeStateORM.mastery).label("avg_mastery"),
                func.count(KnowledgeStateORM.id).label("count"),
            )
            .where(
                KnowledgeStateORM.learner_id.in_(learner_ids),
                KnowledgeStateORM.mastery < 0.4,
            )
            .group_by(KnowledgeStateORM.knowledge_id)
            .order_by(func.avg(KnowledgeStateORM.mastery).asc())
            .limit(10)
        )
        weak_knowledge_ids = [
            {"knowledge_id": r[0], "avg_mastery": round(float(r[1]), 3), "student_count": r[2]}
            for r in weak_result.all()
        ]

        # 干预推荐: mastery < 0.2 且 attempts >= 3 的学生
        interventions_result = await self.session.execute(
            select(
                KnowledgeStateORM.learner_id,
                KnowledgeStateORM.knowledge_id,
                KnowledgeStateORM.mastery,
                KnowledgeStateORM.attempts,
            )
            .where(
                KnowledgeStateORM.learner_id.in_(learner_ids),
                KnowledgeStateORM.mastery < 0.2,
                KnowledgeStateORM.attempts >= 3,
            )
            .order_by(KnowledgeStateORM.mastery.asc())
            .limit(20)
        )
        interventions = [
            {
                "learner_id": r[0],
                "knowledge_id": r[1],
                "mastery": round(float(r[2]), 3),
                "attempts": r[3],
                "recommendation": "提供分级提示 + 一对一辅导",
                "public_id": None,
                "name": None,
            }
            for r in interventions_result.all()
        ]
        if interventions:
            from repositories import LearnerRepository

            learner_repo = LearnerRepository(self.session)
            for itv in interventions:
                learner = await learner_repo.get_by_id(itv["learner_id"])
                if learner is not None:
                    itv["public_id"] = learner.public_id
                    itv["name"] = learner.name

        return {
            "class_id": class_id,
            "class_name": cls.name,
            "member_count": len(learner_ids),
            "total_states": total_states,
            "avg_mastery": round(avg_mastery, 3),
            "weak_knowledge_ids": weak_knowledge_ids,
            "interventions": interventions,
        }
