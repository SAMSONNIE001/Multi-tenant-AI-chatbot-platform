from datetime import datetime, timedelta
import os
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
from app.chat.llm import generate_answer
from app.handoff.models import HandoffInternalNote, HandoffRequest
from app.handoff.schemas import (
    HandoffAgentReplyRequest,
    HandoffDailyMetric,
    HandoffAgentMetric,
    HandoffAIToggleRequest,
    HandoffClaimRequest,
    HandoffCreateRequest,
    HandoffListResponse,
    HandoffMetricsResponse,
    HandoffNoteCreateRequest,
    HandoffNoteOut,
    HandoffNotesResponse,
    HandoffOut,
    HandoffPatchRequest,
    HandoffReplyReviewRequest,
    HandoffReplyReviewResponse,
    HandoffRiskFlag,
    HandoffTotalsMetric,
    HandoffWindowMetrics,
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


def _is_admin(user: User) -> bool:
    return (getattr(user, "role", "") or "").strip().lower() == "admin"


def _assert_handoff_operator(row: HandoffRequest, current_user: User) -> None:
    """
    Non-admin users can operate only unassigned handoffs or handoffs assigned to them.
    """
    assigned = (row.assigned_to_user_id or "").strip()
    if assigned and assigned != current_user.id and not _is_admin(current_user):
        raise HTTPException(status_code=409, detail=f"Handoff is assigned to {assigned}")


def _is_sla_breached(row: HandoffRequest, now: datetime) -> bool:
    first_response_breach = bool(
        row.first_response_due_at
        and row.first_response_due_at < now
        and row.first_responded_at is None
        and row.status in {"new", "open"}
    )
    resolution_breach = bool(
        row.resolution_due_at
        and row.resolution_due_at < now
        and row.status in {"open", "pending_customer"}
    )
    return first_response_breach or resolution_breach


def _window_metrics(rows: list[HandoffRequest], now: datetime, hours: int) -> HandoffWindowMetrics:
    cutoff = now.timestamp() - (hours * 3600)
    in_window = [r for r in rows if r.created_at and r.created_at.timestamp() >= cutoff]
    total = len(in_window)
    breached = sum(1 for r in in_window if _is_sla_breached(r, now))

    first_response_mins = []
    resolution_mins = []
    for r in in_window:
        if r.first_responded_at and r.first_responded_at >= r.created_at:
            first_response_mins.append((r.first_responded_at - r.created_at).total_seconds() / 60.0)
        if r.resolved_at and r.resolved_at >= r.created_at:
            resolution_mins.append((r.resolved_at - r.created_at).total_seconds() / 60.0)

    avg_first = round(sum(first_response_mins) / len(first_response_mins), 2) if first_response_mins else None
    avg_resolution = round(sum(resolution_mins) / len(resolution_mins), 2) if resolution_mins else None
    breach_rate = round((breached / total), 4) if total else 0.0
    return HandoffWindowMetrics(
        window_hours=hours,
        total_tickets=total,
        breached_tickets=breached,
        breach_rate=breach_rate,
        avg_first_response_min=avg_first,
        avg_resolution_min=avg_resolution,
    )


def _daily_metrics(rows: list[HandoffRequest], now: datetime, days: int = 7) -> list[HandoffDailyMetric]:
    buckets: list[HandoffDailyMetric] = []
    start = now.date() - timedelta(days=days - 1)
    for i in range(days):
        day = start + timedelta(days=i)
        day_rows = [r for r in rows if r.created_at and r.created_at.date() == day]
        total = len(day_rows)
        breached = sum(1 for r in day_rows if _is_sla_breached(r, now))
        rate = round((breached / total), 4) if total else 0.0
        buckets.append(
            HandoffDailyMetric(
                day=day.isoformat(),
                tickets=total,
                breached_tickets=breached,
                breach_rate=rate,
            )
        )
    return buckets


def _review_risk_flags(text: str) -> list[HandoffRiskFlag]:
    s = (text or "").lower()
    flags: list[HandoffRiskFlag] = []
    if any(k in s for k in ["guarantee", "guaranteed", "always works", "never fail"]):
        flags.append(HandoffRiskFlag(code="overpromise", severity="high", message="Message may overpromise outcome."))
    if any(k in s for k in ["credit card", "cvv", "social security", "ssn", "otp", "one-time password", "bank pin"]):
        flags.append(HandoffRiskFlag(code="sensitive_data", severity="high", message="Avoid asking for highly sensitive data in chat."))
    if "legal advice" in s or "financial advice" in s:
        flags.append(HandoffRiskFlag(code="regulated_advice", severity="high", message="Regulated advice should be handled by specialist support."))
    if len(s.split()) < 4:
        flags.append(HandoffRiskFlag(code="too_short", severity="low", message="Reply may be too short to be actionable."))
    if "sorry" not in s and ("cannot" in s or "can't" in s or "unable" in s):
        flags.append(HandoffRiskFlag(code="tone", severity="low", message="Consider a more empathetic tone for refusal-style responses."))
    return flags


def _simple_rewrite(draft: str, mode: str) -> str:
    txt = draft.strip()
    if mode == "shorter":
        parts = txt.split(".")
        return parts[0].strip() + ("." if parts and parts[0].strip() else "")
    if mode == "friendlier":
        return f"Thanks for reaching out. {txt}"
    if mode == "formal":
        return f"Thank you for contacting support. {txt}"
    return txt


def _rewrite_with_llm(question: str, draft: str, mode: str) -> str:
    if mode == "none":
        return draft
    if not os.getenv("OPENAI_API_KEY"):
        return _simple_rewrite(draft, mode)
    system = (
        "You are a support quality reviewer. Rewrite the draft reply while preserving factual content. "
        "Do not invent account data. Keep it clear, safe, and professional. "
        "Avoid requesting sensitive data (passwords, CVV, SSN, OTP)."
    )
    style_hint = {
        "shorter": "Make it shorter and concise.",
        "friendlier": "Make it warm and empathetic while still professional.",
        "formal": "Make it formal and polished.",
    }.get(mode, "Keep style unchanged.")
    user = (
        f"Customer question:\n{question}\n\n"
        f"Draft reply:\n{draft}\n\n"
        f"Rewrite instruction: {style_hint}\n"
        "Return only the rewritten reply text."
    )
    rewritten, _, _, _ = generate_answer(system, user)
    rewritten = (rewritten or "").strip()
    if not rewritten:
        return _simple_rewrite(draft, mode)
    if "I couldn't find that in the available support information yet" in rewritten:
        return _simple_rewrite(draft, mode)
    return rewritten


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


@admin_router.get("/metrics", response_model=HandoffMetricsResponse)
def handoff_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "handoff:read")
    now = datetime.utcnow()

    rows = (
        db.execute(
            select(HandoffRequest)
            .where(HandoffRequest.tenant_id == current_user.tenant_id)
            .order_by(desc(HandoffRequest.created_at))
            .limit(5000)
        )
        .scalars()
        .all()
    )

    by_agent: dict[str, dict[str, int]] = {}
    for r in rows:
        agent = (r.assigned_to_user_id or "").strip()
        if not agent:
            continue
        if agent not in by_agent:
            by_agent[agent] = {"assigned_count": 0, "resolved_count": 0}
        by_agent[agent]["assigned_count"] += 1
        if r.status in {"resolved", "closed"} or r.resolved_at is not None:
            by_agent[agent]["resolved_count"] += 1

    per_agent = [
        HandoffAgentMetric(
            agent_user_id=agent,
            assigned_count=counts["assigned_count"],
            resolved_count=counts["resolved_count"],
        )
        for agent, counts in by_agent.items()
    ]
    per_agent.sort(key=lambda x: (x.assigned_count, x.resolved_count), reverse=True)

    all_tickets = len(rows)
    resolved_tickets = sum(1 for r in rows if r.status in {"resolved", "closed"} or r.resolved_at is not None)
    unresolved_tickets = max(0, all_tickets - resolved_tickets)
    resolved_rate = round((resolved_tickets / all_tickets), 4) if all_tickets else 0.0

    return HandoffMetricsResponse(
        tenant_id=current_user.tenant_id,
        as_of=now,
        window_24h=_window_metrics(rows, now, 24),
        window_7d=_window_metrics(rows, now, 24 * 7),
        by_agent=per_agent[:20],
        daily=_daily_metrics(rows, now, 7),
        totals=HandoffTotalsMetric(
            all_tickets=all_tickets,
            resolved_tickets=resolved_tickets,
            unresolved_tickets=unresolved_tickets,
            resolved_rate=resolved_rate,
        ),
    )


@admin_router.post("/reply-review", response_model=HandoffReplyReviewResponse)
def review_agent_reply(
    payload: HandoffReplyReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "handoff:write")

    row = db.execute(
        select(HandoffRequest).where(
            HandoffRequest.id == payload.handoff_id,
            HandoffRequest.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Handoff not found")

    improved = _rewrite_with_llm(row.question, payload.draft, payload.rewrite_mode)
    flags = _review_risk_flags(improved)
    requires_override = any(f.severity == "high" for f in flags)
    base_conf = 0.92
    penalty = sum(0.35 if f.severity == "high" else 0.12 if f.severity == "medium" else 0.04 for f in flags)
    confidence = max(0.05, round(base_conf - penalty, 2))

    return HandoffReplyReviewResponse(
        handoff_id=row.id,
        improved_draft=improved,
        confidence=confidence,
        requires_override=requires_override,
        risk_flags=flags,
    )


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

    _assert_handoff_operator(row, current_user)

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
        target = payload.assigned_to_user_id.strip() or None
        if target and target != current_user.id and not _is_admin(current_user):
            raise HTTPException(status_code=403, detail="Only admin can assign handoff to another user")
        row.assigned_to_user_id = target

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
    _assert_handoff_operator(row, current_user)

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

    if row.assigned_to_user_id and row.assigned_to_user_id != current_user.id and not _is_admin(current_user):
        raise HTTPException(status_code=409, detail=f"Handoff is assigned to {row.assigned_to_user_id}")

    requested_assignee = (payload.assigned_to_user_id or "").strip()
    if requested_assignee and requested_assignee != current_user.id and not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admin can assign handoff to another user")

    now = datetime.utcnow()
    row.assigned_to_user_id = requested_assignee or current_user.id
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
    _assert_handoff_operator(row, current_user)
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
    _assert_handoff_operator(row, current_user)
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
