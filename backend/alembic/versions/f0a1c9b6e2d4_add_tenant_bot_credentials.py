"""add tenant bot credentials

Revision ID: f0a1c9b6e2d4
Revises: d27b82e5ef47
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f0a1c9b6e2d4"
down_revision = "d27b82e5ef47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_bot_credentials",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("allowed_origins", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenant_bot_credentials_key_hash"), "tenant_bot_credentials", ["key_hash"], unique=True)
    op.create_index(op.f("ix_tenant_bot_credentials_tenant_id"), "tenant_bot_credentials", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tenant_bot_credentials_tenant_id"), table_name="tenant_bot_credentials")
    op.drop_index(op.f("ix_tenant_bot_credentials_key_hash"), table_name="tenant_bot_credentials")
    op.drop_table("tenant_bot_credentials")
