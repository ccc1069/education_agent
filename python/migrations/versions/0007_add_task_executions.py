"""add task_executions table (P2#17 异步任务与定时调度)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_executions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_name", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            comment="running / success / failed / cancelled",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "triggered_by",
            sa.String(length=64),
            nullable=False,
            server_default="scheduler",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_executions_task_name", "task_executions", ["task_name"])
    op.create_index("ix_task_executions_status", "task_executions", ["status"])
    op.create_index(
        "ix_task_executions_started_at", "task_executions", ["started_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_task_executions_started_at", table_name="task_executions")
    op.drop_index("ix_task_executions_status", table_name="task_executions")
    op.drop_index("ix_task_executions_task_name", table_name="task_executions")
    op.drop_table("task_executions")
