import os
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.tenants.models import Tenant
from app.auth.models import User
from app.auth.security import hash_password, create_access_token
from app.system.schemas import BootstrapRequest

router = APIRouter()


@router.post("/bootstrap")
def bootstrap(
    payload: BootstrapRequest,
    db: Session = Depends(get_db),
    x_bootstrap_secret: str | None = Header(default=None, alias="X-Bootstrap-Secret"),
):
    # 1) Must be enabled
    if os.getenv("BOOTSTRAP_ENABLED", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Bootstrap is disabled")

    # 2) Must provide correct secret
    expected = os.getenv("BOOTSTRAP_SECRET")
    if not expected or x_bootstrap_secret != expected:
        raise HTTPException(status_code=401, detail="Invalid bootstrap secret")

    # 3) Only allowed if database is empty (no tenants)
    tenants_exist = db.query(Tenant).first() is not None
    if tenants_exist:
        raise HTTPException(status_code=409, detail="Bootstrap already completed")

    tenant_id = payload.tenant_id
    tenant_name = payload.tenant_name
    compliance_level = payload.compliance_level
    admin_id = payload.admin_id
    admin_email = str(payload.admin_email).lower()
    admin_password = payload.admin_password

    # Create tenant
    tenant = Tenant(id=tenant_id, name=tenant_name, compliance_level=compliance_level)
    db.add(tenant)
    db.flush()

    # Create admin user
    user = User(
        id=admin_id,
        tenant_id=tenant_id,
        email=admin_email,
        password_hash=hash_password(admin_password),
        role="admin",
    )
    db.add(user)
    db.commit()

    token = create_access_token(
        {"sub": user.id, "tenant_id": user.tenant_id, "role": user.role, "email": user.email}
    )

    return {
        "tenant": {"id": tenant.id, "name": tenant.name, "compliance_level": tenant.compliance_level},
        "admin": {"id": user.id, "tenant_id": user.tenant_id, "email": user.email, "role": user.role},
        "access_token": token,
        "token_type": "bearer",
    }
