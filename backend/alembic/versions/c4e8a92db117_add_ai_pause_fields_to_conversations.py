"""add ai pause fields to conversations

Revision ID: c4e8a92db117
Revises: b3e2c4d7f1aa
Create Date: 2026-03-01 00:25:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4e8a92db117"
down_revision: Union[str, Sequence[str], None] = "b3e2c4d7f1aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("ai_paused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "conversations",
        sa.Column("ai_paused_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("ai_paused_by_user_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "ai_paused_by_user_id")
    op.drop_column("conversations", "ai_paused_at")
    op.drop_column("conversations", "ai_paused")

