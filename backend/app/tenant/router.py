import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.models import RefreshToken, User
from app.auth.rbac import require_roles
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
)
from app.db.session import get_db
from app.embed.models import TenantBotCredential
from app.embed.router import _normalize_origins
from app.embed.security import generate_bot_key, hash_bot_key
from app.core.config import settings
from app.rag.embeddings import embed_text
from app.rag.file_extract import extract_text_from_upload
from app.rag.models import Chunk, Document
from app.rag.service import ingest_text_document
from app.tenant.schemas import (
    TenantEmbedSnippetResponse,
    TenantKnowledgeReindexRequest,
    TenantKnowledgeReindexResponse,
    TenantKnowledgeStatusResponse,
    TenantKnowledgeUploadResponse,
    TenantOnboardRequest,
    TenantOnboardResponse,
    TenantProfilePatchRequest,
)
from app.tenants.models import Tenant

router = APIRouter()


def _slugify(value: str, *, fallback: str) -> str:
    raw = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    raw = "_".join(part for part in raw.split("_") if part)
    return raw[:40] if raw else fallback


def _https_base(url: str) -> str:
    cleaned = str(url or "").strip().rstrip("/")
    if cleaned.startswith("http://"):
        return "https://" + cleaned[len("http://") :]
    return cleaned


def _resolve_widget_script_base(bot: TenantBotCredential) -> str:
    explicit = str(settings.FRONTEND_PUBLIC_BASE_URL or "").strip().rstrip("/")
    if explicit:
        return _https_base(explicit)
    for origin in bot.allowed_origins or []:
        normalized = _https_base(origin)
        if normalized.startswith("https://"):
            return normalized
    return "https://www.staunchbot.com"


def _js_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


@router.post("/onboard", response_model=TenantOnboardResponse)
def tenant_onboard(
    payload: TenantOnboardRequest,
    db: Session = Depends(get_db),
):
    tenant_id = payload.tenant_id or f"t_{_slugify(payload.tenant_name, fallback='tenant')}"
    admin_id = payload.admin_id or f"u_{_slugify(payload.admin_email.split('@')[0], fallback='admin')}"

    existing_tenant = db.get(Tenant, tenant_id)
    if existing_tenant:
        raise HTTPException(status_code=409, detail="Tenant already exists")

    existing_user = db.query(User).filter(User.id == admin_id).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Admin user id already exists")

    existing_email = (
        db.query(User)
        .filter(
            User.tenant_id == tenant_id,
            User.email == str(payload.admin_email).lower(),
        )
        .first()
    )
    if existing_email:
        raise HTTPException(status_code=409, detail="Admin email already exists for tenant")

    try:
        pw_hash = hash_password(payload.admin_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    tenant = Tenant(
        id=tenant_id,
        name=payload.tenant_name,
        avatar_url=(payload.company_avatar_url.strip() if payload.company_avatar_url else None),
        compliance_level=payload.compliance_level,
    )
    admin = User(
        id=admin_id,
        tenant_id=tenant_id,
        email=str(payload.admin_email).lower(),
        password_hash=pw_hash,
        role="admin",
    )

    raw_key = generate_bot_key()
    bot = TenantBotCredential(
        id=f"bot_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
        tenant_id=tenant_id,
        name=payload.bot_name,
        avatar_url=(payload.company_avatar_url.strip() if payload.company_avatar_url else None),
        key_hash=hash_bot_key(raw_key),
        allowed_origins=_normalize_origins(payload.allowed_origins),
        is_active=True,
    )

    db.add(tenant)
    db.add(admin)
    db.add(bot)

    access_token = create_access_token(
        {"sub": admin.id, "tenant_id": admin.tenant_id, "role": admin.role, "email": admin.email}
    )
    refresh_token, refresh_expires_at = create_refresh_token(
        {"sub": admin.id, "tenant_id": admin.tenant_id}
    )
    db.add(
        RefreshToken(
            id=f"rt_{secrets.token_hex(10)}",
            user_id=admin.id,
            tenant_id=admin.tenant_id,
            token_hash=hash_token(refresh_token),
            expires_at=refresh_expires_at,
            revoked_at=None,
        )
    )

    db.commit()

    return TenantOnboardResponse(
        tenant={
            "id": tenant.id,
            "name": tenant.name,
            "avatar_url": tenant.avatar_url,
            "compliance_level": tenant.compliance_level,
        },
        admin={
            "id": admin.id,
            "tenant_id": admin.tenant_id,
            "email": admin.email,
            "role": admin.role,
        },
        bot_id=bot.id,
        bot_api_key=raw_key,
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.get("/bots")
def tenant_bots(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.execute(
        select(TenantBotCredential)
        .where(TenantBotCredential.tenant_id == current_user.tenant_id)
        .order_by(TenantBotCredential.created_at.desc())
    ).scalars().all()
    return rows


@router.post("/bots")
def tenant_create_bot(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "owner")),
):
    name = str(payload.get("name", "")).strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="name must be at least 2 characters")
    allowed_origins = payload.get("allowed_origins", [])
    if not isinstance(allowed_origins, list):
        raise HTTPException(status_code=422, detail="allowed_origins must be a list")

    raw_key = generate_bot_key()
    tenant = db.get(Tenant, current_user.tenant_id)
    bot = TenantBotCredential(
        id=f"bot_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
        tenant_id=current_user.tenant_id,
        name=name,
        avatar_url=(
            str(payload.get("avatar_url", "")).strip()
            or (tenant.avatar_url if tenant else None)
        ),
        key_hash=hash_bot_key(raw_key),
        allowed_origins=_normalize_origins(allowed_origins),
        is_active=True,
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return {
        "id": bot.id,
        "tenant_id": bot.tenant_id,
        "name": bot.name,
        "api_key": raw_key,
        "created_at": bot.created_at,
    }


@router.patch("/bots/{bot_id}")
def tenant_patch_bot(
    bot_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "owner")),
):
    bot = db.execute(
        select(TenantBotCredential).where(
            TenantBotCredential.id == bot_id,
            TenantBotCredential.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot credential not found")

    if "name" in payload:
        name = str(payload["name"]).strip()
        if len(name) < 2:
            raise HTTPException(status_code=422, detail="name must be at least 2 characters")
        bot.name = name
    if "avatar_url" in payload:
        bot.avatar_url = str(payload["avatar_url"]).strip() or None
    if "allowed_origins" in payload:
        if not isinstance(payload["allowed_origins"], list):
            raise HTTPException(status_code=422, detail="allowed_origins must be a list")
        bot.allowed_origins = _normalize_origins(payload["allowed_origins"])
    if "is_active" in payload:
        bot.is_active = bool(payload["is_active"])

    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


@router.post("/bots/{bot_id}/rotate-key")
def tenant_rotate_bot_key(
    bot_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "owner")),
):
    bot = db.execute(
        select(TenantBotCredential).where(
            TenantBotCredential.id == bot_id,
            TenantBotCredential.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot credential not found")

    raw_key = generate_bot_key()
    bot.key_hash = hash_bot_key(raw_key)
    bot.rotated_at = datetime.utcnow()
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return {
        "id": bot.id,
        "tenant_id": bot.tenant_id,
        "name": bot.name,
        "api_key": raw_key,
        "created_at": bot.created_at,
    }


@router.post("/knowledge/upload", response_model=TenantKnowledgeUploadResponse)
async def tenant_upload_knowledge(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("editor", "admin", "owner")),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    raw = await file.read()
    if len(raw) > 10_000_000:
        raise HTTPException(status_code=413, detail="File too large (max 10MB).")
    try:
        content_type, text = extract_text_from_upload(
            filename=file.filename,
            content_type=file.content_type,
            raw=raw,
        )
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    doc = ingest_text_document(
        db=db,
        tenant_id=current_user.tenant_id,
        filename=file.filename,
        content_type=content_type,
        text=text,
    )
    chunk_count = (
        db.query(func.count(Chunk.id))
        .filter(
            Chunk.tenant_id == current_user.tenant_id,
            Chunk.document_id == doc.id,
        )
        .scalar()
        or 0
    )
    return TenantKnowledgeUploadResponse(
        document_id=doc.id,
        tenant_id=doc.tenant_id,
        filename=doc.filename,
        content_type=doc.content_type,
        chunk_count=int(chunk_count),
    )


@router.post("/knowledge/reindex", response_model=TenantKnowledgeReindexResponse)
def tenant_reindex_knowledge(
    payload: TenantKnowledgeReindexRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("editor", "admin", "owner")),
):
    query = db.query(Chunk).filter(Chunk.tenant_id == current_user.tenant_id)
    if payload.document_id:
        query = query.filter(Chunk.document_id == payload.document_id)
    chunks = query.all()

    updated = 0
    for chunk in chunks:
        try:
            chunk.embedding = embed_text(chunk.text)
            db.add(chunk)
            updated += 1
        except Exception:
            continue
    db.commit()

    return TenantKnowledgeReindexResponse(
        tenant_id=current_user.tenant_id,
        document_id=payload.document_id,
        chunks_reindexed=updated,
        openai_enabled=updated > 0,
        status="completed",
    )


@router.get("/knowledge/status", response_model=TenantKnowledgeStatusResponse)
def tenant_knowledge_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document_count = (
        db.query(func.count(Document.id))
        .filter(Document.tenant_id == current_user.tenant_id)
        .scalar()
        or 0
    )
    chunk_count = (
        db.query(func.count(Chunk.id))
        .filter(Chunk.tenant_id == current_user.tenant_id)
        .scalar()
        or 0
    )
    latest_doc = (
        db.query(Document)
        .filter(Document.tenant_id == current_user.tenant_id)
        .order_by(desc(Document.created_at))
        .first()
    )
    return TenantKnowledgeStatusResponse(
        tenant_id=current_user.tenant_id,
        document_count=int(document_count),
        chunk_count=int(chunk_count),
        latest_document_id=latest_doc.id if latest_doc else None,
        latest_document_at=latest_doc.created_at if latest_doc else None,
    )


@router.get("/embed/snippet", response_model=TenantEmbedSnippetResponse)
def tenant_embed_snippet(
    request: Request,
    bot_id: str = Query(min_length=3, max_length=64),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bot = db.execute(
        select(TenantBotCredential).where(
            TenantBotCredential.id == bot_id,
            TenantBotCredential.tenant_id == current_user.tenant_id,
            TenantBotCredential.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot credential not found")

    api_base = _https_base(str(request.base_url).rstrip("/"))
    widget_script_base = _resolve_widget_script_base(bot)
    tenant = db.get(Tenant, current_user.tenant_id)
    bot_title = (bot.name or "").strip() or "AI Assistant"
    company_name = ((tenant.name if tenant else "") or "our company").strip()
    effective_avatar_url = (bot.avatar_url or (tenant.avatar_url if tenant else None) or "").strip()
    avatar_cfg = (
        f',\n  avatarUrl: "{_js_escape(effective_avatar_url)}"' if effective_avatar_url else ""
    )
    welcome_message = (
        f"Welcome to {company_name}. "
        f"I'm {bot_title}, your AI customer agent. How can I help you today?"
    )
    snippet = (
        f'<script src="{widget_script_base}/chat-widget.js"></script>\n'
        "<script>\n"
        "window.MTChatWidget.init({\n"
        f'  apiBase: "{api_base}",\n'
        f'  botId: "{bot.id}",\n'
        '  mode: "bubble",\n'
        '  title: "Live Chat",\n'
        f'  subtitle: "{_js_escape(bot_title)}",\n'
        f'  companyName: "{_js_escape(company_name)}",\n'
        f'  assistantName: "{_js_escape(bot_title)}",\n'
        f'  welcomeMessage: "{_js_escape(welcome_message)}",\n'
        f"{avatar_cfg}\n"
        '  placeholder: "Ask a question..."\n'
        "});\n"
        "</script>"
    )
    return TenantEmbedSnippetResponse(
        tenant_id=current_user.tenant_id,
        bot_id=bot.id,
        api_base=api_base,
        snippet_html=snippet,
    )


@router.patch("/profile")
def tenant_patch_profile(
    payload: TenantProfilePatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "owner")),
):
    tenant = db.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if payload.company_name is not None:
        tenant.name = payload.company_name.strip()
    if payload.company_avatar_url is not None:
        tenant.avatar_url = payload.company_avatar_url.strip() or None

    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return {
        "id": tenant.id,
        "name": tenant.name,
        "avatar_url": tenant.avatar_url,
        "compliance_level": tenant.compliance_level,
    }
