import os
import re
import uuid
from typing import List

from sqlalchemy.orm import Session

from app.rag.models import Document, Chunk
from app.rag.embeddings import embed_text


def _make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def chunk_text(text: str, max_chars: int = 1000, overlap: int = 200) -> List[str]:
    """
    Simple chunker: normalizes whitespace, then chunks by size with overlap.
    Works well enough for MVP.
    """
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []

    chunks: List[str] = []
    start = 0
    n = len(cleaned)

    while start < n:
        end = min(start + max_chars, n)
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)

        if end == n:
            break
        start = max(0, end - overlap)

    return chunks


def ingest_text_document(
    db: Session,
    tenant_id: str,
    filename: str,
    content_type: str,
    text: str,
) -> Document:
    """
    Stores the document + chunks for a tenant.
    Also generates embeddings for each chunk (OpenAI) and stores them in Postgres (pgvector).
    """
    doc = Document(
        id=_make_id("d"),
        tenant_id=tenant_id,
        filename=filename,
        content_type=content_type or "text/plain",
    )
    db.add(doc)
    db.flush()  # ensure doc exists before chunks

    pieces = chunk_text(text)

    # If OPENAI_API_KEY isn't set, we still ingest text but embeddings will be None.
    openai_enabled = bool(os.getenv("OPENAI_API_KEY"))
    embedding_failed = False

    for i, piece in enumerate(pieces):
        vec = None
        if openai_enabled and not embedding_failed:
            # Generate embedding per chunk. If OpenAI fails (quota/auth/network),
            # continue ingestion with keyword-only fallback.
            try:
                vec = embed_text(piece)
            except Exception:
                embedding_failed = True

        db.add(
            Chunk(
                id=_make_id("c"),
                tenant_id=tenant_id,
                document_id=doc.id,
                chunk_index=i,
                text=piece,
                embedding=vec,
            )
        )

    db.commit()
    db.refresh(doc)
    return doc


def _keyword_search_chunks(
    db: Session,
    tenant_id: str,
    question: str,
    top_k: int,
) -> list[Chunk]:
    """
    Fallback keyword search (ILIKE), used if embeddings aren't available.
    """
    q = question.strip()
    if not q:
        return []

    keywords = [k for k in re.split(r"\W+", q) if len(k) >= 3]
    if not keywords:
        keywords = [q]

    query = db.query(Chunk).filter(Chunk.tenant_id == tenant_id)

    from sqlalchemy import or_

    conditions = [Chunk.text.ilike(f"%{kw}%") for kw in keywords[:8]]
    query = query.filter(or_(*conditions)).order_by(Chunk.document_id, Chunk.chunk_index)

    return query.limit(top_k).all()


def search_chunks(
    db: Session,
    tenant_id: str,
    question: str,
    top_k: int = 5,
) -> list[Chunk]:
    """
    Semantic retrieval (pgvector cosine distance) using OpenAI embeddings.
    Falls back to keyword search if embeddings cannot be used.
    """
    q = question.strip()
    if not q:
        return []

    # If OpenAI isn't configured, fall back.
    if not os.getenv("OPENAI_API_KEY"):
        return _keyword_search_chunks(db, tenant_id, q, top_k)

    # Compute embedding for the query
    try:
        qvec = embed_text(q)
    except Exception:
        # If OpenAI errors (network, auth, etc), fall back.
        return _keyword_search_chunks(db, tenant_id, q, top_k)

    # Vector search: only chunks with embeddings
    return (
        db.query(Chunk)
        .filter(Chunk.tenant_id == tenant_id, Chunk.embedding.isnot(None))
        .order_by(Chunk.embedding.cosine_distance(qvec))
        .limit(top_k)
        .all()
    )
