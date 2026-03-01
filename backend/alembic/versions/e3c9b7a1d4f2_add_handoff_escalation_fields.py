"""add handoff escalation fields

Revision ID: e3c9b7a1d4f2
Revises: d2f6c1ab4e90
Create Date: 2026-03-01 20:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e3c9b7a1d4f2"
down_revision: Union[str, Sequence[str], None] = "d2f6c1ab4e90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "handoff_requests",
        sa.Column("escalation_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "handoff_requests",
        sa.Column("escalated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("handoff_requests", "escalated_at")
    op.drop_column("handoff_requests", "escalation_flag")
