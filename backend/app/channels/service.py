import hashlib
import hmac
import json
import logging
import re
import secrets
from datetime import datetime
from types import SimpleNamespace
from urllib import request

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.models import TenantChannelAccount
from app.chat.router import ask as ask_internal
from app.chat.schemas import AskRequest
from app.handoff.service import create_handoff_request
from app.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_CHANNELS = {"whatsapp", "messenger", "instagram", "facebook"}
_SOCIAL_HANDOFF_INTENT_RE = re.compile(
    r"\b(human|agent|customer service|support person|real person|someone)\b",
    re.IGNORECASE,
)


def generate_verify_token() -> str:
    return secrets.token_urlsafe(24)


def normalize_channel_type(channel_type: str) -> str:
    value = (channel_type or "").strip().lower()
    if value not in SUPPORTED_CHANNELS:
        raise ValueError("Unsupported channel_type")
    return value


def _safe_user_id(prefix: str, external_user_id: str) -> str:
    digest = hashlib.sha256(f"{prefix}:{external_user_id}".encode("utf-8")).hexdigest()[:40]
    return f"c_{prefix}_{digest}"[:64]


def _graph_post(path: str, access_token: str, payload: dict) -> None:
    url = f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/{path}"
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=8):
            return
    except Exception:
        logger.exception("Failed to send channel response via Meta Graph API")
        raise


def _clean_social_answer(answer: str) -> str:
    text = " ".join((answer or "").split()).strip()
    # Hide internal citation/debug tags from social channels.
    text = re.sub(r"\s*\[[^\]]+:[^\]]+\]\s*", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def _split_message(text: str, limit: int) -> list[str]:
    s = (text or "").strip()
    if not s:
        return []
    if len(s) <= limit:
        return [s]

    out: list[str] = []
    buf = s
    while len(buf) > limit:
        cut = buf.rfind(" ", 0, limit)
        if cut < int(limit * 0.6):
            cut = limit
        part = buf[:cut].strip()
        if part:
            out.append(part)
        buf = buf[cut:].strip()
    if buf:
        out.append(buf)
    return out


def _format_for_channel(channel_type: str, answer: str) -> list[str]:
    cleaned = _clean_social_answer(answer)
    limit = 1500 if channel_type in {"messenger", "instagram", "facebook"} else 1200
    return _split_message(cleaned, limit)


def _social_handoff_intent(question: str) -> bool:
    q = (question or "").strip().lower()
    if not q:
        return False
    if "human resources" in q or "hr policy" in q:
        return False
    return bool(_SOCIAL_HANDOFF_INTENT_RE.search(q)) and any(
        k in q for k in ("speak", "talk", "connect", "agent", "support", "human")
    )


def send_whatsapp_text(account: TenantChannelAccount, *, to: str, text: str) -> None:
    if not account.phone_number_id:
        return
    _graph_post(
        f"{account.phone_number_id}/messages",
        account.access_token,
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text[:4096]},
        },
    )


def send_messenger_or_instagram_text(
    account: TenantChannelAccount,
    *,
    recipient_id: str,
    text: str,
) -> None:
    path = "me/messages"
    if account.channel_type == "instagram" and account.instagram_account_id:
        path = f"{account.instagram_account_id}/messages"

    _graph_post(
        path,
        account.access_token,
        {
            "recipient": {"id": recipient_id},
            "message": {"text": text[:2000]},
        },
    )


def _set_channel_error(account: TenantChannelAccount, message: str) -> None:
    account.last_error = message[:1000]
    account.last_error_at = datetime.utcnow()
    account.updated_at = datetime.utcnow()


def _clear_channel_error(account: TenantChannelAccount) -> None:
    account.last_error = None
    account.last_error_at = None


def _resolve_account_for_page_event(
    db: Session,
    *,
    channel_type: str,
    recipient_id: str,
) -> TenantChannelAccount | None:
    account = db.execute(
        select(TenantChannelAccount).where(
            TenantChannelAccount.channel_type == channel_type,
            TenantChannelAccount.page_id == recipient_id,
            TenantChannelAccount.is_active.is_(True),
        )
    ).scalar_one_or_none()

    if account:
        return account

    if channel_type == "messenger":
        return db.execute(
            select(TenantChannelAccount).where(
                TenantChannelAccount.channel_type == "facebook",
                TenantChannelAccount.page_id == recipient_id,
                TenantChannelAccount.is_active.is_(True),
            )
        ).scalar_one_or_none()

    return None


def verify_meta_signature(payload_bytes: bytes, header_value: str, secrets_list: list[str]) -> bool:
    if not header_value or not header_value.startswith("sha256="):
        return False

    sent_sig = header_value.split("=", 1)[1].strip()
    if not sent_sig:
        return False

    for secret in secrets_list:
        digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        if hmac.compare_digest(digest, sent_sig):
            return True
    return False


def _ask_and_reply(
    db: Session,
    *,
    account: TenantChannelAccount,
    external_user_id: str,
    question: str,
    channel_type: str,
) -> None:
    try:
        if _social_handoff_intent(question):
            handoff = create_handoff_request(
                db,
                tenant_id=account.tenant_id,
                user_id=_safe_user_id(channel_type, external_user_id),
                question=question,
                conversation_id=None,
                reason="human_requested",
                destination=None,
                source_channel=channel_type,
            )
            handoff_msg = (
                "I have connected you to our support team. "
                f"Please hold while an agent takes over. Ticket ID: {handoff.id}"
            )
            parts = _format_for_channel(channel_type, handoff_msg) or [handoff_msg]
            if channel_type == "whatsapp":
                for part in parts:
                    send_whatsapp_text(account, to=external_user_id, text=part)
            else:
                for part in parts:
                    send_messenger_or_instagram_text(account, recipient_id=external_user_id, text=part)
            now = datetime.utcnow()
            account.last_used_at = now
            account.last_outbound_at = now
            account.updated_at = now
            _clear_channel_error(account)
            db.add(account)
            return

        pseudo_user = SimpleNamespace(
            id=_safe_user_id(channel_type, external_user_id),
            tenant_id=account.tenant_id,
            source_channel=channel_type,
            tenant_name=account.name,
            bot_display_name=(account.name or "").strip() or "AI Assistant",
        )
        response = ask_internal(
            payload=AskRequest(question=question),
            db=db,
            current_user=pseudo_user,
        )
        answer = response.answer
        message_parts = _format_for_channel(channel_type, answer) or [answer]

        if channel_type == "whatsapp":
            for part in message_parts:
                send_whatsapp_text(account, to=external_user_id, text=part)
        else:
            for part in message_parts:
                send_messenger_or_instagram_text(account, recipient_id=external_user_id, text=part)

        now = datetime.utcnow()
        account.last_used_at = now
        account.last_outbound_at = now
        account.updated_at = now
        _clear_channel_error(account)
        db.add(account)
    except Exception as exc:
        _set_channel_error(account, str(exc))
        db.add(account)


def process_meta_webhook_payload(db: Session, payload: dict) -> tuple[int, int]:
    processed = 0
    ignored = 0

    obj = (payload.get("object") or "").strip().lower()

    if obj == "whatsapp_business_account":
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value") or {}
                phone_number_id = ((value.get("metadata") or {}).get("phone_number_id") or "").strip()
                if not phone_number_id:
                    ignored += 1
                    continue

                account = db.execute(
                    select(TenantChannelAccount).where(
                        TenantChannelAccount.channel_type == "whatsapp",
                        TenantChannelAccount.phone_number_id == phone_number_id,
                        TenantChannelAccount.is_active.is_(True),
                    )
                ).scalar_one_or_none()
                if not account:
                    ignored += 1
                    continue
                account.last_webhook_at = datetime.utcnow()
                account.updated_at = datetime.utcnow()
                db.add(account)

                for msg in value.get("messages", []):
                    if msg.get("type") != "text":
                        ignored += 1
                        continue

                    text = ((msg.get("text") or {}).get("body") or "").strip()
                    sender = (msg.get("from") or "").strip()
                    if not text or not sender:
                        ignored += 1
                        continue

                    _ask_and_reply(
                        db,
                        account=account,
                        external_user_id=sender,
                        question=text,
                        channel_type="whatsapp",
                    )
                    processed += 1

    elif obj in {"page", "instagram"}:
        for entry in payload.get("entry", []):
            for evt in entry.get("messaging", []):
                if (evt.get("message") or {}).get("is_echo"):
                    ignored += 1
                    continue

                text = ((evt.get("message") or {}).get("text") or "").strip()
                sender_id = ((evt.get("sender") or {}).get("id") or "").strip()
                recipient_id = ((evt.get("recipient") or {}).get("id") or "").strip()
                if not text or not sender_id or not recipient_id:
                    ignored += 1
                    continue

                channel_type = "instagram" if obj == "instagram" else "messenger"
                account = _resolve_account_for_page_event(
                    db,
                    channel_type=channel_type,
                    recipient_id=recipient_id,
                )

                if not account and channel_type == "instagram":
                    account = db.execute(
                        select(TenantChannelAccount).where(
                            TenantChannelAccount.channel_type == "instagram",
                            TenantChannelAccount.instagram_account_id == recipient_id,
                            TenantChannelAccount.is_active.is_(True),
                        )
                    ).scalar_one_or_none()

                if not account:
                    ignored += 1
                    continue
                account.last_webhook_at = datetime.utcnow()
                account.updated_at = datetime.utcnow()
                db.add(account)

                _ask_and_reply(
                    db,
                    account=account,
                    external_user_id=sender_id,
                    question=text,
                    channel_type=channel_type,
                )
                processed += 1

    else:
        ignored += 1

    db.commit()
    return processed, ignored
