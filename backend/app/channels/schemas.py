from datetime import datetime

from pydantic import BaseModel, Field


class ChannelAccountCreateRequest(BaseModel):
    channel_type: str = Field(min_length=3, max_length=32)
    name: str = Field(min_length=2, max_length=255)

    access_token: str = Field(min_length=8, max_length=4000)
    app_secret: str | None = Field(default=None, min_length=8, max_length=255)
    verify_token: str | None = Field(default=None, min_length=8, max_length=255)

    phone_number_id: str | None = Field(default=None, min_length=3, max_length=128)
    page_id: str | None = Field(default=None, min_length=3, max_length=128)
    instagram_account_id: str | None = Field(default=None, min_length=3, max_length=128)
    metadata_json: dict = Field(default_factory=dict)


class ChannelAccountPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    access_token: str | None = Field(default=None, min_length=8, max_length=4000)
    app_secret: str | None = Field(default=None, min_length=8, max_length=255)

    phone_number_id: str | None = Field(default=None, min_length=3, max_length=128)
    page_id: str | None = Field(default=None, min_length=3, max_length=128)
    instagram_account_id: str | None = Field(default=None, min_length=3, max_length=128)

    metadata_json: dict | None = None
    is_active: bool | None = None


class ChannelAccountOut(BaseModel):
    id: str
    tenant_id: str
    channel_type: str
    name: str

    verify_token: str
    has_app_secret: bool
    has_access_token: bool

    phone_number_id: str | None = None
    page_id: str | None = None
    instagram_account_id: str | None = None
    metadata_json: dict

    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None
    last_webhook_at: datetime | None = None
    last_outbound_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None


class ChannelAccountRotateTokenResponse(BaseModel):
    id: str
    verify_token: str


class MetaWebhookResponse(BaseModel):
    received: bool
    processed_messages: int
    ignored_events: int


class ChannelAccountHealthOut(BaseModel):
    id: str
    tenant_id: str
    channel_type: str
    is_active: bool
    status: str
    last_webhook_at: datetime | None = None
    last_outbound_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
