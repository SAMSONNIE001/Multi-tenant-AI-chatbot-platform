"""add channel health fields

Revision ID: c1d4e7f9a2b3
Revises: 8e9c2a1f5b7d
Create Date: 2026-02-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1d4e7f9a2b3"
down_revision: Union[str, Sequence[str], None] = "8e9c2a1f5b7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenant_channel_accounts", sa.Column("last_webhook_at", sa.DateTime(), nullable=True))
    op.add_column("tenant_channel_accounts", sa.Column("last_outbound_at", sa.DateTime(), nullable=True))
    op.add_column("tenant_channel_accounts", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("tenant_channel_accounts", sa.Column("last_error_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenant_channel_accounts", "last_error_at")
    op.drop_column("tenant_channel_accounts", "last_error")
    op.drop_column("tenant_channel_accounts", "last_outbound_at")
    op.drop_column("tenant_channel_accounts", "last_webhook_at")

