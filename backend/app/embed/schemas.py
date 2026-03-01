from datetime import datetime

from pydantic import BaseModel, Field


class BotCredentialCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    avatar_url: str | None = Field(default=None, min_length=3, max_length=1024)
    allowed_origins: list[str] = Field(default_factory=list)


class BotCredentialRotateResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    api_key: str
    created_at: datetime


class BotCredentialOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    avatar_url: str | None = None
    allowed_origins: list[str]
    is_active: bool
    created_at: datetime
    rotated_at: datetime | None = None
    last_used_at: datetime | None = None


class BotCredentialPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    avatar_url: str | None = Field(default=None, min_length=3, max_length=1024)
    allowed_origins: list[str] | None = None
    is_active: bool | None = None


class WidgetTokenRequest(BaseModel):
    origin: str = Field(min_length=1, max_length=300)
    session_id: str = Field(min_length=3, max_length=64)


class WidgetTokenResponse(BaseModel):
    token: str
    expires_in_seconds: int
    bot_id: str
    tenant_id: str


class PublicAskRequest(BaseModel):
    widget_token: str = Field(min_length=20)
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    conversation_id: str | None = None
    memory_turns: int = Field(default=8, ge=0, le=40)


class PublicHandoffRequest(BaseModel):
    widget_token: str = Field(min_length=20)
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=128)
    destination: str | None = Field(default=None, min_length=1, max_length=255)


class PublicHandoffResponse(BaseModel):
    handoff_id: str
    tenant_id: str
    status: str
    conversation_id: str | None
