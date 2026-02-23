from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.auth.deps import get_current_user
from app.auth.models import User

from app.rag.models import Document, Chunk
from app.governance.models import TenantPolicy
from app.governance.extract_policy import extract_policy_from_text

router = APIRouter()


@router.post("/generate-from-document/{document_id}")
def generate_policy_from_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Admin-only (you can relax later)
    if (current_user.role or "").lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    # Ensure document belongs to tenant
    doc = db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found for tenant")

    # Rebuild full text from chunks
    chunks = db.execute(
        select(Chunk)
        .where(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index.asc())
    ).scalars().all()

    full_text = "\n".join(c.text for c in chunks)
    if not full_text.strip():
        raise HTTPException(status_code=400, detail="Document has no chunk text to extract policy from")

    policy_json = extract_policy_from_text(full_text)

    # Upsert tenant policy
    existing = db.execute(
        select(TenantPolicy).where(TenantPolicy.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()

    if existing:
        existing.policy_json = policy_json
    else:
        db.add(TenantPolicy(tenant_id=current_user.tenant_id, policy_json=policy_json))

    db.commit()

    return {"tenant_id": current_user.tenant_id, "document_id": document_id, "policy": policy_json}