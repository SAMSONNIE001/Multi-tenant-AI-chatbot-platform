import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.system.usage_models import TenantUsageEvent, TenantUsageLimit

DEFAULT_DAILY_REQUEST_LIMIT = 1000
DEFAULT_MONTHLY_TOKEN_LIMIT = 1_000_000


def _window_start_day(now: datetime | None = None) -> datetime:
    current = now or datetime.utcnow()
    return datetime(current.year, current.month, current.day)


def _window_start_month(now: datetime | None = None) -> datetime:
    current = now or datetime.utcnow()
    return datetime(current.year, current.month, 1)


def get_or_create_tenant_limit(db: Session, tenant_id: str) -> TenantUsageLimit:
    row = db.get(TenantUsageLimit, tenant_id)
    if row:
        return row

    row = TenantUsageLimit(
        tenant_id=tenant_id,
        daily_request_limit=DEFAULT_DAILY_REQUEST_LIMIT,
        monthly_token_limit=DEFAULT_MONTHLY_TOKEN_LIMIT,
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def check_tenant_quota(db: Session, tenant_id: str) -> tuple[bool, str | None, dict[str, int]]:
    now = datetime.utcnow()
    limits = get_or_create_tenant_limit(db, tenant_id)

    day_start = _window_start_day(now)
    month_start = _window_start_month(now)

    requests_today = db.execute(
        select(func.count(TenantUsageEvent.id)).where(
            TenantUsageEvent.tenant_id == tenant_id,
            TenantUsageEvent.created_at >= day_start,
        )
    ).scalar_one()

    tokens_month = db.execute(
        select(func.coalesce(func.sum(TenantUsageEvent.total_tokens), 0)).where(
            TenantUsageEvent.tenant_id == tenant_id,
            TenantUsageEvent.created_at >= month_start,
        )
    ).scalar_one()

    usage = {
        "requests_today": int(requests_today or 0),
        "tokens_month": int(tokens_month or 0),
        "daily_request_limit": int(limits.daily_request_limit),
        "monthly_token_limit": int(limits.monthly_token_limit),
    }

    if usage["requests_today"] >= usage["daily_request_limit"]:
        return False, "quota:daily_requests", usage

    if usage["tokens_month"] >= usage["monthly_token_limit"]:
        return False, "quota:monthly_tokens", usage

    return True, None, usage


def write_usage_event(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    channel: str,
    refused: bool,
    total_tokens: int,
    latency_ms: int | None,
) -> None:
    row = TenantUsageEvent(
        id=f"ue_{secrets.token_hex(12)}",
        tenant_id=tenant_id,
        user_id=user_id,
        channel=channel,
        refused=bool(refused),
        total_tokens=max(0, int(total_tokens or 0)),
        latency_ms=latency_ms,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()


def usage_summary(db: Session, *, tenant_id: str, since_days: int) -> dict:
    since = datetime.utcnow() - timedelta(days=max(1, int(since_days)))

    totals = db.execute(
        select(
            func.count(TenantUsageEvent.id),
            func.coalesce(func.sum(TenantUsageEvent.total_tokens), 0),
            func.avg(TenantUsageEvent.latency_ms),
        ).where(
            TenantUsageEvent.tenant_id == tenant_id,
            TenantUsageEvent.created_at >= since,
        )
    ).one()

    refused_count = db.execute(
        select(func.count(TenantUsageEvent.id)).where(
            TenantUsageEvent.tenant_id == tenant_id,
            TenantUsageEvent.created_at >= since,
            TenantUsageEvent.refused.is_(True),
        )
    ).scalar_one()

    channel_rows = db.execute(
        select(TenantUsageEvent.channel, func.count(TenantUsageEvent.id))
        .where(
            TenantUsageEvent.tenant_id == tenant_id,
            TenantUsageEvent.created_at >= since,
        )
        .group_by(TenantUsageEvent.channel)
    ).all()

    return {
        "window_days": max(1, int(since_days)),
        "total_requests": int(totals[0] or 0),
        "total_tokens": int(totals[1] or 0),
        "avg_latency_ms": float(totals[2]) if totals[2] is not None else None,
        "refused_requests": int(refused_count or 0),
        "by_channel": [{"channel": c, "count": int(n)} for c, n in channel_rows],
    }
