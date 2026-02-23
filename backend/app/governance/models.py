from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TenantPolicy(Base):
    __tablename__ = "tenant_policies"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
