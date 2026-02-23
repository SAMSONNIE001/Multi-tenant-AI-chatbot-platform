from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.models import User
from app.auth.rbac import require_roles
from app.db.session import get_db
from app.rag.schemas import DocumentOut, QueryRequest, QueryResponse, QueryResultChunk
from app.rag.service import ingest_text_document, search_chunks

router = APIRouter()


@router.post("/upload", response_model=DocumentOut)
async def upload_rag_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("editor", "admin", "owner")),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    # MVP: allow only text-based files
    allowed = {"text/plain", "text/markdown", "application/json"}
    content_type = file.content_type or "text/plain"
    if content_type not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. Use txt/markdown/json for now.",
        )

    raw = await file.read()
    if len(raw) > 2_000_000:  # 2MB MVP limit
        raise HTTPException(status_code=413, detail="File too large (max 2MB for now).")

    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decode file as UTF-8 text.")

    doc = ingest_text_document(
        db=db,
        tenant_id=current_user.tenant_id,
        filename=file.filename,
        content_type=content_type,
        text=text,
    )
    return doc


@router.post("/query", response_model=QueryResponse)
def query_rag(
    payload: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chunks = search_chunks(
        db=db,
        tenant_id=current_user.tenant_id,
        question=payload.question,
        top_k=payload.top_k,
    )

    return QueryResponse(
        tenant_id=current_user.tenant_id,
        question=payload.question,
        results=[
            QueryResultChunk(
                document_id=c.document_id,
                chunk_index=c.chunk_index,
                text=c.text,
            )
            for c in chunks
        ],
    )
