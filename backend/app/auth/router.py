import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.tenants.models import Tenant
from app.auth.login_guard import clear_failures, is_locked, register_failure
from app.auth.models import RefreshToken, User
from app.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.auth.security import (
    JWTError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.auth.deps import get_current_user

router = APIRouter()
MAX_ACTIVE_REFRESH_TOKENS = 5


def _enforce_refresh_token_limit(db: Session, *, user_id: str, tenant_id: str) -> None:
    now = datetime.utcnow()
    active_tokens = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user_id,
            RefreshToken.tenant_id == tenant_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .order_by(RefreshToken.created_at.desc())
        .all()
    )
    for stale in active_tokens[MAX_ACTIVE_REFRESH_TOKENS:]:
        stale.revoked_at = now
        db.add(stale)


@router.post("/register", response_model=MeResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    tenant = db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    existing = (
        db.query(User)
        .filter(
            User.tenant_id == payload.tenant_id,
            User.email == str(payload.email).lower(),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    try:
        pw_hash = hash_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    user = User(
        id=payload.id,
        tenant_id=payload.tenant_id,
        email=str(payload.email).lower(),
        password_hash=pw_hash,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return MeResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        role=user.role,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    login_key = f"{payload.tenant_id}:{str(payload.email).lower()}:{client_ip}"
    locked_until = is_locked(login_key)
    if locked_until:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Retry after {locked_until.isoformat()}",
        )

    user = (
        db.query(User)
        .filter(
            User.tenant_id == payload.tenant_id,
            User.email == str(payload.email).lower(),
        )
        .first()
    )
    password_ok = False
    if user:
        try:
            password_ok = verify_password(payload.password, user.password_hash)
        except ValueError:
            password_ok = False

    if not user or not password_ok:
        new_lock = register_failure(login_key)
        if new_lock:
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed attempts. Retry after {new_lock.isoformat()}",
            )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    clear_failures(login_key)

    access_token = create_access_token(
        {"sub": user.id, "tenant_id": user.tenant_id, "role": user.role, "email": user.email}
    )
    refresh_token, refresh_expires_at = create_refresh_token(
        {"sub": user.id, "tenant_id": user.tenant_id}
    )
    refresh = RefreshToken(
        id=f"rt_{secrets.token_hex(10)}",
        user_id=user.id,
        tenant_id=user.tenant_id,
        token_hash=hash_token(refresh_token),
        expires_at=refresh_expires_at,
        revoked_at=None,
    )
    db.add(refresh)
    _enforce_refresh_token_limit(db, user_id=user.id, tenant_id=user.tenant_id)
    db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        claims = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if claims.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = claims.get("sub")
    tenant_id = claims.get("tenant_id")
    if not user_id or not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token payload")

    token_hash_value = hash_token(payload.refresh_token)
    row = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash_value,
            RefreshToken.user_id == user_id,
            RefreshToken.tenant_id == tenant_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=401, detail="Refresh token not recognized")
    if row.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Refresh token revoked")
    if row.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = db.get(User, user_id)
    if not user or user.tenant_id != tenant_id:
        raise HTTPException(status_code=401, detail="User not found")

    # Rotate refresh token on every refresh.
    row.revoked_at = datetime.utcnow()
    db.add(row)

    access_token = create_access_token(
        {"sub": user.id, "tenant_id": user.tenant_id, "role": user.role, "email": user.email}
    )
    new_refresh_token, refresh_expires_at = create_refresh_token(
        {"sub": user.id, "tenant_id": user.tenant_id}
    )
    db.add(
        RefreshToken(
            id=f"rt_{secrets.token_hex(10)}",
            user_id=user.id,
            tenant_id=user.tenant_id,
            token_hash=hash_token(new_refresh_token),
            expires_at=refresh_expires_at,
            revoked_at=None,
        )
    )
    _enforce_refresh_token_limit(db, user_id=user.id, tenant_id=user.tenant_id)
    db.commit()

    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout")
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    try:
        claims = decode_token(payload.refresh_token)
    except JWTError:
        return {"ok": True}

    user_id = claims.get("sub")
    tenant_id = claims.get("tenant_id")
    token_hash_value = hash_token(payload.refresh_token)
    row = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash_value,
            RefreshToken.user_id == user_id,
            RefreshToken.tenant_id == tenant_id,
        )
        .first()
    )
    if row and row.revoked_at is None:
        row.revoked_at = datetime.utcnow()
        db.add(row)
        db.commit()

    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)):
    return MeResponse(
        id=current_user.id,
        tenant_id=current_user.tenant_id,
        email=current_user.email,
        role=current_user.role,
    )
