"""add privacy tables + audit_logs HMAC chain columns (P2#15 数据合规与隐私)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # audit_logs: 新增 HMAC 链字段
    op.add_column(
        "audit_logs",
        sa.Column(
            "prev_hash",
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "audit_logs",
        sa.Column(
            "curr_hash",
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
    )
    op.create_index("ix_audit_curr_hash", "audit_logs", ["curr_hash"])

    # privacy_consents
    op.create_table(
        "privacy_consents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("consent_type", sa.String(length=32), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column(
            "consent_version", sa.String(length=16), nullable=False, server_default="1.0"
        ),
        sa.Column("ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "user_agent", sa.String(length=256), nullable=False, server_default=""
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_privacy_consents_user_id", "privacy_consents", ["user_id"])
    op.create_index(
        "ix_privacy_consents_consent_type", "privacy_consents", ["consent_type"]
    )
    op.create_index(
        "ix_consent_user_type", "privacy_consents", ["user_id", "consent_type"]
    )
    op.create_index(
        "ix_privacy_consents_created_at", "privacy_consents", ["created_at"]
    )

    # privacy_deletion_requests
    op.create_table(
        "privacy_deletion_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_privacy_deletion_requests_user_id",
        "privacy_deletion_requests",
        ["user_id"],
    )
    op.create_index(
        "ix_privacy_deletion_requests_status",
        "privacy_deletion_requests",
        ["status"],
    )

    # data_export_jobs
    op.create_table(
        "data_export_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("download_url", sa.String(length=512), nullable=True),
        sa.Column(
            "file_size_bytes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_export_jobs_user_id", "data_export_jobs", ["user_id"])
    op.create_index("ix_data_export_jobs_status", "data_export_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_data_export_jobs_status", table_name="data_export_jobs")
    op.drop_index("ix_data_export_jobs_user_id", table_name="data_export_jobs")
    op.drop_table("data_export_jobs")

    op.drop_index(
        "ix_privacy_deletion_requests_status", table_name="privacy_deletion_requests"
    )
    op.drop_index(
        "ix_privacy_deletion_requests_user_id", table_name="privacy_deletion_requests"
    )
    op.drop_table("privacy_deletion_requests")

    op.drop_index("ix_privacy_consents_created_at", table_name="privacy_consents")
    op.drop_index("ix_consent_user_type", table_name="privacy_consents")
    op.drop_index("ix_privacy_consents_consent_type", table_name="privacy_consents")
    op.drop_index("ix_privacy_consents_user_id", table_name="privacy_consents")
    op.drop_table("privacy_consents")

    op.drop_index("ix_audit_curr_hash", table_name="audit_logs")
    op.drop_column("audit_logs", "curr_hash")
    op.drop_column("audit_logs", "prev_hash")
