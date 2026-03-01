from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, asc, desc, or_, select
from sqlalchemy.orm import Session

from app.admin.rbac import require_scope
from app.auth.deps import get_current_user
from app.auth.models import User
from app.db.session import get_db
from app.chat.memory_models import Conversation
from app.chat.memory_service import append_message, touch_conversation
from app.handoff.models import HandoffInternalNote, HandoffRequest
from app.handoff.schemas import (
    HandoffAgentReplyRequest,
    HandoffAIToggleRequest,
    HandoffClaimRequest,
    HandoffCreateRequest,
    HandoffListResponse,
    HandoffNoteCreateRequest,
    HandoffNoteOut,
    HandoffNotesResponse,
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
        internal_notes=row.internal_notes,
        first_response_due_at=row.first_response_due_at,
        first_responded_at=row.first_responded_at,
        resolution_due_at=row.resolution_due_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        resolved_at=row.resolved_at,
        closed_at=row.closed_at,
)


def _append_internal_note(existing: str | None, note: str, author_id: str) -> str:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] ({author_id}) {note.strip()}"
    if not existing:
        return line
    return f"{existing.rstrip()}\n{line}"


def _to_note_out(row: HandoffInternalNote) -> HandoffNoteOut:
    return HandoffNoteOut(
        id=row.id,
        handoff_id=row.handoff_id,
        tenant_id=row.tenant_id,
        author_user_id=row.author_user_id,
        content=row.content,
        created_at=row.created_at,
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
    if payload.internal_note_append is not None:
        note_text = payload.internal_note_append.strip()
        row.internal_notes = _append_internal_note(
            row.internal_notes,
            note_text,
            current_user.id,
        )
        db.add(
            HandoffInternalNote(
                id=f"hon_{uuid4().hex[:16]}",
                handoff_id=row.id,
                tenant_id=row.tenant_id,
                author_user_id=current_user.id,
                content=note_text,
            )
        )

    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@admin_router.get("/{handoff_id}/notes", response_model=HandoffNotesResponse)
def list_handoff_notes(
    handoff_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "handoff:read")

    exists = db.execute(
        select(HandoffRequest.id).where(
            HandoffRequest.id == handoff_id,
            HandoffRequest.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=404, detail="Handoff not found")

    rows = (
        db.execute(
            select(HandoffInternalNote)
            .where(
                HandoffInternalNote.handoff_id == handoff_id,
                HandoffInternalNote.tenant_id == current_user.tenant_id,
            )
            .order_by(asc(HandoffInternalNote.created_at))
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return {
        "tenant_id": current_user.tenant_id,
        "handoff_id": handoff_id,
        "count": len(rows),
        "items": [_to_note_out(r) for r in rows],
    }


@admin_router.post("/{handoff_id}/notes", response_model=HandoffNoteOut)
def add_handoff_note(
    handoff_id: str,
    payload: HandoffNoteCreateRequest,
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

    text = payload.content.strip()
    note = HandoffInternalNote(
        id=f"hon_{uuid4().hex[:16]}",
        handoff_id=row.id,
        tenant_id=row.tenant_id,
        author_user_id=current_user.id,
        content=text,
    )
    row.internal_notes = _append_internal_note(row.internal_notes, text, current_user.id)
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.add(note)
    db.commit()
    db.refresh(note)
    return _to_note_out(note)


@admin_router.post("/{handoff_id}/claim", response_model=HandoffOut)
def claim_handoff(
    handoff_id: str,
    payload: HandoffClaimRequest,
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
    row.assigned_to_user_id = payload.assigned_to_user_id or current_user.id
    if row.status == "new":
        row.status = "open"
    if row.first_responded_at is None:
        row.first_responded_at = now
    row.updated_at = now

    if row.conversation_id:
        conv = db.execute(
            select(Conversation).where(
                Conversation.id == row.conversation_id,
                Conversation.tenant_id == current_user.tenant_id,
            )
        ).scalar_one_or_none()
        if conv:
            conv.ai_paused = True
            conv.ai_paused_at = now
            conv.ai_paused_by_user_id = current_user.id
            db.add(conv)

    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@admin_router.post("/{handoff_id}/reply", response_model=HandoffOut)
def handoff_agent_reply(
    handoff_id: str,
    payload: HandoffAgentReplyRequest,
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
    if not row.conversation_id:
        raise HTTPException(status_code=422, detail="Handoff has no conversation_id")

    conv = db.execute(
        select(Conversation).where(
            Conversation.id == row.conversation_id,
            Conversation.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    now = datetime.utcnow()
    append_message(
        db,
        conversation_id=conv.id,
        role="agent",
        content=payload.message.strip(),
    )
    touch_conversation(db, conversation=conv)

    row.assigned_to_user_id = row.assigned_to_user_id or current_user.id
    row.status = "pending_customer" if payload.mark_pending_customer else "open"
    row.first_responded_at = row.first_responded_at or now
    row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@admin_router.post("/{handoff_id}/ai-toggle", response_model=HandoffOut)
def handoff_ai_toggle(
    handoff_id: str,
    payload: HandoffAIToggleRequest,
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
    if not row.conversation_id:
        raise HTTPException(status_code=422, detail="Handoff has no conversation_id")

    conv = db.execute(
        select(Conversation).where(
            Conversation.id == row.conversation_id,
            Conversation.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    now = datetime.utcnow()
    conv.ai_paused = bool(payload.ai_paused)
    conv.ai_paused_at = now if conv.ai_paused else None
    conv.ai_paused_by_user_id = current_user.id if conv.ai_paused else None
    db.add(conv)

    row.status = "open" if conv.ai_paused else "pending_customer"
    row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)
