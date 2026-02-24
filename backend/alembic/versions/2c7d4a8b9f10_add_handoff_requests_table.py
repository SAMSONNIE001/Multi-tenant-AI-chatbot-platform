"""add handoff requests table

Revision ID: 2c7d4a8b9f10
Revises: 6f1d9a2c4b3e
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2c7d4a8b9f10"
down_revision = "6f1d9a2c4b3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "handoff_requests",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("source_channel", sa.String(length=32), nullable=False, server_default="api"),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("destination", sa.String(length=255), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_handoff_requests_tenant_id"), "handoff_requests", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_handoff_requests_conversation_id"), "handoff_requests", ["conversation_id"], unique=False)
    op.create_index(op.f("ix_handoff_requests_user_id"), "handoff_requests", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_handoff_requests_user_id"), table_name="handoff_requests")
    op.drop_index(op.f("ix_handoff_requests_conversation_id"), table_name="handoff_requests")
    op.drop_index(op.f("ix_handoff_requests_tenant_id"), table_name="handoff_requests")
    op.drop_table("handoff_requests")
