from datetime import datetime

from pydantic import BaseModel, Field


class HandoffCreateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=128)
    destination: str | None = Field(default=None, min_length=1, max_length=255)


class HandoffPatchRequest(BaseModel):
    status: str = Field(min_length=2, max_length=32)
    resolution_note: str | None = Field(default=None, min_length=1, max_length=5000)


class HandoffOut(BaseModel):
    id: str
    tenant_id: str
    conversation_id: str | None
    user_id: str
    source_channel: str
    question: str
    reason: str | None
    status: str
    destination: str | None
    resolution_note: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class HandoffListResponse(BaseModel):
    tenant_id: str
    count: int
    items: list[HandoffOut]
