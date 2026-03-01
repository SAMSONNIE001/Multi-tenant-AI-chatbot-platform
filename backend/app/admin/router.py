import csv
import io
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.admin.rbac import require_scope
from app.admin.schemas import (
    AuditListResponse,
    ConversationMessagesResponse,
    ConversationsListResponse,
    DocumentAdminOut,
    DocumentDeleteResponse,
    DocumentPatchRequest,
    DocumentsListResponse,
    PolicyGeneratedResponse,
    PolicyPutRequest,
    PolicyResponse,
    OpsAuditListResponse,
    OpsAuditLogCreateRequest,
    OpsAuditLogEntryOut,
    RetentionConfig,
    RetentionResponse,
    UsageLimitConfig,
    UsageLimitResponse,
    UsageSummaryResponse,
)
from app.auth.deps import get_current_user
from app.auth.models import User
from app.audit.models import ChatAuditLog
from app.audit.models import OpsAuditLog
from app.chat.memory_models import Conversation, Message
from app.db.session import get_db
from app.governance.extract_policy import extract_policy_from_text
from app.governance.models import TenantPolicy
from app.rag.models import Chunk, Document
from app.system.usage_service import get_or_create_tenant_limit, usage_summary

router = APIRouter()


def _to_ops_audit_out(row: OpsAuditLog) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "actor_user_id": row.actor_user_id,
        "action_type": row.action_type,
        "reason": row.reason,
        "metadata_json": row.metadata_json or {},
        "created_at": row.created_at,
    }


@router.get("/documents", response_model=DocumentsListResponse)
def list_documents(
    q: str | None = Query(default=None, min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "docs:read")

    stmt = select(Document).where(Document.tenant_id == current_user.tenant_id)

    if q:
        stmt = stmt.where(Document.filename.ilike(f"%{q}%"))

    docs = db.execute(
        stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)
    ).scalars().all()

    doc_ids = [d.id for d in docs]

    chunk_counts: dict[str, int] = {}
    if doc_ids:
        chunk_counts = dict(
            db.execute(
                select(Chunk.document_id, func.count(Chunk.id))
                .where(
                    Chunk.tenant_id == current_user.tenant_id,
                    Chunk.document_id.in_(doc_ids),
                )
                .group_by(Chunk.document_id)
            ).all()
        )

    return {
        "tenant_id": current_user.tenant_id,
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "visibility": d.visibility,
                "tags": d.tags or [],
                "created_at": d.created_at,
                "chunk_count": int(chunk_counts.get(d.id, 0)),
            }
            for d in docs
        ],
    }


@router.patch("/documents/{document_id}", response_model=DocumentAdminOut)
def update_document(
    document_id: str,
    payload: DocumentPatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "docs:write")

    doc = db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found for tenant")

    if payload.visibility is None and payload.tags is None:
        raise HTTPException(status_code=422, detail="Provide at least one field: visibility or tags")

    if payload.visibility is not None:
        doc.visibility = payload.visibility
    if payload.tags is not None:
        doc.tags = payload.tags

    db.add(doc)
    db.commit()
    db.refresh(doc)

    chunk_count = db.execute(
        select(func.count(Chunk.id)).where(
            Chunk.document_id == doc.id,
            Chunk.tenant_id == current_user.tenant_id,
        )
    ).scalar_one()

    return {
        "id": doc.id,
        "filename": doc.filename,
        "visibility": doc.visibility,
        "tags": doc.tags or [],
        "created_at": doc.created_at,
        "chunk_count": int(chunk_count or 0),
    }


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "docs:delete")

    doc = db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found for tenant")

    db.execute(
        delete(Chunk).where(
            Chunk.document_id == document_id,
            Chunk.tenant_id == current_user.tenant_id,
        )
    )
    db.delete(doc)
    db.commit()

    return {"deleted": True, "document_id": document_id}


@router.get("/policy", response_model=PolicyResponse)
def get_policy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "policy:read")

    row = db.execute(
        select(TenantPolicy).where(TenantPolicy.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()

    return {
        "tenant_id": current_user.tenant_id,
        "policy": row.policy_json if row else {"refusal_message": "", "rules": []},
    }


@router.put("/policy", response_model=PolicyResponse)
def put_policy(
    payload: PolicyPutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "policy:write")

    existing = db.execute(
        select(TenantPolicy).where(TenantPolicy.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()
    if existing:
        existing.policy_json = payload.policy
        db.add(existing)
    else:
        db.add(TenantPolicy(tenant_id=current_user.tenant_id, policy_json=payload.policy))
    db.commit()

    return {"tenant_id": current_user.tenant_id, "policy": payload.policy}


@router.post("/policy/generate-from-document/{document_id}", response_model=PolicyGeneratedResponse)
def generate_policy_from_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "policy:write")

    doc = db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found for tenant")

    chunks = (
        db.execute(
            select(Chunk)
            .where(
                Chunk.document_id == document_id,
                Chunk.tenant_id == current_user.tenant_id,
            )
            .order_by(Chunk.chunk_index.asc())
        )
        .scalars()
        .all()
    )

    full_text = "\n".join(c.text for c in chunks)
    if not full_text.strip():
        raise HTTPException(status_code=400, detail="Document has no chunk text to extract policy from")

    policy_json = extract_policy_from_text(full_text)

    existing = db.execute(
        select(TenantPolicy).where(TenantPolicy.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()
    if existing:
        existing.policy_json = policy_json
        db.add(existing)
    else:
        db.add(TenantPolicy(tenant_id=current_user.tenant_id, policy_json=policy_json))
    db.commit()

    return {"tenant_id": current_user.tenant_id, "document_id": document_id, "policy": policy_json}


@router.get("/retention", response_model=RetentionResponse)
def get_retention(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "policy:read")

    row = db.execute(
        select(TenantPolicy).where(TenantPolicy.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()

    policy = row.policy_json if row and row.policy_json else {}
    retention = policy.get("retention") or {}
    return {
        "tenant_id": current_user.tenant_id,
        "retention": {
            "audit_days": int(retention.get("audit_days", 90)),
            "messages_days": int(retention.get("messages_days", 30)),
        },
    }


@router.put("/retention", response_model=RetentionResponse)
def put_retention(
    payload: RetentionConfig,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "policy:write")

    row = db.execute(
        select(TenantPolicy).where(TenantPolicy.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()

    policy = row.policy_json if row and row.policy_json else {"refusal_message": "", "rules": []}
    policy["retention"] = {
        "audit_days": int(payload.audit_days),
        "messages_days": int(payload.messages_days),
    }

    if row:
        row.policy_json = policy
        db.add(row)
    else:
        db.add(TenantPolicy(tenant_id=current_user.tenant_id, policy_json=policy))

    db.commit()

    return {"tenant_id": current_user.tenant_id, "retention": policy["retention"]}


@router.post("/retention/purge")
def purge_retention(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "policy:write")

    row = db.execute(
        select(TenantPolicy).where(TenantPolicy.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()
    policy = row.policy_json if row and row.policy_json else {}
    retention = policy.get("retention") or {}

    audit_days = int(retention.get("audit_days", 90))
    messages_days = int(retention.get("messages_days", 30))

    audit_cutoff = datetime.utcnow() - timedelta(days=audit_days)
    msg_cutoff = datetime.utcnow() - timedelta(days=messages_days)

    audit_deleted = db.execute(
        delete(ChatAuditLog).where(
            ChatAuditLog.tenant_id == current_user.tenant_id,
            ChatAuditLog.created_at < audit_cutoff,
        )
    ).rowcount or 0

    conv_ids = db.execute(
        select(Conversation.id).where(Conversation.tenant_id == current_user.tenant_id)
    ).scalars().all()

    msg_deleted = 0
    if conv_ids:
        msg_deleted = db.execute(
            delete(Message).where(
                Message.conversation_id.in_(conv_ids),
                Message.created_at < msg_cutoff,
            )
        ).rowcount or 0

    db.commit()

    return {
        "tenant_id": current_user.tenant_id,
        "audit_deleted": int(audit_deleted),
        "messages_deleted": int(msg_deleted),
        "audit_cutoff": audit_cutoff.isoformat(),
        "messages_cutoff": msg_cutoff.isoformat(),
    }


@router.get("/conversations", response_model=ConversationsListResponse)
def list_conversations(
    user_id: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "conversations:read")

    stmt = select(Conversation).where(Conversation.tenant_id == current_user.tenant_id)

    if user_id:
        stmt = stmt.where(Conversation.user_id == user_id)

    convs = db.execute(
        stmt.order_by(Conversation.last_activity_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    conv_ids = [c.id for c in convs]

    msg_counts: dict[str, int] = {}
    if conv_ids:
        msg_counts = dict(
            db.execute(
                select(Message.conversation_id, func.count(Message.id))
                .where(Message.conversation_id.in_(conv_ids))
                .group_by(Message.conversation_id)
            ).all()
        )

    return {
        "tenant_id": current_user.tenant_id,
        "conversations": [
            {
                "id": c.id,
                "user_id": c.user_id,
                "created_at": c.created_at,
                "last_activity_at": c.last_activity_at,
                "message_count": int(msg_counts.get(c.id, 0)),
            }
            for c in convs
        ],
    }


@router.get("/conversations/{conversation_id}/messages", response_model=ConversationMessagesResponse)
def list_conversation_messages(
    conversation_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "conversations:read")

    conv = db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found for tenant")

    msgs = (
        db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return {
        "tenant_id": current_user.tenant_id,
        "conversation_id": conv.id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in msgs
        ],
    }


@router.post("/ops/audit", response_model=OpsAuditLogEntryOut)
def create_ops_audit_log(
    payload: OpsAuditLogCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "audit:write")

    row = OpsAuditLog(
        id=f"opl_{secrets.token_hex(10)}",
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action_type=payload.action_type.strip().lower(),
        reason=payload.reason.strip(),
        metadata_json=payload.metadata_json or {},
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_ops_audit_out(row)


@router.get("/ops/audit", response_model=OpsAuditListResponse)
def list_ops_audit_logs(
    action_type: str | None = Query(default=None, min_length=3, max_length=64),
    since_hours: int = Query(default=168, ge=1, le=24 * 90),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "audit:read")

    since = datetime.utcnow() - timedelta(hours=since_hours)
    stmt = select(OpsAuditLog).where(
        OpsAuditLog.tenant_id == current_user.tenant_id,
        OpsAuditLog.created_at >= since,
    )
    if action_type:
        stmt = stmt.where(OpsAuditLog.action_type == action_type.strip().lower())

    rows = db.execute(
        stmt.order_by(desc(OpsAuditLog.created_at)).limit(limit).offset(offset)
    ).scalars().all()
    return {
        "tenant_id": current_user.tenant_id,
        "count": len(rows),
        "entries": [_to_ops_audit_out(r) for r in rows],
    }


@router.get("/audit", response_model=AuditListResponse)
def list_audit_logs(
    since_hours: int = Query(default=24, ge=1, le=720),
    refused_only: bool = Query(default=False),
    q: str | None = Query(default=None, min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "audit:read")

    since = datetime.utcnow() - timedelta(hours=since_hours)

    base_filter = [
        ChatAuditLog.tenant_id == current_user.tenant_id,
        ChatAuditLog.created_at >= since,
    ]
    if refused_only:
        base_filter.append(ChatAuditLog.refused == True)  # noqa: E712
    if q:
        base_filter.append(ChatAuditLog.question.ilike(f"%{q}%"))

    total = db.execute(
        select(func.count()).select_from(ChatAuditLog).where(*base_filter)
    ).scalar_one()

    refused = db.execute(
        select(func.count())
        .select_from(ChatAuditLog)
        .where(*base_filter, ChatAuditLog.refused == True)  # noqa: E712
    ).scalar_one()

    avg_latency = db.execute(
        select(func.avg(ChatAuditLog.latency_ms)).where(*base_filter)
    ).scalar_one()

    # Top refused reasons across the full window (not just current page)
    reason_rows = db.execute(
        select(ChatAuditLog.policy_reason, func.count(ChatAuditLog.id))
        .where(*base_filter, ChatAuditLog.policy_reason.isnot(None))
        .group_by(ChatAuditLog.policy_reason)
        .order_by(desc(func.count(ChatAuditLog.id)))
        .limit(10)
    ).all()

    top_refused_reasons = [
        {"reason": reason, "count": int(count)}
        for reason, count in reason_rows
    ]

    rows = db.execute(
        select(ChatAuditLog)
        .where(*base_filter)
        .order_by(desc(ChatAuditLog.created_at))
        .limit(limit)
        .offset(offset)
    ).scalars().all()

    return {
        "tenant_id": current_user.tenant_id,
        "window_hours": since_hours,
        "filters": {"refused_only": refused_only},
        "summary": {
            "total_requests": int(total or 0),
            "refused_requests": int(refused or 0),
            "refusal_rate": (float(refused) / float(total)) if total else 0.0,
            "avg_latency_ms": float(avg_latency) if avg_latency is not None else None,
            "top_refused_reasons": top_refused_reasons,
        },
        "entries": [
            {
                "id": r.id,
                "tenant_id": r.tenant_id,
                "user_id": r.user_id,
                "question": r.question,
                "answer": r.answer,
                "retrieved_chunks": r.retrieved_chunks,
                "citations": r.citations,
                "refused": r.refused,
                "model": r.model,
                "latency_ms": r.latency_ms,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "policy_reason": r.policy_reason,
                "retrieval_doc_count": r.retrieval_doc_count,
                "retrieval_chunk_count": r.retrieval_chunk_count,
                "created_at": r.created_at,
            }
            for r in rows
        ],
    }


@router.get("/audit/export.csv")
def export_audit_csv(
    since_hours: int = Query(default=24, ge=1, le=720),
    refused_only: bool = Query(default=False),
    q: str | None = Query(default=None, min_length=1, max_length=200),
    limit: int = Query(default=5000, ge=1, le=50000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "audit:read")

    since = datetime.utcnow() - timedelta(hours=since_hours)

    base_filter = [
        ChatAuditLog.tenant_id == current_user.tenant_id,
        ChatAuditLog.created_at >= since,
    ]
    if refused_only:
        base_filter.append(ChatAuditLog.refused == True)  # noqa: E712
    if q:
        base_filter.append(ChatAuditLog.question.ilike(f"%{q}%"))

    rows = db.execute(
        select(ChatAuditLog)
        .where(*base_filter)
        .order_by(desc(ChatAuditLog.created_at))
        .limit(limit)
    ).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(
        [
            "id",
            "tenant_id",
            "user_id",
            "created_at",
            "refused",
            "policy_reason",
            "latency_ms",
            "model",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "retrieval_doc_count",
            "retrieval_chunk_count",
            "question",
            "answer",
        ]
    )

    for r in rows:
        writer.writerow(
            [
                r.id,
                r.tenant_id,
                r.user_id,
                r.created_at.isoformat() if r.created_at else "",
                r.refused,
                r.policy_reason or "",
                r.latency_ms if r.latency_ms is not None else "",
                r.model or "",
                r.prompt_tokens if r.prompt_tokens is not None else "",
                r.completion_tokens if r.completion_tokens is not None else "",
                r.total_tokens if r.total_tokens is not None else "",
                r.retrieval_doc_count if r.retrieval_doc_count is not None else "",
                r.retrieval_chunk_count if r.retrieval_chunk_count is not None else "",
                (r.question or "").replace("\n", " ").strip(),
                (r.answer or "").replace("\n", " ").strip(),
            ]
        )

    buf.seek(0)
    filename = f"audit_{current_user.tenant_id}_{since_hours}h.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/usage/limits", response_model=UsageLimitResponse)
def get_usage_limits(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "policy:read")
    limits = get_or_create_tenant_limit(db, current_user.tenant_id)
    return {
        "tenant_id": current_user.tenant_id,
        "limits": {
            "daily_request_limit": int(limits.daily_request_limit),
            "monthly_token_limit": int(limits.monthly_token_limit),
        },
    }


@router.put("/usage/limits", response_model=UsageLimitResponse)
def put_usage_limits(
    payload: UsageLimitConfig,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "policy:write")
    limits = get_or_create_tenant_limit(db, current_user.tenant_id)
    limits.daily_request_limit = int(payload.daily_request_limit)
    limits.monthly_token_limit = int(payload.monthly_token_limit)
    limits.updated_at = datetime.utcnow()
    db.add(limits)
    db.commit()
    db.refresh(limits)
    return {
        "tenant_id": current_user.tenant_id,
        "limits": {
            "daily_request_limit": int(limits.daily_request_limit),
            "monthly_token_limit": int(limits.monthly_token_limit),
        },
    }


@router.get("/usage/summary", response_model=UsageSummaryResponse)
def get_usage_summary(
    since_days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "audit:read")
    summary = usage_summary(
        db=db,
        tenant_id=current_user.tenant_id,
        since_days=since_days,
    )
    return {
        "tenant_id": current_user.tenant_id,
        "summary": summary,
    }
