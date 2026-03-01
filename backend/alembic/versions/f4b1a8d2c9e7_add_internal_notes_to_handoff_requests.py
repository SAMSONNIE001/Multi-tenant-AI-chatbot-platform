"""add internal notes to handoff requests

Revision ID: f4b1a8d2c9e7
Revises: c4e8a92db117
Create Date: 2026-03-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f4b1a8d2c9e7"
down_revision: Union[str, Sequence[str], None] = "c4e8a92db117"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "handoff_requests",
        sa.Column("internal_notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("handoff_requests", "internal_notes")

