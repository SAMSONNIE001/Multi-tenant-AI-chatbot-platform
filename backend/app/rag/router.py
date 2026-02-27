from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.models import User
from app.auth.rbac import require_roles
from app.db.session import get_db
from app.rag.file_extract import extract_text_from_upload
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

    raw = await file.read()
    if len(raw) > 10_000_000:
        raise HTTPException(status_code=413, detail="File too large (max 10MB).")
    try:
        content_type, text = extract_text_from_upload(
            filename=file.filename,
            content_type=file.content_type,
            raw=raw,
        )
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

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
