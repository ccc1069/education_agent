"""Repository 测试: 使用 SQLite in-memory 验证 CRUD + upsert + load。"""

import pytest

from db.models import KnowledgeNodeORM, LearnerORM, UserORM, UserRole


@pytest.mark.asyncio
async def test_learner_repository_add_and_get(db_session):
    from repositories import LearnerRepository

    repo = LearnerRepository(db_session)
    learner = await repo.add(LearnerORM(public_id="pub_001", name="张三"))
    await db_session.commit()

    fetched = await repo.get_by_public_id("pub_001")
    assert fetched is not None
    assert fetched.name == "张三"


@pytest.mark.asyncio
async def test_learner_repository_get_or_create_idempotent(db_session):
    from repositories import LearnerRepository

    repo = LearnerRepository(db_session)
    learner1 = await repo.get_or_create("pub_001", name="A")
    await db_session.commit()

    learner2 = await repo.get_or_create("pub_001", name="A")
    await db_session.commit()

    assert learner1.id == learner2.id


@pytest.mark.asyncio
async def test_knowledge_state_upsert(db_session):
    """upsert_from_domain 应在新建时 insert,再次调用时 update。"""
    from repositories import KnowledgeStateRepository, LearnerRepository

    learner_repo = LearnerRepository(db_session)
    learner = await learner_repo.add(LearnerORM(public_id="pub_001", name="A"))
    db_session.add(KnowledgeNodeORM(public_id="kp1", name="K1", difficulty=0.5))
    await db_session.commit()
    await db_session.refresh(learner)

    repo = KnowledgeStateRepository(db_session)
    await repo.upsert_from_domain(
        learner_id=learner.id,
        knowledge_id="kp1",
        state_dict={"mastery": 0.3, "attempts": 2, "correct_count": 1},
    )
    await db_session.commit()

    states = await repo.list_by_learner(learner.id)
    assert len(states) == 1
    assert states[0].mastery == 0.3
    assert states[0].attempts == 2

    # 第二次 upsert 应更新,而不是新建
    await repo.upsert_from_domain(
        learner_id=learner.id,
        knowledge_id="kp1",
        state_dict={"mastery": 0.5, "attempts": 4, "correct_count": 2},
    )
    await db_session.commit()
    states = await repo.list_by_learner(learner.id)
    assert len(states) == 1  # 仍只有一条
    assert states[0].mastery == 0.5


@pytest.mark.asyncio
async def test_user_repository_add_and_lookup(db_session):
    from repositories import UserRepository

    repo = UserRepository(db_session)
    user = await repo.add(
        UserORM(
            email="test@example.com",
            password_hash="hashed",
            role=UserRole.STUDENT,
        )
    )
    await db_session.commit()

    fetched = await repo.get_by_email("test@example.com")
    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.role == UserRole.STUDENT


@pytest.mark.asyncio
async def test_knowledge_graph_repository_load_empty(db_session):
    """空 DB 加载时返回 None。"""
    from repositories import KnowledgeGraphRepository

    repo = KnowledgeGraphRepository(db_session)
    graph = await repo.load_full_graph()
    assert graph is None or len(graph.nodes) == 0


@pytest.mark.asyncio
async def test_knowledge_graph_repository_seed_and_load(db_session):
    """写入示例 graph 后应能读回。"""
    from core.knowledge_graph import build_sample_math_graph
    from repositories import KnowledgeGraphRepository

    repo = KnowledgeGraphRepository(db_session)
    sample = build_sample_math_graph()
    await repo.seed_from_domain_graph(sample)
    await db_session.commit()

    loaded = await repo.load_full_graph()
    assert loaded is not None
    assert len(loaded.nodes) == len(sample.nodes)


@pytest.mark.asyncio
async def test_event_repository_append(db_session):
    """EventRepository 应能写入事件。"""
    from datetime import datetime, timezone

    from core.event_bus import Event, EventType
    from repositories import EventRepository

    repo = EventRepository(db_session)
    event = Event(
        type=EventType.STUDENT_SUBMISSION,
        source="test",
        learner_id="learner_1",
        data={"knowledge_id": "kp1", "is_correct": True},
    )
    event.timestamp = datetime.now(timezone.utc)

    await repo.append(event)
    await db_session.commit()

    events = await repo.list_by_learner("learner_1", limit=10)
    assert len(events) == 1
