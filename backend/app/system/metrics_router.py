from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from datetime import datetime, timedelta

from app.db.session import get_db
from app.auth.deps import get_current_user
from app.auth.models import User
from app.audit.models import ChatAuditLog

router = APIRouter()

@router.get("/metrics")
def metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if (current_user.role or "").lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    since = datetime.utcnow() - timedelta(hours=24)

    total = db.execute(
        select(func.count()).select_from(ChatAuditLog).where(ChatAuditLog.created_at >= since)
    ).scalar_one()

    refused = db.execute(
        select(func.count())
        .select_from(ChatAuditLog)
        .where(ChatAuditLog.created_at >= since, ChatAuditLog.refused == True)  # noqa: E712
    ).scalar_one()

    avg_latency = db.execute(
        select(func.avg(ChatAuditLog.latency_ms)).where(ChatAuditLog.created_at >= since)
    ).scalar_one()

    return {
        "window_hours": 24,
        "total_requests": int(total or 0),
        "refused_requests": int(refused or 0),
        "refusal_rate": (float(refused) / float(total)) if total else 0.0,
        "avg_latency_ms": float(avg_latency) if avg_latency is not None else None,
    }
