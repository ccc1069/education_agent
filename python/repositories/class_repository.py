"""班级 + 作业仓储: P2#12 教师后台。"""

import logging
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    AssignmentORM,
    ClassMemberORM,
    ClassORM,
    KnowledgeStateORM,
    LearnerORM,
    SubmissionORM,
)
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ClassRepository(BaseRepository[ClassORM]):
    """班级仓储: CRUD + 邀请码 + 成员管理。"""

    model = ClassORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_invite_code(self, invite_code: str) -> ClassORM | None:
        result = await self.session.execute(
            select(ClassORM).where(ClassORM.invite_code == invite_code)
        )
        return result.scalar_one_or_none()

    async def list_by_teacher(self, teacher_id: int) -> list[ClassORM]:
        result = await self.session.execute(
            select(ClassORM)
            .where(ClassORM.teacher_id == teacher_id)
            .order_by(ClassORM.created_at.desc(), ClassORM.id.desc())
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[ClassORM]:
        """全部班级(管理员全量视图)。"""
        result = await self.session.execute(
            select(ClassORM).order_by(ClassORM.created_at.desc(), ClassORM.id.desc())
        )
        return list(result.scalars().all())

    async def get_with_members(self, class_id: int) -> ClassORM | None:
        """带成员列表的班级详情。"""
        result = await self.session.execute(
            select(ClassORM)
            .options(selectinload(ClassORM.members))
            .where(ClassORM.id == class_id)
        )
        return result.scalar_one_or_none()

    async def list_members(self, class_id: int) -> list[ClassMemberORM]:
        result = await self.session.execute(
            select(ClassMemberORM)
            .where(ClassMemberORM.class_id == class_id)
            .order_by(ClassMemberORM.joined_at.asc())
        )
        return list(result.scalars().all())

    async def add_member(self, class_id: int, learner_id: int) -> ClassMemberORM:
        member = ClassMemberORM(class_id=class_id, learner_id=learner_id)
        self.session.add(member)
        await self.session.flush()
        return member

    async def remove_member(self, class_id: int, learner_id: int) -> bool:
        result = await self.session.execute(
            delete(ClassMemberORM).where(
                ClassMemberORM.class_id == class_id,
                ClassMemberORM.learner_id == learner_id,
            )
        )
        return (result.rowcount or 0) > 0

    async def is_member(self, class_id: int, learner_id: int) -> bool:
        result = await self.session.execute(
            select(ClassMemberORM.id).where(
                ClassMemberORM.class_id == class_id,
                ClassMemberORM.learner_id == learner_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_class_ids_for_learner(self, learner_id: int) -> list[int]:
        result = await self.session.execute(
            select(ClassMemberORM.class_id).where(
                ClassMemberORM.learner_id == learner_id
            )
        )
        return [int(r) for r in result.scalars().all()]


class AssignmentRepository(BaseRepository[AssignmentORM]):
    """作业仓储: CRUD + 状态机 + 按班级查询。"""

    model = AssignmentORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_classes(
        self, class_ids: list[int], status: str | None = None
    ) -> list[AssignmentORM]:
        if not class_ids:
            return []
        stmt = (
            select(AssignmentORM)
            .where(AssignmentORM.class_id.in_(class_ids))
            .order_by(AssignmentORM.created_at.desc(), AssignmentORM.id.desc())
        )
        if status:
            stmt = stmt.where(AssignmentORM.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_class(
        self, class_id: int, status: str | None = None
    ) -> list[AssignmentORM]:
        stmt = select(AssignmentORM).where(AssignmentORM.class_id == class_id).order_by(
            AssignmentORM.created_at.desc(), AssignmentORM.id.desc()
        )
        if status:
            stmt = stmt.where(AssignmentORM.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_teacher(
        self, teacher_id: int, status: str | None = None
    ) -> list[AssignmentORM]:
        stmt = select(AssignmentORM).where(
            AssignmentORM.teacher_id == teacher_id
        ).order_by(AssignmentORM.created_at.desc(), AssignmentORM.id.desc())
        if status:
            stmt = stmt.where(AssignmentORM.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self, status: str | None = None) -> list[AssignmentORM]:
        """全部作业(管理员全量视图)。"""
        stmt = select(AssignmentORM).order_by(
            AssignmentORM.created_at.desc(), AssignmentORM.id.desc()
        )
        if status:
            stmt = stmt.where(AssignmentORM.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self, assignment_id: int, status: str
    ) -> None:
        await self.session.execute(
            update(AssignmentORM)
            .where(AssignmentORM.id == assignment_id)
            .values(**{"status": status})
        )
        await self.session.flush()

    async def update_fields(
        self,
        assignment_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        question_ids: list[int] | None = None,
        due_at: Any = ...,
        class_id: int | None = None,
    ) -> AssignmentORM | None:
        """更新作业内容字段(不含状态)。due_at 传 Ellipsis 表示不改。"""
        a = await self.get_by_id(assignment_id)
        if a is None:
            return None
        values: dict[str, Any] = {}
        if title is not None:
            values["title"] = title
        if description is not None:
            values["description"] = description
        if question_ids is not None:
            values["question_ids"] = question_ids
        if due_at is not ...:
            values["due_at"] = due_at
        if class_id is not None:
            values["class_id"] = class_id
        if not values:
            return a
        await self.session.execute(
            update(AssignmentORM)
            .where(AssignmentORM.id == assignment_id)
            .values(**values)
        )
        await self.session.flush()
        return await self.get_by_id(assignment_id)
