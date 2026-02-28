from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, or_, select
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
        assigned_to_user_id=row.assigned_to_user_id,
        priority=row.priority,
        destination=row.destination,
        resolution_note=row.resolution_note,
        first_response_due_at=row.first_response_due_at,
        first_responded_at=row.first_responded_at,
        resolution_due_at=row.resolution_due_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        resolved_at=row.resolved_at,
        closed_at=row.closed_at,
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
    assigned_to: str | None = Query(default=None, min_length=3, max_length=64),
    priority: str | None = Query(default=None, min_length=2, max_length=16),
    breached_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "handoff:read")

    stmt = select(HandoffRequest).where(HandoffRequest.tenant_id == current_user.tenant_id)
    if status:
        stmt = stmt.where(HandoffRequest.status == status)
    if assigned_to:
        stmt = stmt.where(HandoffRequest.assigned_to_user_id == assigned_to)
    if priority:
        stmt = stmt.where(HandoffRequest.priority == priority)
    if breached_only:
        now = datetime.utcnow()
        first_response_breach = and_(
            HandoffRequest.first_response_due_at.is_not(None),
            HandoffRequest.first_response_due_at < now,
            HandoffRequest.first_responded_at.is_(None),
            HandoffRequest.status.in_(["new", "open"]),
        )
        resolution_breach = and_(
            HandoffRequest.resolution_due_at.is_not(None),
            HandoffRequest.resolution_due_at < now,
            HandoffRequest.status.in_(["open", "pending_customer"]),
        )
        stmt = stmt.where(or_(first_response_breach, resolution_breach))

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

    now = datetime.utcnow()
    allowed_status = {"new", "open", "pending_customer", "resolved", "closed"}
    allowed_priority = {"low", "normal", "high", "urgent"}

    if payload.status is not None:
        next_status = payload.status.strip().lower()
        if next_status not in allowed_status:
            raise HTTPException(status_code=422, detail=f"Invalid status. Allowed: {sorted(allowed_status)}")
        row.status = next_status

        if next_status in {"open", "pending_customer"} and row.first_responded_at is None:
            row.first_responded_at = now
        if next_status in {"resolved", "closed"}:
            row.resolved_at = now
        else:
            row.resolved_at = None
        if next_status == "closed":
            row.closed_at = now
        elif next_status != "closed":
            row.closed_at = None

    if payload.assigned_to_user_id is not None:
        row.assigned_to_user_id = payload.assigned_to_user_id.strip() or None

    if payload.priority is not None:
        priority = payload.priority.strip().lower()
        if priority not in allowed_priority:
            raise HTTPException(status_code=422, detail=f"Invalid priority. Allowed: {sorted(allowed_priority)}")
        row.priority = priority

    row.updated_at = datetime.utcnow()
    if payload.resolution_note is not None:
        row.resolution_note = payload.resolution_note

    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)
