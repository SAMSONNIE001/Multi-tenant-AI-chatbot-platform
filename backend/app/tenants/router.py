from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.models import User
from app.auth.rbac import require_roles
from app.db.session import get_db
from app.tenants.models import Tenant
from app.tenants.schemas import TenantCreate, TenantOut

router = APIRouter()


@router.post("", response_model=TenantOut)
def create_tenant(
    payload: TenantCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("owner", "admin")),
):
    existing = db.get(Tenant, payload.id)
    if existing:
        raise HTTPException(status_code=409, detail="Tenant already exists")

    tenant = Tenant(
        id=payload.id,
        name=payload.name,
        compliance_level=payload.compliance_level,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant
