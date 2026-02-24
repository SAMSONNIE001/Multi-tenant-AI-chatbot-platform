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
        "conversations:read",
        "handoff:read",
        "handoff:write",
    },
    "auditor": {"audit:read", "conversations:read", "handoff:read"},
    "support": {"docs:read", "conversations:read", "audit:read", "handoff:read", "handoff:write"},
    "user": set(),
}


def require_scope(user: User, scope: str) -> None:
    role = (user.role or "user").lower()
    allowed = ROLE_SCOPES.get(role, set())
    if scope not in allowed:
        raise HTTPException(status_code=403, detail=f"Missing required scope: {scope}")
