"""add critiques table (P2#16a LLM-as-judge CriticAgent)

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-28

变更:
1. 新建 critiques 表: CriticAgent 评估记录
2. 索引: learner_id, knowledge_id, teaching_event_id, created_at, tenant_id
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "critiques",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("learner_id", sa.String(length=64), nullable=False),
        sa.Column("knowledge_id", sa.String(length=128), nullable=False),
        sa.Column("teaching_event_id", sa.String(length=64), nullable=True),
        sa.Column("overall", sa.SmallInteger(), nullable=False),
        sa.Column(
            "scores",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("critique", sa.Text(), nullable=False),
        sa.Column(
            "needs_regeneration",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "regenerated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("original_response", sa.Text(), nullable=False),
        sa.Column("regenerated_response", sa.Text(), nullable=True),
        sa.Column("critic_model", sa.String(length=64), nullable=True),
        sa.Column("critic_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_critiques_learner_id", "critiques", ["learner_id"])
    op.create_index("ix_critiques_knowledge_id", "critiques", ["knowledge_id"])
    op.create_index(
        "ix_critiques_teaching_event_id", "critiques", ["teaching_event_id"]
    )
    op.create_index("ix_critiques_tenant_id", "critiques", ["tenant_id"])
    op.create_index("ix_critiques_created_at", "critiques", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_critiques_created_at", table_name="critiques")
    op.drop_index("ix_critiques_tenant_id", table_name="critiques")
    op.drop_index("ix_critiques_teaching_event_id", table_name="critiques")
    op.drop_index("ix_critiques_knowledge_id", table_name="critiques")
    op.drop_index("ix_critiques_learner_id", table_name="critiques")
    op.drop_table("critiques")
