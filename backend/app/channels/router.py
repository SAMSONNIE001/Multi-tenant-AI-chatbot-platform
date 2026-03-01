import json
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.admin.rbac import require_scope
from app.auth.deps import get_current_user
from app.auth.models import User
from app.channels.models import CustomerChannelHandle, CustomerProfile, TenantChannelAccount
from app.channels.schemas import (
    ChannelAccountHealthOut,
    ChannelAccountCreateRequest,
    ChannelAccountOut,
    ChannelAccountPatchRequest,
    ChannelAccountRotateTokenResponse,
    CustomerProfilesResponse,
    CustomerProfileMergeRequest,
    CustomerProfileMergeResponse,
    CustomerProfileOut,
    CustomerChannelHandleOut,
    MetaWebhookResponse,
)
from app.channels.service import (
    generate_verify_token,
    normalize_channel_type,
    process_meta_webhook_payload,
    verify_meta_signature,
)
from app.chat.memory_models import Conversation
from app.db.session import get_db
from app.handoff.models import HandoffRequest

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


def _to_profile_out(
    profile: CustomerProfile,
    *,
    handles: list[CustomerChannelHandle],
    conversation_count: int,
    handoff_count: int,
) -> CustomerProfileOut:
    return CustomerProfileOut(
        id=profile.id,
        tenant_id=profile.tenant_id,
        display_name=profile.display_name,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        conversation_count=int(conversation_count or 0),
        handoff_count=int(handoff_count or 0),
        handles=[
            CustomerChannelHandleOut(
                id=h.id,
                channel_type=h.channel_type,
                external_user_id=h.external_user_id,
                last_seen_at=h.last_seen_at,
                created_at=h.created_at,
                updated_at=h.updated_at,
            )
            for h in handles
        ],
    )


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


@admin_router.get("/profiles", response_model=CustomerProfilesResponse)
def list_customer_profiles(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "channels:read")

    profiles = db.execute(
        select(CustomerProfile)
        .where(CustomerProfile.tenant_id == current_user.tenant_id)
        .order_by(CustomerProfile.updated_at.desc())
        .limit(limit)
    ).scalars().all()

    profile_ids = [p.id for p in profiles]
    if not profile_ids:
        return {"tenant_id": current_user.tenant_id, "profiles": []}

    handles_rows = db.execute(
        select(CustomerChannelHandle).where(
            CustomerChannelHandle.tenant_id == current_user.tenant_id,
            CustomerChannelHandle.customer_profile_id.in_(profile_ids),
        )
    ).scalars().all()
    handles_by_profile: dict[str, list[CustomerChannelHandle]] = {}
    for h in handles_rows:
        handles_by_profile.setdefault(h.customer_profile_id, []).append(h)

    conv_counts_rows = db.execute(
        select(Conversation.user_id, func.count(Conversation.id))
        .where(
            Conversation.tenant_id == current_user.tenant_id,
            Conversation.user_id.in_(profile_ids),
        )
        .group_by(Conversation.user_id)
    ).all()
    conv_counts = {uid: int(cnt) for uid, cnt in conv_counts_rows}

    handoff_counts_rows = db.execute(
        select(HandoffRequest.user_id, func.count(HandoffRequest.id))
        .where(
            HandoffRequest.tenant_id == current_user.tenant_id,
            HandoffRequest.user_id.in_(profile_ids),
        )
        .group_by(HandoffRequest.user_id)
    ).all()
    handoff_counts = {uid: int(cnt) for uid, cnt in handoff_counts_rows}

    return {
        "tenant_id": current_user.tenant_id,
        "profiles": [
            _to_profile_out(
                p,
                handles=sorted(
                    handles_by_profile.get(p.id, []),
                    key=lambda x: ((x.channel_type or ""), (x.external_user_id or "")),
                ),
                conversation_count=conv_counts.get(p.id, 0),
                handoff_count=handoff_counts.get(p.id, 0),
            )
            for p in profiles
        ],
    }


@admin_router.post("/profiles/merge", response_model=CustomerProfileMergeResponse)
def merge_customer_profiles(
    payload: CustomerProfileMergeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_scope(current_user, "channels:write")

    source = db.execute(
        select(CustomerProfile).where(
            CustomerProfile.id == payload.source_profile_id,
            CustomerProfile.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source profile not found")

    target = db.execute(
        select(CustomerProfile).where(
            CustomerProfile.id == payload.target_profile_id,
            CustomerProfile.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Target profile not found")

    if source.id == target.id:
        raise HTTPException(status_code=422, detail="source_profile_id and target_profile_id must differ")

    moved_handles = 0
    deduped_handles = 0
    now = datetime.utcnow()

    source_handles = db.execute(
        select(CustomerChannelHandle).where(
            CustomerChannelHandle.tenant_id == current_user.tenant_id,
            CustomerChannelHandle.customer_profile_id == source.id,
        )
    ).scalars().all()
    for handle in source_handles:
        duplicate = db.execute(
            select(CustomerChannelHandle).where(
                CustomerChannelHandle.tenant_id == current_user.tenant_id,
                CustomerChannelHandle.customer_profile_id == target.id,
                CustomerChannelHandle.channel_type == handle.channel_type,
                CustomerChannelHandle.external_user_id == handle.external_user_id,
            )
        ).scalar_one_or_none()
        if duplicate:
            db.delete(handle)
            deduped_handles += 1
            continue
        handle.customer_profile_id = target.id
        handle.updated_at = now
        db.add(handle)
        moved_handles += 1

    moved_conversations = db.execute(
        update(Conversation)
        .where(
            Conversation.tenant_id == current_user.tenant_id,
            Conversation.user_id == source.id,
        )
        .values(user_id=target.id)
    ).rowcount or 0

    moved_handoffs = db.execute(
        update(HandoffRequest)
        .where(
            HandoffRequest.tenant_id == current_user.tenant_id,
            HandoffRequest.user_id == source.id,
        )
        .values(user_id=target.id)
    ).rowcount or 0

    target.updated_at = now
    db.add(target)
    db.delete(source)
    db.commit()

    return {
        "tenant_id": current_user.tenant_id,
        "source_profile_id": payload.source_profile_id,
        "target_profile_id": payload.target_profile_id,
        "moved_handles": int(moved_handles),
        "deduped_handles": int(deduped_handles),
        "moved_conversations": int(moved_conversations),
        "moved_handoffs": int(moved_handoffs),
    }


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
