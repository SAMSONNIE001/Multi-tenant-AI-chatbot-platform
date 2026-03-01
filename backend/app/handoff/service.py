import json
import secrets
from datetime import datetime, timedelta
from urllib import request

from sqlalchemy.orm import Session

from app.core.config import settings
from app.handoff.models import HandoffRequest


def _emit_handoff_webhook(payload: dict) -> None:
    if not settings.HANDOFF_WEBHOOK_URL:
        return

    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        settings.HANDOFF_WEBHOOK_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=3):
            pass
    except Exception:
        # non-blocking best-effort hook
        return


def create_handoff_request(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    question: str,
    conversation_id: str | None,
    reason: str | None,
    destination: str | None,
    source_channel: str = "api",
) -> HandoffRequest:
    now = datetime.utcnow()
    row = HandoffRequest(
        id=f"ho_{secrets.token_hex(12)}",
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        user_id=user_id,
        source_channel=source_channel,
        question=question,
        reason=reason,
        status="new",
        priority="normal",
        destination=destination,
        first_response_due_at=now + timedelta(minutes=15),
        resolution_due_at=now + timedelta(hours=24),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    _emit_handoff_webhook(
        {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "conversation_id": row.conversation_id,
            "user_id": row.user_id,
            "source_channel": row.source_channel,
            "question": row.question,
            "reason": row.reason,
            "status": row.status,
            "destination": row.destination,
            "created_at": row.created_at.isoformat(),
        }
    )

    return row
