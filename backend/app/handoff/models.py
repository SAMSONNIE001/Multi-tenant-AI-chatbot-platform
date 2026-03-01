from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HandoffRequest(Base):
    __tablename__ = "handoff_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_channel: Mapped[str] = mapped_column(String(32), nullable=False, default="api")

    question: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    assigned_to_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    destination: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_response_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
