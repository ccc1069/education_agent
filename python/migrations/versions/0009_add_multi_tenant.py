"""add multi-tenant tables + tenant_id columns (P2#11 多租户)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-28

变更:
1. 新建 tenants 表(租户)
2. 新建 tenant_quotas 表(配额)
3. 插入默认租户 id=1 slug='default'
4. 给所有业务表加 tenant_id 列(BigInt, NOT NULL, default=1, index)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 需要加 tenant_id 的业务表(共享库行级隔离)
# 知识图谱(knowledge_nodes/prerequisites)保持全局共享
TENANT_TABLES = [
    "users",
    "learners",
    "knowledge_states",
    "submissions",
    "review_schedules",
    "events",
    "audit_logs",
    "documents",
    "document_chunks",
    "questions",
    "classes",
    "class_members",
    "assignments",
    "privacy_consents",
    "privacy_deletion_requests",
    "data_export_jobs",
    "task_executions",
    "notifications",
    "notification_preferences",
]


def upgrade() -> None:
    # 1. tenants 表
    op.create_table(
        "tenants",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "slug",
            sa.String(length=64),
            nullable=False,
            comment="URL 友好的短标识",
        ),
        sa.Column(
            "plan",
            sa.String(length=16),
            nullable=False,
            server_default="free",
            comment="free / pro / enterprise",
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "settings",
            sa.JSON().with_variant(
                sa.dialects.postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])
    op.create_index("ix_tenants_plan", "tenants", ["plan"])

    # 2. tenant_quotas 表
    op.create_table(
        "tenant_quotas",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("max_users", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "max_llm_tokens_per_month",
            sa.Integer(),
            nullable=False,
            server_default="100000",
        ),
        sa.Column(
            "current_llm_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "period_start",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_quotas_tenant_id"),
    )
    op.create_index("ix_tenant_quotas_tenant_id", "tenant_quotas", ["tenant_id"])

    # 3. 插入默认租户
    op.execute(
        "INSERT INTO tenants (id, name, slug, plan) VALUES (1, 'Default', 'default', 'enterprise')"
    )
    op.execute(
        "INSERT INTO tenant_quotas (tenant_id, max_users, max_llm_tokens_per_month) "
        "VALUES (1, 100000, 10000000)"
    )

    # 4. 给业务表加 tenant_id 列
    for table in TENANT_TABLES:
        op.add_column(
            table,
            sa.Column(
                "tenant_id",
                sa.BigInteger(),
                nullable=False,
                server_default="1",
            ),
        )
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        # 加外键(允许引用 tenants)
        op.create_foreign_key(
            f"fk_{table}_tenant_id_tenants",
            table,
            "tenants",
            ["tenant_id"],
            ["id"],
        )


def downgrade() -> None:
    # 先删外键和索引
    for table in TENANT_TABLES:
        op.drop_constraint(
            f"fk_{table}_tenant_id_tenants", table, type_="foreignkey"
        )
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")

    op.drop_index("ix_tenant_quotas_tenant_id", table_name="tenant_quotas")
    op.drop_table("tenant_quotas")
    op.drop_index("ix_tenants_plan", table_name="tenants")
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
