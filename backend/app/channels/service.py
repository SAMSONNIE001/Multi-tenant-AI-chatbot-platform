import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime
from types import SimpleNamespace
from urllib import request

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.models import TenantChannelAccount
from app.chat.router import ask as ask_internal
from app.chat.schemas import AskRequest
from app.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_CHANNELS = {"whatsapp", "messenger", "instagram", "facebook"}


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
    pseudo_user = SimpleNamespace(
        id=_safe_user_id(channel_type, external_user_id),
        tenant_id=account.tenant_id,
    )
    answer = ask_internal(
        payload=AskRequest(question=question),
        db=db,
        current_user=pseudo_user,
    ).answer

    if channel_type == "whatsapp":
        send_whatsapp_text(account, to=external_user_id, text=answer)
    else:
        send_messenger_or_instagram_text(account, recipient_id=external_user_id, text=answer)

    account.last_used_at = datetime.utcnow()
    account.updated_at = datetime.utcnow()
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
