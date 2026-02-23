from pydantic import BaseModel, EmailStr, Field


class BootstrapRequest(BaseModel):
    tenant_id: str = Field(min_length=3, max_length=64, description="Tenant ID like t_acme")
    tenant_name: str = Field(min_length=2, max_length=255)
    compliance_level: str = Field(default="standard", description="standard|regulated")
    admin_id: str = Field(min_length=3, max_length=64, description="Admin user ID like u_admin")
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=72)
