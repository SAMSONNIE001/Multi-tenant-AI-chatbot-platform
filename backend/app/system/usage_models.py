from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TenantUsageLimit(Base):
    __tablename__ = "tenant_usage_limits"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    daily_request_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    monthly_token_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1_000_000)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class TenantUsageEvent(Base):
    __tablename__ = "tenant_usage_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="api")
    refused: Mapped[bool] = mapped_column(nullable=False, default=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
