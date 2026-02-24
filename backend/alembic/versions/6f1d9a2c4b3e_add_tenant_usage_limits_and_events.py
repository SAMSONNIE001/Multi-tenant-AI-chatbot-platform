"""add tenant usage limits and events

Revision ID: 6f1d9a2c4b3e
Revises: f0a1c9b6e2d4
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6f1d9a2c4b3e"
down_revision = "f0a1c9b6e2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_usage_limits",
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("daily_request_limit", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("monthly_token_limit", sa.Integer(), nullable=False, server_default="1000000"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id"),
    )

    op.create_table(
        "tenant_usage_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("refused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_tenant_usage_events_tenant_id"), "tenant_usage_events", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_tenant_usage_events_user_id"), "tenant_usage_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_tenant_usage_events_created_at"), "tenant_usage_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tenant_usage_events_created_at"), table_name="tenant_usage_events")
    op.drop_index(op.f("ix_tenant_usage_events_user_id"), table_name="tenant_usage_events")
    op.drop_index(op.f("ix_tenant_usage_events_tenant_id"), table_name="tenant_usage_events")
    op.drop_table("tenant_usage_events")
    op.drop_table("tenant_usage_limits")
