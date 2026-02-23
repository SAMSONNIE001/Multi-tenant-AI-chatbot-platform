import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.memory_models import Conversation, Message


def get_or_create_conversation(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    conversation_id: str | None,
) -> Conversation:
    # If client provided a conversation_id, ensure it belongs to same tenant+user
    if conversation_id:
        conv = db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
            )
        ).scalar_one_or_none()
        if conv:
            return conv

    # Create new conversation
    conv = Conversation(
        id=f"conv_{secrets.token_hex(10)}",
        tenant_id=tenant_id,
        user_id=user_id,
        created_at=datetime.utcnow(),
        last_activity_at=datetime.utcnow(),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def fetch_recent_messages(db: Session, *, conversation_id: str, limit: int) -> list[Message]:
    limit = max(0, min(int(limit or 0), 40))
    if limit == 0:
        return []

    rows = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    ).scalars().all()

    # reverse -> oldest to newest
    return list(reversed(rows))


def append_message(db: Session, *, conversation_id: str, role: str, content: str) -> None:
    msg = Message(
        id=f"msg_{secrets.token_hex(10)}",
        conversation_id=conversation_id,
        role=role,
        content=content,
        created_at=datetime.utcnow(),
    )
    db.add(msg)
    db.commit()


def touch_conversation(db: Session, *, conversation: Conversation) -> None:
    conversation.last_activity_at = datetime.utcnow()
    db.add(conversation)
    db.commit()