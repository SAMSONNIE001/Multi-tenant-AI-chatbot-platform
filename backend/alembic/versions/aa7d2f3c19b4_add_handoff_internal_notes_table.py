"""add handoff internal notes table

Revision ID: aa7d2f3c19b4
Revises: f4b1a8d2c9e7
Create Date: 2026-03-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "aa7d2f3c19b4"
down_revision: Union[str, Sequence[str], None] = "f4b1a8d2c9e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "handoff_internal_notes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("handoff_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("author_user_id", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["handoff_id"], ["handoff_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_handoff_internal_notes_author_user_id"),
        "handoff_internal_notes",
        ["author_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_handoff_internal_notes_handoff_id"),
        "handoff_internal_notes",
        ["handoff_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_handoff_internal_notes_tenant_id"),
        "handoff_internal_notes",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_handoff_internal_notes_tenant_id"), table_name="handoff_internal_notes")
    op.drop_index(op.f("ix_handoff_internal_notes_handoff_id"), table_name="handoff_internal_notes")
    op.drop_index(op.f("ix_handoff_internal_notes_author_user_id"), table_name="handoff_internal_notes")
    op.drop_table("handoff_internal_notes")

