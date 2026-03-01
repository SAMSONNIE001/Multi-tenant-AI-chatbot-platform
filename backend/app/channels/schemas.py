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


class CustomerChannelHandleOut(BaseModel):
    id: str
    channel_type: str
    external_user_id: str
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CustomerProfileOut(BaseModel):
    id: str
    tenant_id: str
    display_name: str | None = None
    created_at: datetime
    updated_at: datetime
    conversation_count: int = 0
    handoff_count: int = 0
    handles: list[CustomerChannelHandleOut] = Field(default_factory=list)


class CustomerProfilesResponse(BaseModel):
    tenant_id: str
    profiles: list[CustomerProfileOut]


class CustomerProfileMergeRequest(BaseModel):
    source_profile_id: str = Field(min_length=3, max_length=64)
    target_profile_id: str = Field(min_length=3, max_length=64)


class CustomerProfileMergeResponse(BaseModel):
    tenant_id: str
    source_profile_id: str
    target_profile_id: str
    moved_handles: int
    deduped_handles: int
    moved_conversations: int
    moved_handoffs: int
