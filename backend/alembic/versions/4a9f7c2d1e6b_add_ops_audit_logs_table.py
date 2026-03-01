"""add ops audit logs table

Revision ID: 4a9f7c2d1e6b
Revises: e3c9b7a1d4f2
Create Date: 2026-03-01 23:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4a9f7c2d1e6b"
down_revision: Union[str, Sequence[str], None] = "e3c9b7a1d4f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ops_audit_logs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ops_audit_logs_tenant_id"), "ops_audit_logs", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_ops_audit_logs_actor_user_id"), "ops_audit_logs", ["actor_user_id"], unique=False)
    op.create_index(op.f("ix_ops_audit_logs_action_type"), "ops_audit_logs", ["action_type"], unique=False)
    op.create_index("ix_ops_audit_tenant_created_at", "ops_audit_logs", ["tenant_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ops_audit_tenant_created_at", table_name="ops_audit_logs")
    op.drop_index(op.f("ix_ops_audit_logs_action_type"), table_name="ops_audit_logs")
    op.drop_index(op.f("ix_ops_audit_logs_actor_user_id"), table_name="ops_audit_logs")
    op.drop_index(op.f("ix_ops_audit_logs_tenant_id"), table_name="ops_audit_logs")
    op.drop_table("ops_audit_logs")

