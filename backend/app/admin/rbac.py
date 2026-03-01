from fastapi import HTTPException

from app.auth.models import User


ROLE_SCOPES: dict[str, set[str]] = {
    "admin": {
        "docs:read",
        "docs:write",
        "docs:delete",
        "policy:read",
        "policy:write",
        "audit:read",
        "audit:write",
        "conversations:read",
        "handoff:read",
        "handoff:write",
        "channels:read",
        "channels:write",
    },
    "auditor": {"audit:read", "conversations:read", "handoff:read", "channels:read"},
    "support": {
        "docs:read",
        "conversations:read",
        "audit:read",
        "audit:write",
        "handoff:read",
        "handoff:write",
        "channels:read",
    },
    "user": set(),
}


def require_scope(user: User, scope: str) -> None:
    role = (user.role or "user").lower()
    allowed = ROLE_SCOPES.get(role, set())
    if scope not in allowed:
        raise HTTPException(status_code=403, detail=f"Missing required scope: {scope}")
