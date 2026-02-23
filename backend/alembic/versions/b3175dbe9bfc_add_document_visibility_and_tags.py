"""add document visibility and tags

Revision ID: b3175dbe9bfc
Revises: 0432ad4c7d83
Create Date: 2026-02-21 12:34:34.523469

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3175dbe9bfc'
down_revision: Union[str, Sequence[str], None] = '0432ad4c7d83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("documents", sa.Column("visibility", sa.String(length=32), nullable=True))
    op.add_column("documents", sa.Column("tags", sa.JSON(), nullable=True))

    # Backfill existing rows before enforcing NOT NULL constraints.
    op.execute("UPDATE documents SET visibility = 'public' WHERE visibility IS NULL")
    op.execute("UPDATE documents SET tags = '[]'::json WHERE tags IS NULL")

    op.alter_column("documents", "visibility", nullable=False)
    op.alter_column("documents", "tags", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("documents", "tags")
    op.drop_column("documents", "visibility")
