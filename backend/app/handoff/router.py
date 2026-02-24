from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.admin.rbac import require_scope
from app.auth.deps import get_current_user
from app.auth.models import User
from app.db.session import get_db
from app.handoff.models import HandoffRequest
from app.handoff.schemas import (
    HandoffCreateRequest,
    HandoffListResponse,
    HandoffOut,
    HandoffPatchRequest,
)
from app.handoff.service import create_handoff_request

router = APIRouter()
admin_router = APIRouter()


def _to_out(row: HandoffRequest) -> HandoffOut:
    return HandoffOut(
        id=row.id,
        tenant_id=row.tenant_id,
        conversation_id=row.conversation_id,
        user_id=row.user_id,
        source_channel=row.source_channel,
        question=row.question,
        reason=row.reason,
        status=row.status,
        destination=row.destination,
        resolution_note=row.resolution_note,
        created_at=row.created_at,
        updated_at=row.updated_at,
        resolved_at=row.resolved_at,
    )


@router.post("/request", response_model=HandoffOut)
def request_handoff(
    payload: HandoffCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source_channel = "embed" if str(current_user.id).startswith("w_") else "api"
    row = create_handoff_request(
        db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        question=payload.question,
        conversation_id=payload.conversation_id,
        reason=payload.reason,
        destination=payload.destination,
        source_channel=source_channel,
    )
    return _to_out(row)


@admin_router.get("", response_model=HandoffListResponse)
def list_handoffs(
    status: str | None = Query(default=None, min_length=2, max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "handoff:read")

    stmt = select(HandoffRequest).where(HandoffRequest.tenant_id == current_user.tenant_id)
    if status:
        stmt = stmt.where(HandoffRequest.status == status)

    rows = db.execute(
        stmt.order_by(desc(HandoffRequest.created_at)).limit(limit).offset(offset)
    ).scalars().all()

    return {
        "tenant_id": current_user.tenant_id,
        "count": len(rows),
        "items": [_to_out(r) for r in rows],
    }


@admin_router.patch("/{handoff_id}", response_model=HandoffOut)
def patch_handoff(
    handoff_id: str,
    payload: HandoffPatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "handoff:write")

    row = db.execute(
        select(HandoffRequest).where(
            HandoffRequest.id == handoff_id,
            HandoffRequest.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Handoff not found")

    next_status = payload.status.strip().lower()
    allowed = {"open", "in_progress", "resolved", "closed"}
    if next_status not in allowed:
        raise HTTPException(status_code=422, detail=f"Invalid status. Allowed: {sorted(allowed)}")

    row.status = next_status
    row.updated_at = datetime.utcnow()
    if payload.resolution_note is not None:
        row.resolution_note = payload.resolution_note

    if next_status in {"resolved", "closed"}:
        row.resolved_at = datetime.utcnow()
    else:
        row.resolved_at = None

    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)
