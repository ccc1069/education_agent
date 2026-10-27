"""add questions table (P2#13 题目生成与题库)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "questions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("knowledge_id", sa.String(length=64), nullable=False),
        sa.Column("question_type", sa.String(length=32), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("analysis", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column(
            "content_embedding",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_questions_knowledge_id", "questions", ["knowledge_id"])
    op.create_index("ix_questions_status", "questions", ["status"])
    op.create_index("ix_questions_created_by", "questions", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_questions_created_by", table_name="questions")
    op.drop_index("ix_questions_status", table_name="questions")
    op.drop_index("ix_questions_knowledge_id", table_name="questions")
    op.drop_table("questions")
