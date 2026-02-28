"""expand handoff requests for inbox v1

Revision ID: e9f4b21c7a6d
Revises: c1d4e7f9a2b3
Create Date: 2026-02-27
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e9f4b21c7a6d"
down_revision = "c1d4e7f9a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "handoff_requests",
        sa.Column("assigned_to_user_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "handoff_requests",
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
    )
    op.add_column(
        "handoff_requests",
        sa.Column("first_response_due_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "handoff_requests",
        sa.Column("first_responded_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "handoff_requests",
        sa.Column("resolution_due_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "handoff_requests",
        sa.Column("closed_at", sa.DateTime(), nullable=True),
    )

    op.create_index(
        op.f("ix_handoff_requests_assigned_to_user_id"),
        "handoff_requests",
        ["assigned_to_user_id"],
        unique=False,
    )

    op.alter_column(
        "handoff_requests",
        "status",
        existing_type=sa.String(length=32),
        server_default="new",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "handoff_requests",
        "status",
        existing_type=sa.String(length=32),
        server_default="open",
        existing_nullable=False,
    )

    op.drop_index(op.f("ix_handoff_requests_assigned_to_user_id"), table_name="handoff_requests")
    op.drop_column("handoff_requests", "closed_at")
    op.drop_column("handoff_requests", "resolution_due_at")
    op.drop_column("handoff_requests", "first_responded_at")
    op.drop_column("handoff_requests", "first_response_due_at")
    op.drop_column("handoff_requests", "priority")
    op.drop_column("handoff_requests", "assigned_to_user_id")
