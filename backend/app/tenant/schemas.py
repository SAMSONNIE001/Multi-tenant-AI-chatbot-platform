from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class TenantOnboardRequest(BaseModel):
    tenant_id: str | None = Field(default=None, min_length=3, max_length=64)
    tenant_name: str = Field(min_length=2, max_length=255)
    compliance_level: str = Field(default="standard", min_length=2, max_length=32)
    admin_id: str | None = Field(default=None, min_length=3, max_length=64)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=72)
    bot_name: str = Field(default="Main Website Bot", min_length=2, max_length=255)
    allowed_origins: list[str] = Field(default_factory=list)


class TenantAdminOut(BaseModel):
    id: str
    tenant_id: str
    email: EmailStr
    role: str


class TenantOut(BaseModel):
    id: str
    name: str
    compliance_level: str


class TenantOnboardResponse(BaseModel):
    tenant: TenantOut
    admin: TenantAdminOut
    bot_id: str
    bot_api_key: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TenantKnowledgeUploadResponse(BaseModel):
    document_id: str
    tenant_id: str
    filename: str
    content_type: str
    chunk_count: int


class TenantKnowledgeReindexRequest(BaseModel):
    document_id: str | None = Field(default=None, min_length=3, max_length=64)


class TenantKnowledgeReindexResponse(BaseModel):
    tenant_id: str
    document_id: str | None = None
    chunks_reindexed: int
    openai_enabled: bool
    status: str


class TenantKnowledgeStatusResponse(BaseModel):
    tenant_id: str
    document_count: int
    chunk_count: int
    latest_document_id: str | None = None
    latest_document_at: datetime | None = None


class TenantEmbedSnippetResponse(BaseModel):
    tenant_id: str
    bot_id: str
    api_base: str
    snippet_html: str
