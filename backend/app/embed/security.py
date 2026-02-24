import secrets
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings

JWT_ALG = "HS256"
WIDGET_EXP_MINUTES = settings.WIDGET_TOKEN_EXP_MINUTES


class WidgetTokenValidationError(ValueError):
    pass


def hash_bot_key(raw_key: str) -> str:
    return sha256(raw_key.encode("utf-8")).hexdigest()


def generate_bot_key() -> str:
    return f"bot_{secrets.token_urlsafe(32)}"


def create_widget_token(*, tenant_id: str, bot_id: str, session_id: str, origin: str) -> tuple[str, int]:
    exp_minutes = max(1, int(WIDGET_EXP_MINUTES))
    expires_at = datetime.utcnow() + timedelta(minutes=exp_minutes)
    payload = {
        "typ": "widget",
        "tenant_id": tenant_id,
        "bot_id": bot_id,
        "session_id": session_id,
        "origin": origin,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.JWT_SECRET or "dev-change-me", algorithm=JWT_ALG)
    return token, exp_minutes * 60


def decode_widget_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET or "dev-change-me", algorithms=[JWT_ALG])
    except JWTError as exc:
        raise WidgetTokenValidationError("Invalid widget token") from exc

    if payload.get("typ") != "widget":
        raise WidgetTokenValidationError("Invalid widget token type")

    for key in ("tenant_id", "bot_id", "session_id", "origin"):
        if not payload.get(key):
            raise WidgetTokenValidationError("Invalid widget token payload")

    return payload
