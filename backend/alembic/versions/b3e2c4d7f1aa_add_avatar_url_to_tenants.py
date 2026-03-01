"""add avatar_url to tenants

Revision ID: b3e2c4d7f1aa
Revises: a1d9f3c7b8e4
Create Date: 2026-03-01 00:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3e2c4d7f1aa"
down_revision: Union[str, Sequence[str], None] = "a1d9f3c7b8e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "avatar_url")

