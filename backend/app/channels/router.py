import json
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.rbac import require_scope
from app.auth.deps import get_current_user
from app.auth.models import User
from app.channels.models import TenantChannelAccount
from app.channels.schemas import (
    ChannelAccountHealthOut,
    ChannelAccountCreateRequest,
    ChannelAccountOut,
    ChannelAccountPatchRequest,
    ChannelAccountRotateTokenResponse,
    MetaWebhookResponse,
)
from app.channels.service import (
    generate_verify_token,
    normalize_channel_type,
    process_meta_webhook_payload,
    verify_meta_signature,
)
from app.db.session import get_db

admin_router = APIRouter()
webhook_router = APIRouter()


def _to_out(row: TenantChannelAccount) -> ChannelAccountOut:
    return ChannelAccountOut(
        id=row.id,
        tenant_id=row.tenant_id,
        channel_type=row.channel_type,
        name=row.name,
        verify_token=row.verify_token,
        has_app_secret=bool(row.app_secret),
        has_access_token=bool(row.access_token),
        phone_number_id=row.phone_number_id,
        page_id=row.page_id,
        instagram_account_id=row.instagram_account_id,
        metadata_json=row.metadata_json or {},
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_used_at=row.last_used_at,
        last_webhook_at=row.last_webhook_at,
        last_outbound_at=row.last_outbound_at,
        last_error=row.last_error,
        last_error_at=row.last_error_at,
    )


def _health_status(row: TenantChannelAccount) -> str:
    if not row.is_active:
        return "inactive"
    if row.last_error:
        return "error"
    if row.last_webhook_at or row.last_outbound_at:
        return "healthy"
    return "configured"


@admin_router.get("/accounts", response_model=list[ChannelAccountOut])
def list_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "channels:read")

    rows = db.execute(
        select(TenantChannelAccount)
        .where(TenantChannelAccount.tenant_id == current_user.tenant_id)
        .order_by(TenantChannelAccount.created_at.desc())
    ).scalars().all()
    return [_to_out(r) for r in rows]


@admin_router.post("/accounts", response_model=ChannelAccountOut)
def create_account(
    payload: ChannelAccountCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "channels:write")

    try:
        channel_type = normalize_channel_type(payload.channel_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    row = TenantChannelAccount(
        id=f"ch_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
        tenant_id=current_user.tenant_id,
        channel_type=channel_type,
        name=payload.name,
        verify_token=(payload.verify_token or generate_verify_token()),
        access_token=payload.access_token,
        app_secret=payload.app_secret,
        phone_number_id=payload.phone_number_id,
        page_id=payload.page_id,
        instagram_account_id=payload.instagram_account_id,
        metadata_json=payload.metadata_json,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@admin_router.patch("/accounts/{account_id}", response_model=ChannelAccountOut)
def patch_account(
    account_id: str,
    payload: ChannelAccountPatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "channels:write")

    row = db.execute(
        select(TenantChannelAccount).where(
            TenantChannelAccount.id == account_id,
            TenantChannelAccount.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Channel account not found")

    if payload.name is not None:
        row.name = payload.name
    if payload.access_token is not None:
        row.access_token = payload.access_token
    if payload.app_secret is not None:
        row.app_secret = payload.app_secret
    if payload.phone_number_id is not None:
        row.phone_number_id = payload.phone_number_id
    if payload.page_id is not None:
        row.page_id = payload.page_id
    if payload.instagram_account_id is not None:
        row.instagram_account_id = payload.instagram_account_id
    if payload.metadata_json is not None:
        row.metadata_json = payload.metadata_json
    if payload.is_active is not None:
        row.is_active = payload.is_active

    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@admin_router.post("/accounts/{account_id}/rotate-verify-token", response_model=ChannelAccountRotateTokenResponse)
def rotate_verify_token(
    account_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "channels:write")

    row = db.execute(
        select(TenantChannelAccount).where(
            TenantChannelAccount.id == account_id,
            TenantChannelAccount.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Channel account not found")

    row.verify_token = generate_verify_token()
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return ChannelAccountRotateTokenResponse(id=row.id, verify_token=row.verify_token)


@admin_router.get("/accounts/{account_id}/health", response_model=ChannelAccountHealthOut)
def get_account_health(
    account_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "channels:read")

    row = db.execute(
        select(TenantChannelAccount).where(
            TenantChannelAccount.id == account_id,
            TenantChannelAccount.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Channel account not found")

    return ChannelAccountHealthOut(
        id=row.id,
        tenant_id=row.tenant_id,
        channel_type=row.channel_type,
        is_active=row.is_active,
        status=_health_status(row),
        last_webhook_at=row.last_webhook_at,
        last_outbound_at=row.last_outbound_at,
        last_error=row.last_error,
        last_error_at=row.last_error_at,
    )


@webhook_router.get("/meta/webhook")
def verify_meta_webhook(
    mode: str | None = Query(default=None, alias="hub.mode"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
    db: Session = Depends(get_db),
):
    if mode != "subscribe" or not verify_token:
        raise HTTPException(status_code=400, detail="Invalid verification request")

    row = db.execute(
        select(TenantChannelAccount).where(
            TenantChannelAccount.verify_token == verify_token,
            TenantChannelAccount.is_active.is_(True),
        )
    ).scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=403, detail="Verification token mismatch")

    return PlainTextResponse(challenge or "")


@webhook_router.post("/meta/webhook", response_model=MetaWebhookResponse)
async def handle_meta_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_hub_signature_256: str | None = Header(default=None),
):
    raw = await request.body()

    if x_hub_signature_256:
        app_secrets = [
            r
            for r in db.execute(
                select(TenantChannelAccount.app_secret).where(TenantChannelAccount.is_active.is_(True))
            ).scalars().all()
            if r
        ]
        if app_secrets and not verify_meta_signature(raw, x_hub_signature_256, app_secrets):
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    processed, ignored = process_meta_webhook_payload(db, payload)
    return MetaWebhookResponse(received=True, processed_messages=processed, ignored_events=ignored)
