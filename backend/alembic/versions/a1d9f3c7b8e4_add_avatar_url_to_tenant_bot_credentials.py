"""add avatar_url to tenant_bot_credentials

Revision ID: a1d9f3c7b8e4
Revises: e9f4b21c7a6d
Create Date: 2026-03-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1d9f3c7b8e4"
down_revision: Union[str, Sequence[str], None] = "e9f4b21c7a6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenant_bot_credentials",
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_bot_credentials", "avatar_url")

