from datetime import datetime

from sqlalchemy import DateTime, String, Text, Boolean, JSON, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatAuditLog(Base):
    __tablename__ = "chat_audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. al_abc123
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    retrieved_chunks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    citations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    refused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    policy_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    retrieval_doc_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieval_chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


Index("ix_chat_audit_tenant_created_at", ChatAuditLog.tenant_id, ChatAuditLog.created_at)


class OpsAuditLog(Base):
    __tablename__ = "ops_audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. opl_abc123
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


Index("ix_ops_audit_tenant_created_at", OpsAuditLog.tenant_id, OpsAuditLog.created_at)
