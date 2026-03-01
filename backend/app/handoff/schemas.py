from datetime import datetime

from pydantic import BaseModel, Field


class HandoffCreateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=128)
    destination: str | None = Field(default=None, min_length=1, max_length=255)


class HandoffPatchRequest(BaseModel):
    status: str | None = Field(default=None, min_length=2, max_length=32)
    assigned_to_user_id: str | None = Field(default=None, min_length=3, max_length=64)
    priority: str | None = Field(default=None, min_length=2, max_length=16)
    resolution_note: str | None = Field(default=None, min_length=1, max_length=5000)
    internal_note_append: str | None = Field(default=None, min_length=1, max_length=2000)


class HandoffClaimRequest(BaseModel):
    assigned_to_user_id: str | None = Field(default=None, min_length=3, max_length=64)


class HandoffAgentReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    mark_pending_customer: bool = True


class HandoffAIToggleRequest(BaseModel):
    ai_paused: bool


class HandoffOut(BaseModel):
    id: str
    tenant_id: str
    conversation_id: str | None
    user_id: str
    source_channel: str
    question: str
    reason: str | None
    status: str
    assigned_to_user_id: str | None
    priority: str
    destination: str | None
    resolution_note: str | None
    internal_notes: str | None
    first_response_due_at: datetime | None
    first_responded_at: datetime | None
    resolution_due_at: datetime | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None


class HandoffListResponse(BaseModel):
    tenant_id: str
    count: int
    items: list[HandoffOut]


class HandoffNoteCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class HandoffNoteOut(BaseModel):
    id: str
    handoff_id: str
    tenant_id: str
    author_user_id: str
    content: str
    created_at: datetime


class HandoffNotesResponse(BaseModel):
    tenant_id: str
    handoff_id: str
    count: int
    items: list[HandoffNoteOut]


class HandoffWindowMetrics(BaseModel):
    window_hours: int
    total_tickets: int
    breached_tickets: int
    breach_rate: float
    avg_first_response_min: float | None = None
    avg_resolution_min: float | None = None


class HandoffAgentMetric(BaseModel):
    agent_user_id: str
    assigned_count: int
    resolved_count: int


class HandoffDailyMetric(BaseModel):
    day: str
    tickets: int
    breached_tickets: int
    breach_rate: float


class HandoffTotalsMetric(BaseModel):
    all_tickets: int
    resolved_tickets: int
    unresolved_tickets: int
    resolved_rate: float


class HandoffMetricsResponse(BaseModel):
    tenant_id: str
    as_of: datetime
    window_24h: HandoffWindowMetrics
    window_7d: HandoffWindowMetrics
    by_agent: list[HandoffAgentMetric]
    daily: list[HandoffDailyMetric]
    totals: HandoffTotalsMetric
