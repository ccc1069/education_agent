"""initial schema: learners, knowledge_states, submissions, events, review_schedules, knowledge_graph, audit_logs

Revision ID: 0001
Revises:
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learners",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="外部可见的 learner_id"),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_learners_public_id", "learners", ["public_id"])

    op.create_table(
        "knowledge_nodes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="知识点 ID, 如 arithmetic"),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("subject", sa.String(length=32), nullable=False),
        sa.Column("difficulty", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_knowledge_nodes_public_id", "knowledge_nodes", ["public_id"])

    op.create_table(
        "knowledge_prerequisites",
        sa.Column("node_id", sa.BigInteger(), nullable=False),
        sa.Column("prerequisite_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["knowledge_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prerequisite_id"], ["knowledge_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("node_id", "prerequisite_id"),
    )
    op.create_index("ix_kp_node_id", "knowledge_prerequisites", ["node_id"])
    op.create_index("ix_kp_prerequisite_id", "knowledge_prerequisites", ["prerequisite_id"])

    op.create_table(
        "knowledge_states",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("learner_id", sa.BigInteger(), nullable=False),
        sa.Column("knowledge_id", sa.String(length=64), nullable=False),
        sa.Column("mastery", sa.Float(), nullable=False),
        sa.Column("alpha", sa.Float(), nullable=False),
        sa.Column("beta", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("streak", sa.Integer(), nullable=False),
        sa.Column("last_attempt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("learner_id", "knowledge_id", name="uq_state_learner_knowledge"),
    )
    op.create_index("ix_state_learner_id", "knowledge_states", ["learner_id"])

    op.create_table(
        "submissions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("learner_id", sa.BigInteger(), nullable=False),
        sa.Column("knowledge_id", sa.String(length=64), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("time_spent_seconds", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_submissions_learner_knowledge", "submissions", ["learner_id", "knowledge_id"])
    op.create_index("ix_submissions_created_at", "submissions", ["created_at"])

    op.create_table(
        "review_schedules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("learner_id", sa.BigInteger(), nullable=False),
        sa.Column("knowledge_id", sa.String(length=64), nullable=False),
        sa.Column("easiness_factor", sa.Float(), nullable=False),
        sa.Column("interval_days", sa.Float(), nullable=False),
        sa.Column("repetition", sa.Integer(), nullable=False),
        sa.Column("total_reviews", sa.Integer(), nullable=False),
        sa.Column("next_review", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_review", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("learner_id", "knowledge_id", name="uq_review_learner_knowledge"),
    )
    op.create_index("ix_review_learner_id", "review_schedules", ["learner_id"])
    op.create_index("ix_review_next_review", "review_schedules", ["next_review"])

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="事件 UUID"),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("learner_public_id", sa.String(length=64), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_events_public_id", "events", ["public_id"])
    op.create_index("ix_events_type", "events", ["type"])
    op.create_index("ix_events_learner_public_id", "events", ["learner_public_id"])
    op.create_index("ix_events_correlation_id", "events", ["correlation_id"])
    op.create_index("ix_events_learner_type", "events", ["learner_public_id", "type"])
    op.create_index("ix_events_timestamp", "events", ["timestamp"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=256), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=256), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_index("ix_events_timestamp", table_name="events")
    op.drop_index("ix_events_learner_type", table_name="events")
    op.drop_index("ix_events_correlation_id", table_name="events")
    op.drop_index("ix_events_learner_public_id", table_name="events")
    op.drop_index("ix_events_type", table_name="events")
    op.drop_index("ix_events_public_id", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_review_next_review", table_name="review_schedules")
    op.drop_index("ix_review_learner_id", table_name="review_schedules")
    op.drop_table("review_schedules")
    op.drop_index("ix_submissions_created_at", table_name="submissions")
    op.drop_index("ix_submissions_learner_knowledge", table_name="submissions")
    op.drop_table("submissions")
    op.drop_index("ix_state_learner_id", table_name="knowledge_states")
    op.drop_table("knowledge_states")
    op.drop_index("ix_kp_prerequisite_id", table_name="knowledge_prerequisites")
    op.drop_index("ix_kp_node_id", table_name="knowledge_prerequisites")
    op.drop_table("knowledge_prerequisites")
    op.drop_index("ix_knowledge_nodes_public_id", table_name="knowledge_nodes")
    op.drop_table("knowledge_nodes")
    op.drop_index("ix_learners_public_id", table_name="learners")
    op.drop_table("learners")
