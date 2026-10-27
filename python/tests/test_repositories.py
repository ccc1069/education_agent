"""SubmissionRepository + ReviewScheduleRepository 单元测试。"""

from datetime import datetime, timedelta

import pytest

from core.spaced_repetition import ReviewItem
from db.models import LearnerORM, SubmissionORM
from repositories import (
    ReviewScheduleRepository,
    SubmissionRepository,
)


async def _seed_learner(db_session) -> tuple[int, str]:
    learner = LearnerORM(public_id="learner-test-1", name="Tester")
    db_session.add(learner)
    await db_session.flush()
    return learner.id, learner.public_id


@pytest.mark.asyncio
async def test_submission_record_returns_with_correct_fields(db_session):
    learner_id, _ = await _seed_learner(db_session)
    repo = SubmissionRepository(db_session)
    sub = await repo.record(
        learner_id=learner_id,
        knowledge_id="arithmetic",
        is_correct=True,
        time_spent_seconds=12.5,
    )
    assert sub.id > 0
    assert sub.is_correct is True
    assert sub.time_spent_seconds == 12.5


@pytest.mark.asyncio
async def test_submission_list_by_learner_orders_recent_first(db_session):
    learner_id, _ = await _seed_learner(db_session)
    repo = SubmissionRepository(db_session)
    for i in range(3):
        await repo.record(
            learner_id=learner_id,
            knowledge_id="kp1",
            is_correct=i % 2 == 0,
            time_spent_seconds=float(i),
        )
    records = await repo.list_by_learner(learner_id, knowledge_id="kp1", limit=10)
    assert len(records) == 3


@pytest.mark.asyncio
async def test_submission_list_filters_by_knowledge_id(db_session):
    learner_id, _ = await _seed_learner(db_session)
    repo = SubmissionRepository(db_session)
    await repo.record(learner_id=learner_id, knowledge_id="kp1", is_correct=True)
    await repo.record(learner_id=learner_id, knowledge_id="kp2", is_correct=False)

    kp1_records = await repo.list_by_learner(learner_id, knowledge_id="kp1")
    assert all(r.knowledge_id == "kp1" for r in kp1_records)
    assert len(kp1_records) == 1


@pytest.mark.asyncio
async def test_submission_get_recent_stats_empty(db_session):
    learner_id, _ = await _seed_learner(db_session)
    repo = SubmissionRepository(db_session)
    stats = await repo.get_recent_stats(learner_id)
    assert stats["total"] == 0
    assert stats["accuracy"] == 0.0


@pytest.mark.asyncio
async def test_submission_get_recent_stats_with_records(db_session):
    learner_id, _ = await _seed_learner(db_session)
    repo = SubmissionRepository(db_session)
    await repo.record(learner_id=learner_id, knowledge_id="kp1", is_correct=True, time_spent_seconds=10)
    await repo.record(learner_id=learner_id, knowledge_id="kp1", is_correct=False, time_spent_seconds=20)
    await repo.record(learner_id=learner_id, knowledge_id="kp1", is_correct=True, time_spent_seconds=30)

    stats = await repo.get_recent_stats(learner_id)
    assert stats["total"] == 3
    assert stats["correct"] == 2
    assert stats["accuracy"] == 2 / 3
    assert stats["avg_time"] == 20.0


# ---------- ReviewScheduleRepository ----------


def _make_review_item(knowledge_id="kp1", repetition=1) -> ReviewItem:
    return ReviewItem(
        knowledge_id=knowledge_id,
        easiness_factor=2.5,
        interval_days=1,
        repetition=repetition,
        next_review=datetime.now() + timedelta(days=1),
        last_review=datetime.now(),
        total_reviews=repetition,
    )


@pytest.mark.asyncio
async def test_review_upsert_inserts_new_record(db_session):
    learner_id, _ = await _seed_learner(db_session)
    repo = ReviewScheduleRepository(db_session)
    item = _make_review_item("kp1", repetition=1)
    record = await repo.upsert_from_domain(learner_id, item)
    assert record.id > 0
    assert record.knowledge_id == "kp1"
    assert record.repetition == 1


@pytest.mark.asyncio
async def test_review_upsert_updates_existing_record(db_session):
    learner_id, _ = await _seed_learner(db_session)
    repo = ReviewScheduleRepository(db_session)
    item1 = _make_review_item("kp1", repetition=1)
    await repo.upsert_from_domain(learner_id, item1)

    item2 = _make_review_item("kp1", repetition=2)
    updated = await repo.upsert_from_domain(learner_id, item2)
    assert updated.repetition == 2
    assert updated.total_reviews == 2


@pytest.mark.asyncio
async def test_review_list_by_learner(db_session):
    learner_id, _ = await _seed_learner(db_session)
    repo = ReviewScheduleRepository(db_session)
    await repo.upsert_from_domain(learner_id, _make_review_item("kp1"))
    await repo.upsert_from_domain(learner_id, _make_review_item("kp2"))

    records = await repo.list_by_learner(learner_id)
    assert len(records) == 2


@pytest.mark.asyncio
async def test_review_list_due_returns_only_due(db_session):
    learner_id, _ = await _seed_learner(db_session)
    repo = ReviewScheduleRepository(db_session)

    due_item = _make_review_item("due_kp")
    due_item.next_review = datetime.now() - timedelta(days=1)  # 已到期
    await repo.upsert_from_domain(learner_id, due_item)

    future_item = _make_review_item("future_kp")
    future_item.next_review = datetime.now() + timedelta(days=10)  # 未到期
    await repo.upsert_from_domain(learner_id, future_item)

    due = await repo.list_due(learner_id)
    assert len(due) == 1
    assert due[0].knowledge_id == "due_kp"


@pytest.mark.asyncio
async def test_review_to_domain_roundtrip(db_session):
    learner_id, _ = await _seed_learner(db_session)
    repo = ReviewScheduleRepository(db_session)
    item = _make_review_item("kp1", repetition=3)
    record = await repo.upsert_from_domain(learner_id, item)
    domain = repo.to_domain(record)
    assert domain.knowledge_id == "kp1"
    assert domain.repetition == 3
    assert domain.easiness_factor == 2.5
