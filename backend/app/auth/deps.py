from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.auth.models import User
from app.auth.security import decode_token

bearer = HTTPBearer(auto_error=False)

ROLE_ORDER = {"viewer": 1, "editor": 2, "admin": 3, "owner": 4}


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        payload = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    token_type = payload.get("typ")
    if token_type and token_type != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    if not user_id or not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.get(User, user_id)
    if not user or user.tenant_id != tenant_id:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def require_role(min_role: str):
    def _dep(user: User = Depends(get_current_user)) -> User:
        if ROLE_ORDER.get(user.role, 0) < ROLE_ORDER.get(min_role, 999):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return _dep
