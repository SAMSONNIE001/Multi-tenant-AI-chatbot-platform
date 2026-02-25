"""add tenant channel accounts

Revision ID: 8e9c2a1f5b7d
Revises: 2c7d4a8b9f10
Create Date: 2026-02-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8e9c2a1f5b7d"
down_revision: Union[str, Sequence[str], None] = "2c7d4a8b9f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_channel_accounts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("verify_token", sa.String(length=255), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("app_secret", sa.String(length=255), nullable=True),
        sa.Column("phone_number_id", sa.String(length=128), nullable=True),
        sa.Column("page_id", sa.String(length=128), nullable=True),
        sa.Column("instagram_account_id", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenant_channel_accounts_tenant_id"), "tenant_channel_accounts", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_tenant_channel_accounts_channel_type"), "tenant_channel_accounts", ["channel_type"], unique=False)
    op.create_index(op.f("ix_tenant_channel_accounts_verify_token"), "tenant_channel_accounts", ["verify_token"], unique=True)
    op.create_index(op.f("ix_tenant_channel_accounts_phone_number_id"), "tenant_channel_accounts", ["phone_number_id"], unique=False)
    op.create_index(op.f("ix_tenant_channel_accounts_page_id"), "tenant_channel_accounts", ["page_id"], unique=False)
    op.create_index(op.f("ix_tenant_channel_accounts_instagram_account_id"), "tenant_channel_accounts", ["instagram_account_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tenant_channel_accounts_instagram_account_id"), table_name="tenant_channel_accounts")
    op.drop_index(op.f("ix_tenant_channel_accounts_page_id"), table_name="tenant_channel_accounts")
    op.drop_index(op.f("ix_tenant_channel_accounts_phone_number_id"), table_name="tenant_channel_accounts")
    op.drop_index(op.f("ix_tenant_channel_accounts_verify_token"), table_name="tenant_channel_accounts")
    op.drop_index(op.f("ix_tenant_channel_accounts_channel_type"), table_name="tenant_channel_accounts")
    op.drop_index(op.f("ix_tenant_channel_accounts_tenant_id"), table_name="tenant_channel_accounts")
    op.drop_table("tenant_channel_accounts")
