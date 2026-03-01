from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.models import User
from app.chat.router import ask as ask_internal
from app.chat.schemas import AskRequest, AskResponse
from app.chat.memory_models import Conversation, Message
from app.db.session import get_db
from app.embed.models import TenantBotCredential
from app.embed.schemas import (
    BotCredentialCreateRequest,
    BotCredentialOut,
    BotCredentialPatchRequest,
    BotCredentialRotateResponse,
    PublicAskRequest,
    PublicHandoffRequest,
    PublicHandoffResponse,
    PublicConversationMessage,
    PublicConversationUpdatesRequest,
    PublicConversationUpdatesResponse,
    WidgetTokenRequest,
    WidgetTokenResponse,
)
from app.embed.security import (
    WidgetTokenValidationError,
    create_widget_token,
    decode_widget_token,
    generate_bot_key,
    hash_bot_key,
)
from app.handoff.service import create_handoff_request
from app.tenants.models import Tenant

admin_router = APIRouter()
public_router = APIRouter()


def _normalize_origins(origins: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for origin in origins:
        val = origin.strip().rstrip("/").lower()
        if not val:
            continue
        if val not in seen:
            seen.add(val)
            out.append(val)
    return out


def _require_bot_for_tenant(db: Session, *, tenant_id: str, bot_id: str) -> TenantBotCredential:
    bot = db.execute(
        select(TenantBotCredential).where(
            TenantBotCredential.id == bot_id,
            TenantBotCredential.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot credential not found")
    return bot


@admin_router.get("/bots", response_model=list[BotCredentialOut])
def list_bots(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.execute(
        select(TenantBotCredential)
        .where(TenantBotCredential.tenant_id == current_user.tenant_id)
        .order_by(TenantBotCredential.created_at.desc())
    ).scalars().all()
    return rows


@admin_router.post("/bots", response_model=BotCredentialRotateResponse)
def create_bot(
    payload: BotCredentialCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw_key = generate_bot_key()
    bot = TenantBotCredential(
        id=f"bot_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
        tenant_id=current_user.tenant_id,
        name=payload.name,
        avatar_url=(payload.avatar_url.strip() if payload.avatar_url else None),
        key_hash=hash_bot_key(raw_key),
        allowed_origins=_normalize_origins(payload.allowed_origins),
        is_active=True,
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return BotCredentialRotateResponse(
        id=bot.id,
        tenant_id=bot.tenant_id,
        name=bot.name,
        api_key=raw_key,
        created_at=bot.created_at,
    )


@admin_router.patch("/bots/{bot_id}", response_model=BotCredentialOut)
def patch_bot(
    bot_id: str,
    payload: BotCredentialPatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bot = _require_bot_for_tenant(db, tenant_id=current_user.tenant_id, bot_id=bot_id)
    if payload.name is not None:
        bot.name = payload.name
    if payload.avatar_url is not None:
        bot.avatar_url = payload.avatar_url.strip() or None
    if payload.allowed_origins is not None:
        bot.allowed_origins = _normalize_origins(payload.allowed_origins)
    if payload.is_active is not None:
        bot.is_active = payload.is_active
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


@admin_router.post("/bots/{bot_id}/rotate-key", response_model=BotCredentialRotateResponse)
def rotate_bot_key(
    bot_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bot = _require_bot_for_tenant(db, tenant_id=current_user.tenant_id, bot_id=bot_id)
    raw_key = generate_bot_key()
    bot.key_hash = hash_bot_key(raw_key)
    bot.rotated_at = datetime.utcnow()
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return BotCredentialRotateResponse(
        id=bot.id,
        tenant_id=bot.tenant_id,
        name=bot.name,
        api_key=raw_key,
        created_at=bot.created_at,
    )


@public_router.post("/widget-token", response_model=WidgetTokenResponse)
def issue_widget_token(
    payload: WidgetTokenRequest,
    db: Session = Depends(get_db),
    x_bot_key: str | None = Header(default=None),
):
    if not x_bot_key:
        raise HTTPException(status_code=401, detail="Missing bot key")

    key_hash = hash_bot_key(x_bot_key)
    bot = db.execute(
        select(TenantBotCredential).where(TenantBotCredential.key_hash == key_hash)
    ).scalar_one_or_none()

    if not bot or not bot.is_active:
        raise HTTPException(status_code=401, detail="Invalid bot key")

    origin = payload.origin.strip().rstrip("/").lower()
    allowed = _normalize_origins(bot.allowed_origins or [])
    if allowed and origin not in allowed:
        raise HTTPException(status_code=403, detail="Origin not allowed")

    token, ttl_seconds = create_widget_token(
        tenant_id=bot.tenant_id,
        bot_id=bot.id,
        session_id=payload.session_id,
        origin=origin,
    )

    bot.last_used_at = datetime.utcnow()
    db.add(bot)
    db.commit()

    return WidgetTokenResponse(
        token=token,
        expires_in_seconds=ttl_seconds,
        bot_id=bot.id,
        tenant_id=bot.tenant_id,
    )


@public_router.post("/widget-token/by-bot/{bot_id}", response_model=WidgetTokenResponse)
def issue_widget_token_by_bot(
    bot_id: str,
    payload: WidgetTokenRequest,
    db: Session = Depends(get_db),
):
    bot = db.execute(
        select(TenantBotCredential).where(
            TenantBotCredential.id == bot_id,
            TenantBotCredential.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot credential not found")

    origin = payload.origin.strip().rstrip("/").lower()
    allowed = _normalize_origins(bot.allowed_origins or [])
    if allowed and origin not in allowed:
        raise HTTPException(status_code=403, detail="Origin not allowed")

    token, ttl_seconds = create_widget_token(
        tenant_id=bot.tenant_id,
        bot_id=bot.id,
        session_id=payload.session_id,
        origin=origin,
    )

    bot.last_used_at = datetime.utcnow()
    db.add(bot)
    db.commit()

    return WidgetTokenResponse(
        token=token,
        expires_in_seconds=ttl_seconds,
        bot_id=bot.id,
        tenant_id=bot.tenant_id,
    )


@public_router.post("/ask", response_model=AskResponse)
def ask_public(
    payload: PublicAskRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        claims = decode_widget_token(payload.widget_token)
    except WidgetTokenValidationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    bot = db.execute(
        select(TenantBotCredential).where(
            TenantBotCredential.id == claims["bot_id"],
            TenantBotCredential.tenant_id == claims["tenant_id"],
            TenantBotCredential.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=401, detail="Bot credential inactive")

    request_origin = (request.headers.get("origin") or "").strip().rstrip("/").lower()
    token_origin = str(claims["origin"]).strip().rstrip("/").lower()
    if request_origin and request_origin != token_origin:
        raise HTTPException(status_code=403, detail="Origin mismatch")

    allowed = _normalize_origins(bot.allowed_origins or [])
    if allowed and token_origin not in allowed:
        raise HTTPException(status_code=403, detail="Origin not allowed")

    widget_user_id = f"w_{claims['bot_id']}_{claims['session_id']}"[:64]
    tenant_name = (
        db.execute(
            select(Tenant.name).where(Tenant.id == claims["tenant_id"])
        ).scalar_one_or_none()
        or "our company"
    )
    bot_display_name = (bot.name or "").strip() or "AI Assistant"
    pseudo_user = SimpleNamespace(
        id=widget_user_id,
        tenant_id=claims["tenant_id"],
        tenant_name=tenant_name,
        bot_display_name=bot_display_name,
        bot_avatar_url=bot.avatar_url,
    )

    bot.last_used_at = datetime.utcnow()
    db.add(bot)
    db.commit()

    ask_payload = AskRequest(
        question=payload.question,
        top_k=payload.top_k,
        conversation_id=payload.conversation_id,
        memory_turns=payload.memory_turns,
    )
    return ask_internal(payload=ask_payload, db=db, current_user=pseudo_user)


@public_router.post("/conversation/updates", response_model=PublicConversationUpdatesResponse)
def conversation_updates_public(
    payload: PublicConversationUpdatesRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        claims = decode_widget_token(payload.widget_token)
    except WidgetTokenValidationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    bot = db.execute(
        select(TenantBotCredential).where(
            TenantBotCredential.id == claims["bot_id"],
            TenantBotCredential.tenant_id == claims["tenant_id"],
            TenantBotCredential.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=401, detail="Bot credential inactive")

    request_origin = (request.headers.get("origin") or "").strip().rstrip("/").lower()
    token_origin = str(claims["origin"]).strip().rstrip("/").lower()
    if request_origin and request_origin != token_origin:
        raise HTTPException(status_code=403, detail="Origin mismatch")

    allowed = _normalize_origins(bot.allowed_origins or [])
    if allowed and token_origin not in allowed:
        raise HTTPException(status_code=403, detail="Origin not allowed")

    widget_user_id = f"w_{claims['bot_id']}_{claims['session_id']}"[:64]
    conv = db.execute(
        select(Conversation).where(
            Conversation.id == payload.conversation_id,
            Conversation.tenant_id == claims["tenant_id"],
            Conversation.user_id == widget_user_id,
        )
    ).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    stmt = (
        select(Message)
        .where(
            Message.conversation_id == conv.id,
            Message.role == "agent",
        )
        .order_by(Message.created_at.asc())
        .limit(100)
    )
    if payload.since_iso:
        try:
            since_dt = datetime.fromisoformat(payload.since_iso.replace("Z", "+00:00"))
            if since_dt.tzinfo is not None:
                since_dt = since_dt.astimezone(timezone.utc).replace(tzinfo=None)
            stmt = stmt.where(Message.created_at > since_dt)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid since_iso format")

    rows = db.execute(stmt).scalars().all()
    return PublicConversationUpdatesResponse(
        conversation_id=conv.id,
        items=[
            PublicConversationMessage(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in rows
        ],
    )


@public_router.post("/handoff", response_model=PublicHandoffResponse)
def request_handoff_public(
    payload: PublicHandoffRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        claims = decode_widget_token(payload.widget_token)
    except WidgetTokenValidationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    bot = db.execute(
        select(TenantBotCredential).where(
            TenantBotCredential.id == claims["bot_id"],
            TenantBotCredential.tenant_id == claims["tenant_id"],
            TenantBotCredential.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=401, detail="Bot credential inactive")

    request_origin = (request.headers.get("origin") or "").strip().rstrip("/").lower()
    token_origin = str(claims["origin"]).strip().rstrip("/").lower()
    if request_origin and request_origin != token_origin:
        raise HTTPException(status_code=403, detail="Origin mismatch")

    allowed = _normalize_origins(bot.allowed_origins or [])
    if allowed and token_origin not in allowed:
        raise HTTPException(status_code=403, detail="Origin not allowed")

    widget_user_id = f"w_{claims['bot_id']}_{claims['session_id']}"[:64]
    row = create_handoff_request(
        db,
        tenant_id=claims["tenant_id"],
        user_id=widget_user_id,
        question=payload.question,
        conversation_id=payload.conversation_id,
        reason=payload.reason or "human_handoff",
        destination=payload.destination,
        source_channel="embed",
    )
    return PublicHandoffResponse(
        handoff_id=row.id,
        tenant_id=row.tenant_id,
        status=row.status,
        conversation_id=row.conversation_id,
    )
