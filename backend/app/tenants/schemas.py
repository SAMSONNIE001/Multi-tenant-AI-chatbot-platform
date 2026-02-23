from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    id: str = Field(min_length=3, max_length=64, description="Tenant ID like t_acme")
    name: str = Field(min_length=2, max_length=255)
    compliance_level: str = Field(default="standard", description="standard|regulated")


class TenantOut(BaseModel):
    id: str
    name: str
    compliance_level: str
