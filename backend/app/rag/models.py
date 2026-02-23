from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. d_abc123
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="text/plain"
    )

    # --- 8.2.3 Document-based governance metadata ---
    # Who can use this document
    # "public" | "internal_only"
    visibility: Mapped[str] = mapped_column(
        String(32), nullable=False, default="public"
    )

    # Arbitrary access tags (e.g. ["hr_only"], ["finance_only"])
    tags: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. c_xyz789
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("documents.id"),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # OpenAI text-embedding-3-small produces 1536-dim vectors
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True
    )