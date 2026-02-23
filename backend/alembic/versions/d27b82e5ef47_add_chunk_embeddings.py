"""add chunk embeddings

Revision ID: d27b82e5ef47
Revises: b62df508a8ec
Create Date: 2026-02-19
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = "d27b82e5ef47"
down_revision = "b62df508a8ec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("embedding", Vector(1536), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "embedding")
