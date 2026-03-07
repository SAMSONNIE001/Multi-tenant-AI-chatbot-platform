import logging
import secrets
import base64
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.tenants.models import Tenant
from app.auth.login_guard import clear_failures, is_locked, register_failure
from app.auth.models import AuthSecurityEvent, PasswordResetToken, RefreshToken, User, UserProfilePreference
from app.auth.schemas import (
    DeleteAccountResponse,
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
    ProfileImageUploadResponse,
    UserPreferenceResponse,
    UserPreferenceUpdateRequest,
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
from app.notifications.email_service import send_transactional_email, send_welcome_email

router = APIRouter()
MAX_ACTIVE_REFRESH_TOKENS = 5
logger = logging.getLogger(__name__)
FORGOT_WINDOW_SECONDS = 15 * 60
FORGOT_MAX_PER_WINDOW = 3
RESET_FAIL_WINDOW_SECONDS = 15 * 60
RESET_FAIL_MAX = 5
_forgot_attempts: dict[str, deque[datetime]] = defaultdict(deque)
_reset_fail_attempts: dict[str, deque[datetime]] = defaultdict(deque)


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

    return send_transactional_email(
        to_email=to_email,
        subject="Password reset request",
        text_body="\n".join(body_lines),
        html_body=None,
    )


def _password_reset_public_message() -> str:
    return "If this account exists, a reset link and code have been sent to the account email."


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _prune_attempts(store: dict[str, deque[datetime]], key: str, now: datetime, window_seconds: int) -> None:
    q = store[key]
    cutoff = now - timedelta(seconds=window_seconds)
    while q and q[0] < cutoff:
        q.popleft()


def _is_rate_limited(store: dict[str, deque[datetime]], key: str, now: datetime, window_seconds: int, limit: int) -> bool:
    _prune_attempts(store, key, now, window_seconds)
    return len(store[key]) >= limit


def _register_attempt(store: dict[str, deque[datetime]], key: str, now: datetime) -> None:
    store[key].append(now)


def _log_auth_security_event(
    db: Session,
    *,
    tenant_id: str | None,
    user_id: str | None,
    email: str,
    event_type: str,
    outcome: str,
    ip_address: str | None,
    metadata_json: dict[str, object] | None = None,
) -> None:
    db.add(
        AuthSecurityEvent(
            id=f"ase_{secrets.token_hex(10)}",
            tenant_id=tenant_id,
            user_id=user_id,
            email=str(email or "").lower(),
            event_type=event_type.strip().lower(),
            outcome=outcome.strip().lower(),
            ip_address=ip_address,
            metadata_json=metadata_json or {},
        )
    )


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
    login_url = f"{str(settings.FRONTEND_PUBLIC_BASE_URL).rstrip('/')}/dashboard.html" if settings.FRONTEND_PUBLIC_BASE_URL else None
    reset_url = f"{str(settings.FRONTEND_PUBLIC_BASE_URL).rstrip('/')}/auth.html" if settings.FRONTEND_PUBLIC_BASE_URL else None
    try:
        sent = send_welcome_email(
            to_email=user.email,
            tenant_name=tenant.name or user.tenant_id,
            login_url=login_url,
            reset_url=reset_url,
        )
        if not sent:
            logger.warning("Welcome email not sent for user=%s tenant=%s (provider returned false)", user.id, user.tenant_id)
    except Exception:
        logger.exception("Failed to dispatch welcome email for user=%s tenant=%s", user.id, user.tenant_id)

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
    expires_at = _as_utc(row.expires_at)
    if expires_at and expires_at <= datetime.now(timezone.utc):
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


@router.delete("/me", response_model=DeleteAccountResponse)
def delete_my_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    # Revoke all refresh tokens for this user.
    active = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == current_user.id,
            RefreshToken.tenant_id == current_user.tenant_id,
            RefreshToken.revoked_at.is_(None),
        )
        .all()
    )
    for token in active:
        token.revoked_at = now
        db.add(token)

    # Remove user preference rows.
    (
        db.query(UserProfilePreference)
        .filter(
            UserProfilePreference.user_id == current_user.id,
            UserProfilePreference.tenant_id == current_user.tenant_id,
        )
        .delete()
    )

    # Remove password reset tokens tied to this user.
    (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == current_user.id,
            PasswordResetToken.tenant_id == current_user.tenant_id,
        )
        .delete()
    )

    # Delete user account.
    row = (
        db.query(User)
        .filter(
            User.id == current_user.id,
            User.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if row:
        db.delete(row)

    db.commit()
    return DeleteAccountResponse(ok=True, message="Account deleted successfully.")


@router.get("/preferences", response_model=UserPreferenceResponse)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(UserProfilePreference)
        .filter(
            UserProfilePreference.user_id == current_user.id,
            UserProfilePreference.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not row:
        return UserPreferenceResponse(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            preferred_name=None,
            timezone=None,
            bot_name=None,
            profile_image_data=None,
        )
    return UserPreferenceResponse(
        user_id=row.user_id,
        tenant_id=row.tenant_id,
        preferred_name=row.preferred_name,
        timezone=row.timezone,
        bot_name=row.bot_name,
        profile_image_data=row.profile_image_data,
    )


@router.put("/preferences", response_model=UserPreferenceResponse)
def put_preferences(
    payload: UserPreferenceUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(UserProfilePreference)
        .filter(
            UserProfilePreference.user_id == current_user.id,
            UserProfilePreference.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    now = datetime.now(timezone.utc)
    if not row:
        row = UserProfilePreference(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            preferred_name=(payload.preferred_name or None),
            timezone=(payload.timezone or None),
            bot_name=(payload.bot_name or None),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.preferred_name = payload.preferred_name or None
        row.timezone = payload.timezone or None
        row.bot_name = payload.bot_name or None
        row.updated_at = now
        db.add(row)
    db.commit()
    db.refresh(row)
    return UserPreferenceResponse(
        user_id=row.user_id,
        tenant_id=row.tenant_id,
        preferred_name=row.preferred_name,
        timezone=row.timezone,
        bot_name=row.bot_name,
        profile_image_data=row.profile_image_data,
    )


@router.post("/preferences/profile-image", response_model=ProfileImageUploadResponse)
async def upload_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content_type = str(file.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="Only image uploads are allowed")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")
    # Keep payload bounded for DB storage.
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Image too large. Max 2MB.")

    encoded = base64.b64encode(raw).decode("ascii")
    data_url = f"data:{content_type};base64,{encoded}"

    now = datetime.now(timezone.utc)
    row = (
        db.query(UserProfilePreference)
        .filter(
            UserProfilePreference.user_id == current_user.id,
            UserProfilePreference.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not row:
        row = UserProfilePreference(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            profile_image_data=data_url,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.profile_image_data = data_url
        row.updated_at = now
        db.add(row)
    db.commit()
    return ProfileImageUploadResponse(
        ok=True,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        profile_image_data=data_url,
    )


@router.post("/password/forgot", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    tenant_hint = (payload.tenant_id or "").strip() or "*"
    client_ip = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)
    limit_key = f"{tenant_hint}:{email}:{client_ip}"
    if _is_rate_limited(_forgot_attempts, limit_key, now, FORGOT_WINDOW_SECONDS, FORGOT_MAX_PER_WINDOW):
        _log_auth_security_event(
            db,
            tenant_id=payload.tenant_id.strip() if payload.tenant_id else None,
            user_id=None,
            email=email,
            event_type="password_forgot",
            outcome="rate_limited",
            ip_address=client_ip,
            metadata_json={"tenant_hint": tenant_hint},
        )
        db.commit()
        return ForgotPasswordResponse(message=_password_reset_public_message())
    _register_attempt(_forgot_attempts, limit_key, now)

    q = db.query(User).filter(User.email == email)
    if payload.tenant_id:
        q = q.filter(User.tenant_id == payload.tenant_id.strip())
    users = q.limit(5).all()
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
            sent = _send_password_reset_email(
                to_email=user.email,
                tenant_id=user.tenant_id,
                reset_token=raw_token,
                code=raw_code,
                expires_minutes=exp_minutes,
            )
            _log_auth_security_event(
                db,
                tenant_id=user.tenant_id,
                user_id=user.id,
                email=user.email,
                event_type="password_forgot",
                outcome="success" if sent else "queued",
                ip_address=client_ip,
                metadata_json={"expires_minutes": exp_minutes},
            )
        except Exception:
            logger.exception("Failed to dispatch password reset email for tenant=%s", user.tenant_id)
            _log_auth_security_event(
                db,
                tenant_id=user.tenant_id,
                user_id=user.id,
                email=user.email,
                event_type="password_forgot",
                outcome="email_error",
                ip_address=client_ip,
                metadata_json={"expires_minutes": exp_minutes},
            )
    if not users:
        _log_auth_security_event(
            db,
            tenant_id=payload.tenant_id.strip() if payload.tenant_id else None,
            user_id=None,
            email=email,
            event_type="password_forgot",
            outcome="not_found",
            ip_address=client_ip,
            metadata_json={"tenant_hint": tenant_hint},
        )
    db.commit()
    return ForgotPasswordResponse(message=_password_reset_public_message())


@router.post("/password/reset", response_model=ResetPasswordResponse)
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    token_hash_value = hash_token(payload.reset_token.strip())
    client_ip = request.client.host if request.client else "unknown"
    limit_key = f"{token_hash_value}:{client_ip}"
    if _is_rate_limited(_reset_fail_attempts, limit_key, now, RESET_FAIL_WINDOW_SECONDS, RESET_FAIL_MAX):
        _log_auth_security_event(
            db,
            tenant_id=None,
            user_id=None,
            email="unknown",
            event_type="password_reset",
            outcome="rate_limited",
            ip_address=client_ip,
        )
        db.commit()
        raise HTTPException(status_code=429, detail="Too many failed reset attempts. Request a new reset email.")

    row = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == token_hash_value,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .order_by(PasswordResetToken.created_at.desc())
        .first()
    )
    if not row:
        _register_attempt(_reset_fail_attempts, limit_key, now)
        _log_auth_security_event(
            db,
            tenant_id=None,
            user_id=None,
            email="unknown",
            event_type="password_reset",
            outcome="invalid_token",
            ip_address=client_ip,
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    if row.code_hash != hash_token(payload.code.strip()):
        _register_attempt(_reset_fail_attempts, limit_key, now)
        _log_auth_security_event(
            db,
            tenant_id=row.tenant_id,
            user_id=row.user_id,
            email=row.email,
            event_type="password_reset",
            outcome="invalid_code",
            ip_address=client_ip,
        )
        db.commit()
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
    _reset_fail_attempts.pop(limit_key, None)
    _log_auth_security_event(
        db,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        email=row.email,
        event_type="password_reset",
        outcome="success",
        ip_address=client_ip,
    )
    db.commit()
    return ResetPasswordResponse(message="Password reset successful. Please log in with the new password.")


