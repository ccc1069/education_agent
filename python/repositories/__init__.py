"""仓储层: 领域对象与 ORM 之间的转换 + 持久化操作。"""

from repositories.base import BaseRepository
from repositories.learner_repository import LearnerRepository
from repositories.knowledge_state_repository import KnowledgeStateRepository
from repositories.submission_repository import SubmissionRepository
from repositories.event_repository import EventRepository
from repositories.knowledge_graph_repository import KnowledgeGraphRepository
from repositories.review_repository import ReviewScheduleRepository
from repositories.user_repository import RefreshTokenRepository, UserRepository
from repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
)
from repositories.question_repository import QuestionRepository
from repositories.class_repository import (
    AssignmentRepository,
    ClassRepository,
)
from repositories.privacy_repository import (
    AuditRepository,
    DataExportJobRepository,
    PrivacyConsentRepository,
    PrivacyDeletionRepository,
)
from repositories.task_repository import TaskExecutionRepository
from repositories.tenant_repository import (
    TenantQuotaRepository,
    TenantRepository,
)
from repositories.notification_repository import (
    NotificationPreferenceRepository,
    NotificationRepository,
)

__all__ = [
    "BaseRepository",
    "LearnerRepository",
    "KnowledgeStateRepository",
    "SubmissionRepository",
    "EventRepository",
    "KnowledgeGraphRepository",
    "ReviewScheduleRepository",
    "UserRepository",
    "RefreshTokenRepository",
    "DocumentRepository",
    "DocumentChunkRepository",
    "QuestionRepository",
    "ClassRepository",
    "AssignmentRepository",
    "AuditRepository",
    "PrivacyConsentRepository",
    "PrivacyDeletionRepository",
    "DataExportJobRepository",
    "TaskExecutionRepository",
    "NotificationRepository",
    "NotificationPreferenceRepository",
    "TenantRepository",
    "TenantQuotaRepository",
]
