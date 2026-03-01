from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    compliance_level: Mapped[str] = mapped_column(String(32), nullable=False, default="standard")
