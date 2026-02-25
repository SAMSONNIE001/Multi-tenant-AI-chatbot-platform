from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TenantChannelAccount(Base):
    __tablename__ = "tenant_channel_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # whatsapp | messenger | instagram | facebook
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    verify_token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    app_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # channel-specific routing identifiers
    phone_number_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    page_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    instagram_account_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
