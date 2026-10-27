"""ClassService + AssignmentService + TeacherDashboardService 单元测试。"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import (
    AssignmentORM,
    ClassMemberORM,
    ClassORM,
    KnowledgeStateORM,
    LearnerORM,
    QuestionORM,
    UserORM,
    UserRole,
)
from services import (
    AssignmentService,
    ClassService,
    TeacherDashboardService,
)


# ---------- 辅助 ----------


async def _make_user(session: AsyncSession, role: UserRole, email: str) -> int:
    user = UserORM(
        email=email,
        password_hash="x",
        role=role,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user.id


async def _make_learner(session: AsyncSession, public_id: str) -> int:
    learner = LearnerORM(public_id=public_id, name=public_id)
    session.add(learner)
    await session.flush()
    return learner.id


async def _make_published_question(
    session: AsyncSession, knowledge_id: str = "kp_test"
) -> int:
    q = QuestionORM(
        knowledge_id=knowledge_id,
        question_type="multiple_choice",
        difficulty=3,
        content={"stem": "1+1=?", "options": ["1", "2", "3", "4"]},
        answer="2",
        analysis="1+1=2",
        status="published",
    )
    session.add(q)
    await session.flush()
    return q.id


# ---------- ClassService: 创建班级 ----------


@pytest.mark.asyncio
async def test_create_class_generates_unique_invite_code(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "t1@test.local")
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        result = await service.create_class(name="Math 101", teacher_id=teacher_id)
        assert result["id"] > 0
        assert result["name"] == "Math 101"
        assert result["teacher_id"] == teacher_id
        assert len(result["invite_code"]) == 8
        assert result["is_active"] is True


@pytest.mark.asyncio
async def test_create_class_rejects_empty_name(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "t2@test.local")
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        with pytest.raises(ValueError, match="cannot be empty"):
            await service.create_class(name="", teacher_id=teacher_id)


@pytest.mark.asyncio
async def test_invite_code_is_unique_across_classes(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "t3@test.local")
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        c1 = await service.create_class(name="A", teacher_id=teacher_id)
        c2 = await service.create_class(name="B", teacher_id=teacher_id)
        assert c1["invite_code"] != c2["invite_code"]


# ---------- ClassService: 邀请码加入 ----------


@pytest.mark.asyncio
async def test_student_joins_class_by_invite_code(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "t4@test.local")
        learner_id = await _make_learner(s, "stu1")
        await s.commit()

    async with async_session() as s:
        cls_service = ClassService(s)
        cls = await cls_service.create_class(name="C", teacher_id=teacher_id)
        invite = cls["invite_code"]
        await s.commit()

    async with async_session() as s:
        cls_service = ClassService(s)
        result = await cls_service.add_member_by_invite_code(invite, learner_id)
        assert result["already_member"] is False
        assert result["class_id"] > 0


@pytest.mark.asyncio
async def test_join_class_invalid_invite_code_raises(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        learner_id = await _make_learner(s, "stu2")
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        with pytest.raises(ValueError, match="Invalid invite code"):
            await service.add_member_by_invite_code("BADCODE1", learner_id)


@pytest.mark.asyncio
async def test_join_class_idempotent(test_engine):
    """学生重复加入同一班级返回 already_member=True。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "t5@test.local")
        learner_id = await _make_learner(s, "stu3")
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        cls = await service.create_class(name="C", teacher_id=teacher_id)
        invite = cls["invite_code"]
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        await service.add_member_by_invite_code(invite, learner_id)
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        result = await service.add_member_by_invite_code(invite, learner_id)
        assert result["already_member"] is True


@pytest.mark.asyncio
async def test_join_class_archived_class_raises(test_engine):
    """归档班级不允许加入。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "t6@test.local")
        learner_id = await _make_learner(s, "stu_archived")
        cls = ClassORM(
            name="C",
            teacher_id=teacher_id,
            invite_code="CODE0099",
            is_active=False,
        )
        s.add(cls)
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        with pytest.raises(ValueError, match="not active"):
            await service.add_member_by_invite_code("CODE0099", learner_id)


# ---------- ClassService: 成员管理 ----------


@pytest.mark.asyncio
async def test_list_members_returns_learner_info(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "t7@test.local")
        learner_id = await _make_learner(s, "stu4")
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        cls = await service.create_class(name="C", teacher_id=teacher_id)
        cls_id = cls["id"]
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        await service.add_member_by_invite_code(cls["invite_code"], learner_id)
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        members = await service.list_members(cls_id)
        assert len(members) == 1
        assert members[0]["learner_id"] == learner_id
        assert members[0]["public_id"] == "stu4"


@pytest.mark.asyncio
async def test_remove_member_success(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "t8@test.local")
        learner_id = await _make_learner(s, "stu5")
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        cls = await service.create_class(name="C", teacher_id=teacher_id)
        cls_id = cls["id"]
        await service.add_member_by_invite_code(cls["invite_code"], learner_id)
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        removed = await service.remove_member(cls_id, learner_id)
        assert removed is True


@pytest.mark.asyncio
async def test_remove_member_not_in_class_returns_false(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "t9@test.local")
        learner_id = await _make_learner(s, "stu6")
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        cls = await service.create_class(name="C", teacher_id=teacher_id)
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        removed = await service.remove_member(cls["id"], learner_id)
        assert removed is False


@pytest.mark.asyncio
async def test_archive_class_sets_inactive(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "t10@test.local")
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        cls = await service.create_class(name="C", teacher_id=teacher_id)
        cls_id = cls["id"]
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        archived = await service.archive_class(cls_id)
        assert archived is True
        detail = await service.get_class(cls_id)
        assert detail["is_active"] is False


@pytest.mark.asyncio
async def test_archive_nonexistent_class_returns_false(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        service = ClassService(s)
        archived = await service.archive_class(99999)
        assert archived is False


@pytest.mark.asyncio
async def test_get_class_returns_member_count(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "t11@test.local")
        l1 = await _make_learner(s, "s1")
        l2 = await _make_learner(s, "s2")
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        cls = await service.create_class(name="C", teacher_id=teacher_id)
        await service.add_member_by_invite_code(cls["invite_code"], l1)
        await service.add_member_by_invite_code(cls["invite_code"], l2)
        await s.commit()

    async with async_session() as s:
        service = ClassService(s)
        detail = await service.get_class(cls["id"])
        assert detail["member_count"] == 2


# ---------- AssignmentService: 创建作业 ----------


@pytest.mark.asyncio
async def test_create_assignment_validates_published_questions(test_engine):
    """布置作业时题目必须是 published 状态。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "a_t1@test.local")
        q_id = await _make_published_question(s)
        await s.commit()

    async with async_session() as s:
        cls_service = ClassService(s)
        cls = await cls_service.create_class(name="C", teacher_id=teacher_id)
        cls_id = cls["id"]
        await s.commit()

    async with async_session() as s:
        service = AssignmentService(s)
        result = await service.create_assignment(
            title="HW1",
            class_id=cls_id,
            teacher_id=teacher_id,
            question_ids=[q_id],
        )
        assert result["status"] == "draft"
        assert result["question_ids"] == [q_id]


@pytest.mark.asyncio
async def test_create_assignment_rejects_draft_question(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "a_t2@test.local")
        q = QuestionORM(
            knowledge_id="kp",
            question_type="multiple_choice",
            difficulty=3,
            content={"stem": "?"},
            answer="x",
            status="draft",
        )
        s.add(q)
        await s.flush()
        q_id = q.id
        cls = ClassORM(name="C", teacher_id=teacher_id, invite_code="CODE0001", is_active=True)
        s.add(cls)
        await s.flush()
        cls_id = cls.id
        await s.commit()

    async with async_session() as s:
        service = AssignmentService(s)
        with pytest.raises(ValueError, match="not published"):
            await service.create_assignment(
                title="HW",
                class_id=cls_id,
                teacher_id=teacher_id,
                question_ids=[q_id],
            )


@pytest.mark.asyncio
async def test_create_assignment_rejects_non_owner(test_engine):
    """非班级创建者不能在该班级布置作业。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_a = await _make_user(s, UserRole.TEACHER, "ta@test.local")
        teacher_b = await _make_user(s, UserRole.TEACHER, "tb@test.local")
        q_id = await _make_published_question(s)
        cls = ClassORM(name="C", teacher_id=teacher_a, invite_code="CODE0002", is_active=True)
        s.add(cls)
        await s.flush()
        cls_id = cls.id
        await s.commit()

    async with async_session() as s:
        service = AssignmentService(s)
        with pytest.raises(ValueError, match="Only class teacher"):
            await service.create_assignment(
                title="HW",
                class_id=cls_id,
                teacher_id=teacher_b,
                question_ids=[q_id],
            )


@pytest.mark.asyncio
async def test_create_assignment_requires_questions(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "a_t3@test.local")
        cls = ClassORM(name="C", teacher_id=teacher_id, invite_code="CODE0003", is_active=True)
        s.add(cls)
        await s.flush()
        cls_id = cls.id
        await s.commit()

    async with async_session() as s:
        service = AssignmentService(s)
        with pytest.raises(ValueError, match="At least one question"):
            await service.create_assignment(
                title="HW",
                class_id=cls_id,
                teacher_id=teacher_id,
                question_ids=[],
            )


# ---------- AssignmentService: 状态机 ----------


@pytest.mark.asyncio
async def test_assignment_state_machine_draft_to_published(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "sm1@test.local")
        q_id = await _make_published_question(s)
        cls = ClassORM(name="C", teacher_id=teacher_id, invite_code="CODE0010", is_active=True)
        s.add(cls)
        await s.flush()
        cls_id = cls.id
        a = AssignmentORM(
            title="HW",
            class_id=cls_id,
            teacher_id=teacher_id,
            question_ids=[q_id],
            status="draft",
        )
        s.add(a)
        await s.flush()
        a_id = a.id
        await s.commit()

    async with async_session() as s:
        service = AssignmentService(s)
        result = await service.update_status(a_id, "published")
        assert result["status"] == "published"


@pytest.mark.asyncio
async def test_assignment_invalid_transition_raises(test_engine):
    """draft 不能直接跳到 closed。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "sm2@test.local")
        q_id = await _make_published_question(s)
        cls = ClassORM(name="C", teacher_id=teacher_id, invite_code="CODE0011", is_active=True)
        s.add(cls)
        await s.flush()
        cls_id = cls.id
        a = AssignmentORM(
            title="HW",
            class_id=cls_id,
            teacher_id=teacher_id,
            question_ids=[q_id],
            status="draft",
        )
        s.add(a)
        await s.flush()
        a_id = a.id
        await s.commit()

    async with async_session() as s:
        service = AssignmentService(s)
        with pytest.raises(ValueError, match="invalid transition"):
            await service.update_status(a_id, "closed")


@pytest.mark.asyncio
async def test_assignment_full_lifecycle(test_engine):
    """draft -> published -> closed -> archived。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "sm3@test.local")
        q_id = await _make_published_question(s)
        cls = ClassORM(name="C", teacher_id=teacher_id, invite_code="CODE0012", is_active=True)
        s.add(cls)
        await s.flush()
        cls_id = cls.id
        a = AssignmentORM(
            title="HW",
            class_id=cls_id,
            teacher_id=teacher_id,
            question_ids=[q_id],
            status="draft",
        )
        s.add(a)
        await s.flush()
        a_id = a.id
        await s.commit()

    async with async_session() as s:
        service = AssignmentService(s)
        await service.update_status(a_id, "published")
        await service.update_status(a_id, "closed")
        result = await service.update_status(a_id, "archived")
        assert result["status"] == "archived"


@pytest.mark.asyncio
async def test_delete_assignment_only_in_draft(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "sm4@test.local")
        q_id = await _make_published_question(s)
        cls = ClassORM(name="C", teacher_id=teacher_id, invite_code="CODE0013", is_active=True)
        s.add(cls)
        await s.flush()
        cls_id = cls.id
        a = AssignmentORM(
            title="HW",
            class_id=cls_id,
            teacher_id=teacher_id,
            question_ids=[q_id],
            status="draft",
        )
        s.add(a)
        await s.flush()
        a_id = a.id
        await s.commit()

    async with async_session() as s:
        service = AssignmentService(s)
        deleted = await service.delete_assignment(a_id)
        assert deleted is True


@pytest.mark.asyncio
async def test_delete_published_assignment_raises(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "sm5@test.local")
        q_id = await _make_published_question(s)
        cls = ClassORM(name="C", teacher_id=teacher_id, invite_code="CODE0014", is_active=True)
        s.add(cls)
        await s.flush()
        cls_id = cls.id
        a = AssignmentORM(
            title="HW",
            class_id=cls_id,
            teacher_id=teacher_id,
            question_ids=[q_id],
            status="published",
        )
        s.add(a)
        await s.flush()
        a_id = a.id
        await s.commit()

    async with async_session() as s:
        service = AssignmentService(s)
        with pytest.raises(ValueError, match="cannot delete assignment in status=published"):
            await service.delete_assignment(a_id)


# ---------- AssignmentService: 查询 ----------


@pytest.mark.asyncio
async def test_list_assignments_by_class(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "q1@test.local")
        q_id = await _make_published_question(s)
        cls = ClassORM(name="C", teacher_id=teacher_id, invite_code="CODE0020", is_active=True)
        s.add(cls)
        await s.flush()
        cls_id = cls.id
        for i in range(3):
            s.add(
                AssignmentORM(
                    title=f"HW{i}",
                    class_id=cls_id,
                    teacher_id=teacher_id,
                    question_ids=[q_id],
                    status="draft",
                )
            )
        await s.commit()

    async with async_session() as s:
        service = AssignmentService(s)
        result = await service.list_class_assignments(cls_id)
        assert len(result) == 3


@pytest.mark.asyncio
async def test_list_assignments_filter_by_status(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "q2@test.local")
        q_id = await _make_published_question(s)
        cls = ClassORM(name="C", teacher_id=teacher_id, invite_code="CODE0021", is_active=True)
        s.add(cls)
        await s.flush()
        cls_id = cls.id
        s.add(
            AssignmentORM(
                title="HW1",
                class_id=cls_id,
                teacher_id=teacher_id,
                question_ids=[q_id],
                status="draft",
            )
        )
        s.add(
            AssignmentORM(
                title="HW2",
                class_id=cls_id,
                teacher_id=teacher_id,
                question_ids=[q_id],
                status="published",
            )
        )
        await s.commit()

    async with async_session() as s:
        service = AssignmentService(s)
        drafts = await service.list_class_assignments(cls_id, status="draft")
        published = await service.list_class_assignments(cls_id, status="published")
        assert len(drafts) == 1
        assert len(published) == 1


# ---------- TeacherDashboardService ----------


@pytest.mark.asyncio
async def test_dashboard_returns_empty_for_class_without_members(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "d1@test.local")
        cls = ClassORM(name="C", teacher_id=teacher_id, invite_code="CODE0030", is_active=True)
        s.add(cls)
        await s.flush()
        cls_id = cls.id
        await s.commit()

    async with async_session() as s:
        service = TeacherDashboardService(s)
        result = await service.get_class_dashboard(cls_id)
        assert result["member_count"] == 0
        assert result["avg_mastery"] == 0.0
        assert result["weak_knowledge_ids"] == []
        assert result["interventions"] == []


@pytest.mark.asyncio
async def test_dashboard_aggregates_mastery(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "d2@test.local")
        l1 = await _make_learner(s, "ds1")
        l2 = await _make_learner(s, "ds2")
        cls = ClassORM(name="C", teacher_id=teacher_id, invite_code="CODE0031", is_active=True)
        s.add(cls)
        await s.flush()
        cls_id = cls.id
        s.add(ClassMemberORM(class_id=cls_id, learner_id=l1))
        s.add(ClassMemberORM(class_id=cls_id, learner_id=l2))
        # 4 个 KnowledgeState: 2 个高掌握(0.9),2 个低掌握(0.1) -> avg=0.5
        s.add(
            KnowledgeStateORM(
                learner_id=l1, knowledge_id="kp_a", mastery=0.9, attempts=5
            )
        )
        s.add(
            KnowledgeStateORM(
                learner_id=l1, knowledge_id="kp_b", mastery=0.1, attempts=4
            )
        )
        s.add(
            KnowledgeStateORM(
                learner_id=l2, knowledge_id="kp_a", mastery=0.9, attempts=5
            )
        )
        s.add(
            KnowledgeStateORM(
                learner_id=l2, knowledge_id="kp_b", mastery=0.1, attempts=3
            )
        )
        await s.commit()

    async with async_session() as s:
        service = TeacherDashboardService(s)
        result = await service.get_class_dashboard(cls_id)
        assert result["member_count"] == 2
        assert result["total_states"] == 4
        # avg = (0.9 + 0.1 + 0.9 + 0.1) / 4 = 0.5
        assert abs(result["avg_mastery"] - 0.5) < 0.01
        # kp_b 的 avg = (0.1 + 0.1) / 2 = 0.1,应该出现在 weak_knowledge_ids
        weak_ids = [w["knowledge_id"] for w in result["weak_knowledge_ids"]]
        assert "kp_b" in weak_ids
        assert "kp_a" not in weak_ids


@pytest.mark.asyncio
async def test_dashboard_intervention_requires_low_mastery_and_attempts(test_engine):
    """干预推荐: mastery < 0.2 且 attempts >= 3。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        teacher_id = await _make_user(s, UserRole.TEACHER, "d3@test.local")
        l1 = await _make_learner(s, "di1")
        cls = ClassORM(name="C", teacher_id=teacher_id, invite_code="CODE0032", is_active=True)
        s.add(cls)
        await s.flush()
        cls_id = cls.id
        s.add(ClassMemberORM(class_id=cls_id, learner_id=l1))
        # 候选 1: mastery=0.1, attempts=5 -> 应该被推荐
        s.add(
            KnowledgeStateORM(
                learner_id=l1, knowledge_id="kp_low", mastery=0.1, attempts=5
            )
        )
        # 候选 2: mastery=0.15, attempts=2 -> attempts 不足,不推荐
        s.add(
            KnowledgeStateORM(
                learner_id=l1, knowledge_id="kp_few", mastery=0.15, attempts=2
            )
        )
        # 候选 3: mastery=0.3, attempts=10 -> mastery 不够低,不推荐
        s.add(
            KnowledgeStateORM(
                learner_id=l1, knowledge_id="kp_ok", mastery=0.3, attempts=10
            )
        )
        await s.commit()

    async with async_session() as s:
        service = TeacherDashboardService(s)
        result = await service.get_class_dashboard(cls_id)
        interventions = result["interventions"]
        assert len(interventions) == 1
        assert interventions[0]["knowledge_id"] == "kp_low"
        assert interventions[0]["learner_id"] == l1


@pytest.mark.asyncio
async def test_dashboard_returns_none_for_nonexistent_class(test_engine):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        service = TeacherDashboardService(s)
        result = await service.get_class_dashboard(99999)
        assert result is None
