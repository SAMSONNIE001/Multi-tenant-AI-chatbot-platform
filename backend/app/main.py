import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.engine.url import make_url

from app.auth.router import router as auth_router
from app.tenants.router import router as tenants_router
from app.rag.router import router as rag_router
from app.chat.router import router as chat_router
from app.admin.router import router as admin_router
from app.system.router import router as system_router
from app.system.metrics_router import router as metrics_router
from app.governance.router import router as governance_router
from app.embed.router import admin_router as embed_admin_router
from app.embed.router import public_router as embed_public_router
from app.handoff.router import admin_router as handoff_admin_router
from app.handoff.router import router as handoff_router
from app.channels.router import admin_router as channels_admin_router
from app.channels.router import webhook_router as channels_webhook_router
from app.tenant.router import router as tenant_router
from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import engine
from app.system.security_headers import SecurityHeadersMiddleware

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Multi-tenant AI Chatbot Platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.add_middleware(SecurityHeadersMiddleware)


@app.on_event("startup")
def on_startup() -> None:
    db_url = make_url(settings.DATABASE_URL)
    logger.info(
        "Config sanity: env=%s db_host=%s cors_origins=%s access_exp_min=%s refresh_exp_days=%s",
        settings.ENV,
        db_url.host or "local",
        len(settings.CORS_ORIGINS),
        settings.JWT_ACCESS_EXP_MINUTES,
        settings.JWT_REFRESH_EXP_DAYS,
    )
    init_db()


# --- Routers ---
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(tenants_router, prefix="/api/v1/tenants", tags=["tenants"])
app.include_router(rag_router, prefix="/api/v1/rag", tags=["rag"])
app.include_router(chat_router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(system_router, prefix="/api/v1/system", tags=["system"])
app.include_router(metrics_router, prefix="/api/v1/system", tags=["system"])
app.include_router(governance_router, prefix="/api/v1/governance", tags=["governance"])
app.include_router(embed_admin_router, prefix="/api/v1/embed", tags=["embed"])
app.include_router(embed_public_router, prefix="/api/v1/public/embed", tags=["public-embed"])
app.include_router(handoff_router, prefix="/api/v1/handoff", tags=["handoff"])
app.include_router(handoff_admin_router, prefix="/api/v1/admin/handoff", tags=["handoff-admin"])
app.include_router(channels_admin_router, prefix="/api/v1/admin/channels", tags=["channels-admin"])
app.include_router(channels_webhook_router, prefix="/api/v1/channels", tags=["channels-webhook"])
app.include_router(tenant_router, prefix="/api/v1/tenant", tags=["tenant"])


# --- System ---
@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
def readiness():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="Database not ready")
    return {"status": "ready"}
