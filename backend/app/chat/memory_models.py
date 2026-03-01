from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # conv_xxx
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ai_paused: Mapped[bool] = mapped_column(default=False, nullable=False)
    ai_paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ai_paused_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # msg_xxx
    conversation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


Index("ix_messages_conv_created", Message.conversation_id, Message.created_at)
Index("ix_conversations_tenant_user", Conversation.tenant_id, Conversation.user_id)
