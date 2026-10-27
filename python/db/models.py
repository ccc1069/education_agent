"""SQLAlchemy ORM 模型。

设计要点:
- BigInteger 主键(避免 Int32 上限)
- created_at/updated_at: 服务器时区 + server_default=now()
- 乐观锁: knowledge_states.version 字段
- 软删除: 不采用(教育数据需保留,改用 audit_logs)
- JSONB: events.data 存事件载荷,知识图谱 tags 存标签数组
- 外部可见 ID: learners.public_id / knowledge_nodes.public_id / events.public_id
- 不暴露内部自增 ID 给客户端
"""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from db.base import Base


# 跨方言 JSON 类型: PG 用 JSONB(支持索引),SQLite 用 JSON(测试用)
JSONType = JSON().with_variant(JSONB(), "postgresql")

# 跨方言主键类型: PG 用 BigInteger,SQLite 用 Integer(支持 autoincrement)
BigIntPK = Integer().with_variant(BigInteger(), "postgresql")


class UserRole(str, enum.Enum):
    """用户角色枚举。"""

    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
    PARENT = "parent"
    AUDITOR = "auditor"


# 与迁移 0002 的 PG 类型名一致；持久化 value（admin）而非成员名（ADMIN）
UserRoleColumn = SAEnum(
    UserRole,
    name="user_role",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    native_enum=True,
    create_constraint=False,
)


class LearnerORM(Base):
    """学习者基础信息。"""

    __tablename__ = "learners"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    public_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, comment="外部可见的 learner_id"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    profile: Mapped[dict[str, Any]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<LearnerORM id={self.id} public_id={self.public_id!r}>"


class UserORM(Base):
    """用户账号(可登录实体)。学生 / 教师 / 管理员 / 家长 / 审计员。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        UserRoleColumn, default=UserRole.STUDENT, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    learner_id: Mapped[int | None] = mapped_column(
        ForeignKey("learners.id", ondelete="SET NULL"), nullable=True, index=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    learner: Mapped["LearnerORM | None"] = relationship(backref="user", lazy="selectin")

    def __repr__(self) -> str:
        return f"<UserORM id={self.id} email={self.email!r} role={self.role}>"


class RefreshTokenORM(Base):
    """Refresh Token 单次使用(撤销后不可重放)。"""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, comment="SHA-256(token)"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KnowledgeNodeORM(Base):
    """知识点(知识图谱节点)。"""

    __tablename__ = "knowledge_nodes"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, comment="知识点 ID, 如 arithmetic"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    subject: Mapped[str] = mapped_column(String(32), nullable=False, default="math")
    difficulty: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default="[]"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class KnowledgePrerequisiteORM(Base):
    """知识点的前置关系(自引用 M:N)。"""

    __tablename__ = "knowledge_prerequisites"

    node_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    prerequisite_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_kp_node_id", "node_id"),
        Index("ix_kp_prerequisite_id", "prerequisite_id"),
    )


class KnowledgeStateORM(Base):
    """学习者对某知识点的掌握状态(BKT)。"""

    __tablename__ = "knowledge_states"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    knowledge_id: Mapped[str] = mapped_column(String(64), nullable=False)
    mastery: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    alpha: Mapped[float] = mapped_column(Float, nullable=False, default=0.1)
    beta: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("learner_id", "knowledge_id", name="uq_state_learner_knowledge"),
    )


class SubmissionORM(Base):
    """学生答题记录。"""

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_id: Mapped[str] = mapped_column(String(64), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    time_spent_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_submissions_learner_knowledge", "learner_id", "knowledge_id"),
        Index("ix_submissions_created_at", "created_at"),
    )


class ReviewScheduleORM(Base):
    """复习计划(SM-2 算法)。"""

    __tablename__ = "review_schedules"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    knowledge_id: Mapped[str] = mapped_column(String(64), nullable=False)
    easiness_factor: Mapped[float] = mapped_column(Float, nullable=False, default=2.5)
    interval_days: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    repetition: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_reviews: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_review: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("learner_id", "knowledge_id", name="uq_review_learner_knowledge"),
    )


class EventORM(Base):
    """事件溯源: 所有 Agent 间通信的事件持久化。"""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    public_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, comment="事件 UUID"
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    learner_public_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_events_learner_type", "learner_public_id", "type"),
    )


class AuditLogORM(Base):
    """审计日志: 敏感操作记录 + HMAC 链(不可篡改)。

    HMAC 链: curr_hash = HMAC(secret, prev_hash || id || actor || action || target || created_at)    - 任何字段被改 → 后续所有 hash 校验失败
    - prev_hash 为空表示链首
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(256), nullable=False)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    prev_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", comment="上一条日志的 curr_hash"
    )
    curr_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="",
        index=True,
        comment="本条日志的 HMAC,空表示未计算",
    )


class DocumentORM(Base):
    """RAG 知识库文档(教材/讲义/笔记)。"""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="text", comment="text/markdown/pdf/docx"
    )
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, comment="SHA-256 用于去重"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )  # pending / indexing / indexed / failed
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    chunks: Mapped[list["DocumentChunkORM"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunkORM(Base):
    """文档分块(语义切分 + embedding)。embedding 以 JSON 数组存储,跨方言兼容。"""

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    document_id: Mapped[int] = mapped_column(
        BigIntPK,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        JSONType, nullable=False, comment="向量存储为 JSON 数组(跨方言)"
    )
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[DocumentORM] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_doc_index"),
    )


class QuestionORM(Base):
    """题目库(教师/LLM 生成,供学生练习)。

    状态机: draft -> review -> published -> archived
    去重: content_embedding 用于相似度检索,避免重复题目
    """

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    knowledge_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="关联知识点 ID"
    )
    question_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="multiple_choice / fill_blank / open_ended / true_false",
    )
    difficulty: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, comment="1-5 难度等级"
    )
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        comment="题干 + 选项 + 答案(JSON 结构按题型而定)",
    )
    answer: Mapped[str] = mapped_column(Text, nullable=False, comment="标准答案")
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True, comment="解析")
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        index=True,
        comment="draft / review / published / archived / rejected",
    )
    content_embedding: Mapped[list[float]] = mapped_column(
        JSONType, nullable=True, comment="题目文本 embedding,用于去重与相似检索"
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True, comment="创建者 user_id"
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------- P2#12 教师后台与班级管理 ----------


class ClassORM(Base):
    """教学班级(教师创建,学生通过邀请码加入)。

    一个教师可创建多个班级;一个学生可加入多个班级(多对多)。
    """

    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invite_code: Mapped[str] = mapped_column(
        String(16), unique=True, index=True, nullable=False, comment="学生加入码"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    teacher: Mapped["UserORM"] = relationship(lazy="selectin")
    members: Mapped[list["ClassMemberORM"]] = relationship(
        back_populates="class_", cascade="all, delete-orphan"
    )


class ClassMemberORM(Base):
    """班级成员(学生 + 班级 多对多)。"""

    __tablename__ = "class_members"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    class_: Mapped["ClassORM"] = relationship(back_populates="members")

    __table_args__ = (
        UniqueConstraint("class_id", "learner_id", name="uq_class_member"),
    )


class AssignmentORM(Base):
    """作业(教师布置,关联多个题目)。

    状态机: draft -> published -> closed
    """

    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_ids: Mapped[list[int]] = mapped_column(
        JSONType, nullable=False, default=list, comment="题目 ID 列表"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", index=True
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="截止时间"
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    class_: Mapped["ClassORM"] = relationship(lazy="selectin")


# ---------- P2#15 数据合规与隐私 ----------


class PrivacyConsentORM(Base):
    """用户隐私同意记录(版本化)。

    每次同意/撤回都新增一行,不修改历史。查询当前状态取最新一行。
    """

    __tablename__ = "privacy_consents"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consent_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="analytics / llm_training / marketing / third_party_share",
    )
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="1.0"
    )
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_consent_user_type", "user_id", "consent_type"),
    )


class PrivacyDeletionRequestORM(Base):
    """账户删除请求(30 天宽限期,期间可撤销)。

    状态机: pending -> scheduled -> executing -> completed / cancelled
    - pending: 用户提交,等待宽限期结束
    - scheduled: 系统标记开始执行(定时任务扫描)
    - executing: 正在删除关联数据
    - completed: 已彻底删除(软删 + 物理删除敏感字段)
    - cancelled: 用户在宽限期内撤销
    """

    __tablename__ = "privacy_deletion_requests"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="预计执行时间(30 天后)"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default="{}"
    )


class DataExportJobORM(Base):
    """数据导出任务(异步生成,完成后用户下载)。

    状态: pending -> running -> completed / failed
    """

    __tablename__ = "data_export_jobs"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    download_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default="{}"
    )


# ---------- P2#17 异步任务与定时调度 ----------


class TaskExecutionORM(Base):
    """任务执行历史(用于审计 + 监控)。

    每次任务执行(无论成功/失败)都新增一行。
    """

    __tablename__ = "task_executions"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    task_name: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="任务名"
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
        comment="running / success / failed / cancelled",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict, server_default="{}"
    )
    triggered_by: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="scheduler",
        comment="scheduler / manual / webhook",
    )


# ---------- P2#18 推送通知系统 ----------


class NotificationORM(Base):
    """通知记录。

    每条通知持久化: status 跟踪 pending -> sent -> delivered -> read / failed。
    channel 决定投递渠道(ws/email/push)。
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="review_reminder / class_event / teacher_feedback / system",
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="ws / email / push"
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
        default="pending",
        comment="pending / sent / delivered / read / failed",
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="0=低 1=中 2=高"
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default="{}"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NotificationPreferenceORM(Base):
    """用户通知偏好(每用户一行)。

    - 各渠道开关(ws/email/push)
    - 勿扰时段(UTC 小时,0-23)
    - min_priority: 低于此优先级的通知不投递(但仍持久化)
    """

    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, unique=True, index=True
    )
    ws_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quiet_hours_start: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="UTC 0-23"
    )
    quiet_hours_end: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="UTC 0-23"
    )
    min_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ----------
# 多租户(P2#11)
# ----------


class TenantORM(Base):
    """租户(学校/培训机构)。

    - 共享库 + 行级隔离: 所有业务表带 tenant_id 列
    - 全局知识图谱不按租户隔离(全局共享)
    - plan 决定配额默认值(free/pro/enterprise)
    """

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, comment="URL 友好的短标识"
    )
    plan: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="free",
        index=True,
        comment="free / pro / enterprise",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantQuotaORM(Base):
    """租户配额与当月用量。

    - max_users / max_llm_tokens_per_month: 上限
    - current_llm_tokens: 当月已用,月初重置
    - period_start: 当前计费周期起始
    """

    __tablename__ = "tenant_quotas"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, unique=True, index=True
    )
    max_users: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, comment="最大用户数"
    )
    max_llm_tokens_per_month: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100_000
    )
    current_llm_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ----------
# Critic 评估记录(P2#16a LLM-as-judge)
# ----------


class CritiqueORM(Base):
    """CriticAgent 对教学回复的评估记录。

    - 每条 TEACHING_RESPONSE 评估一次(可选,LLM 不可用时不记录)
    - low_score 时触发自反思再生成,记录 regenerated_response
    - 用于离线分析 LLM 教学质量、Critic 准确性
    """

    __tablename__ = "critiques"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    knowledge_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    teaching_event_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="对应 TEACHING_RESPONSE 事件 id"
    )
    # 评估结果
    overall: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="1-5 总分")
    scores: Mapped[dict[str, Any]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default="{}"
    )
    critique: Mapped[str] = mapped_column(Text, nullable=False)
    needs_regeneration: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # 重生成结果
    regenerated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    original_response: Mapped[str] = mapped_column(Text, nullable=False)
    regenerated_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    # LLM 元数据
    critic_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    critic_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        default=1,
        server_default="1",
        index=True,
        comment="租户隔离(P2#11)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
