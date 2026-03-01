"""add customer identity linking tables

Revision ID: d2f6c1ab4e90
Revises: aa7d2f3c19b4
Create Date: 2026-03-01 18:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2f6c1ab4e90"
down_revision: Union[str, Sequence[str], None] = "aa7d2f3c19b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_profiles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_customer_profiles_tenant_id"), "customer_profiles", ["tenant_id"], unique=False)

    op.create_table(
        "customer_channel_handles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("customer_profile_id", sa.String(length=64), nullable=False),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column("external_user_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["customer_profile_id"], ["customer_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "channel_type",
            "external_user_id",
            name="uq_customer_channel_handles_tenant_channel_external",
        ),
    )
    op.create_index(
        op.f("ix_customer_channel_handles_tenant_id"),
        "customer_channel_handles",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_channel_handles_customer_profile_id"),
        "customer_channel_handles",
        ["customer_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_channel_handles_channel_type"),
        "customer_channel_handles",
        ["channel_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_customer_channel_handles_channel_type"), table_name="customer_channel_handles")
    op.drop_index(op.f("ix_customer_channel_handles_customer_profile_id"), table_name="customer_channel_handles")
    op.drop_index(op.f("ix_customer_channel_handles_tenant_id"), table_name="customer_channel_handles")
    op.drop_table("customer_channel_handles")

    op.drop_index(op.f("ix_customer_profiles_tenant_id"), table_name="customer_profiles")
    op.drop_table("customer_profiles")
