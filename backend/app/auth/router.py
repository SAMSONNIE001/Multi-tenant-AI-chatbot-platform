import logging
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.tenants.models import Tenant
from app.auth.login_guard import clear_failures, is_locked, register_failure
from app.auth.models import PasswordResetToken, RefreshToken, User
from app.auth.schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
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
logger = logging.getLogger(__name__)


def _send_password_reset_email(
    *,
    to_email: str,
    tenant_id: str,
    reset_token: str,
    code: str,
    expires_minutes: int,
) -> bool:
    reset_link = ""
    if settings.FRONTEND_PUBLIC_BASE_URL:
        base = str(settings.FRONTEND_PUBLIC_BASE_URL).rstrip("/")
        reset_link = f"{base}/dashboard.html?reset_token={reset_token}"

    body_lines = [
        "We received a password reset request for your account.",
        "",
        f"Tenant ID: {tenant_id}",
        f"Reset code: {code}",
        f"This code expires in {expires_minutes} minutes.",
    ]
    if reset_link:
        body_lines.extend(["", f"Reset link: {reset_link}"])
    body_lines.extend(["", "If you did not request this, you can ignore this email."])

    if not settings.SMTP_HOST:
        logger.info(
            "Password reset email skipped (SMTP_HOST unset). email=%s tenant=%s",
            to_email,
            tenant_id,
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = "Password reset request"
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USERNAME or "no-reply@localhost"
    msg["To"] = to_email
    msg.set_content("\n".join(body_lines))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        if settings.SMTP_STARTTLS:
            smtp.starttls()
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
    return True


def _password_reset_public_message() -> str:
    return "If this account exists, a reset link and code have been sent to the account email."


def _enforce_refresh_token_limit(db: Session, *, user_id: str, tenant_id: str) -> None:
    now = datetime.now(timezone.utc)
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
    tenant_hint = (payload.tenant_id or "").strip() or None
    email = str(payload.email).lower()
    login_key = f"{tenant_hint or '*'}:{email}:{client_ip}"
    locked_until = is_locked(login_key)
    if locked_until:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Retry after {locked_until.isoformat()}",
        )

    user = None
    if tenant_hint:
        user = (
            db.query(User)
            .filter(
                User.tenant_id == tenant_hint,
                User.email == email,
            )
            .first()
        )
    else:
        candidates = (
            db.query(User)
            .filter(User.email == email)
            .limit(2)
            .all()
        )
        if len(candidates) > 1:
            raise HTTPException(
                status_code=409,
                detail="Multiple tenants found for this email. Provide tenant_id.",
            )
        if len(candidates) == 1:
            user = candidates[0]

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
    if row.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = db.get(User, user_id)
    if not user or user.tenant_id != tenant_id:
        raise HTTPException(status_code=401, detail="User not found")

    # Rotate refresh token on every refresh.
    row.revoked_at = datetime.now(timezone.utc)
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
        row.revoked_at = datetime.now(timezone.utc)
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


@router.post("/password/forgot", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    q = db.query(User).filter(User.email == email)
    if payload.tenant_id:
        q = q.filter(User.tenant_id == payload.tenant_id.strip())
    users = q.limit(5).all()

    now = datetime.now(timezone.utc)
    exp_minutes = max(5, int(settings.PASSWORD_RESET_EXP_MINUTES))
    expires_at = now + timedelta(minutes=exp_minutes)

    for user in users:
        raw_token = secrets.token_urlsafe(32)
        raw_code = f"{secrets.randbelow(1_000_000):06d}"
        row = PasswordResetToken(
            id=f"prt_{secrets.token_hex(12)}",
            user_id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            token_hash=hash_token(raw_token),
            code_hash=hash_token(raw_code),
            expires_at=expires_at,
            used_at=None,
        )
        db.add(row)
        try:
            _send_password_reset_email(
                to_email=user.email,
                tenant_id=user.tenant_id,
                reset_token=raw_token,
                code=raw_code,
                expires_minutes=exp_minutes,
            )
        except Exception:
            logger.exception("Failed to dispatch password reset email for tenant=%s", user.tenant_id)
    db.commit()
    return ForgotPasswordResponse(message=_password_reset_public_message())


@router.post("/password/reset", response_model=ResetPasswordResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    row = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == hash_token(payload.reset_token.strip()),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .order_by(PasswordResetToken.created_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    if row.code_hash != hash_token(payload.code.strip()):
        raise HTTPException(status_code=400, detail="Invalid reset code")

    user = db.get(User, row.user_id)
    if not user or user.tenant_id != row.tenant_id:
        raise HTTPException(status_code=400, detail="Reset request is no longer valid")

    try:
        user.password_hash = hash_password(payload.new_password)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    row.used_at = now
    db.add(user)
    db.add(row)

    active = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user.id,
            RefreshToken.tenant_id == user.tenant_id,
            RefreshToken.revoked_at.is_(None),
        )
        .all()
    )
    for token in active:
        token.revoked_at = now
        db.add(token)

    db.commit()
    return ResetPasswordResponse(message="Password reset successful. Please log in with the new password.")


