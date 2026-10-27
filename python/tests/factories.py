"""factory_boy 工厂: 用于测试数据生成。"""

import factory
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    KnowledgeNodeORM,
    KnowledgeStateORM,
    LearnerORM,
    SubmissionORM,
    UserORM,
    UserRole,
)


class AsyncSQLAlchemySession:
    """factory_boy 不直接支持 AsyncSession,这里用 stub。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def __call__(self, **kwargs):
        return self.session


class UserFactory(factory.Factory):
    class Meta:
        model = UserORM

    username = factory.Sequence(lambda n: f"user_{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    password_hash = "$2b$12$testhashplaceholderplaceholderplaceholderplaceholderval"
    role = UserRole.STUDENT
    is_active = True


class LearnerFactory(factory.Factory):
    class Meta:
        model = LearnerORM

    public_id = factory.Sequence(lambda n: f"learner_pub_{n:04d}")
    name = factory.Sequence(lambda n: f"学生{n}")
    grade = "高一"
    target = "高考"


class KnowledgeNodeFactory(factory.Factory):
    class Meta:
        model = KnowledgeNodeORM

    id = factory.Sequence(lambda n: f"kp_{n:03d}")
    name = factory.Sequence(lambda n: f"知识点{n}")
    difficulty = 0.5


class KnowledgeStateFactory(factory.Factory):
    class Meta:
        model = KnowledgeStateORM

    learner_id = 1
    knowledge_id = "kp_001"
    mastery = 0.5
    attempts = 0
    correct_count = 0
    version = 1


class SubmissionFactory(factory.Factory):
    class Meta:
        model = SubmissionORM

    learner_id = 1
    knowledge_id = "kp_001"
    is_correct = True
    time_spent_seconds = 30
    submitted_at = factory.Faker("date_time_this_month")
