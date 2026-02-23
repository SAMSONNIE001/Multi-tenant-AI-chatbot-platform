from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentPatchRequest(BaseModel):
    visibility: str | None = Field(default=None, min_length=1, max_length=32)
    tags: list[str] | None = None


class DocumentAdminOut(BaseModel):
    id: str
    filename: str
    visibility: str
    tags: list[str]
    created_at: datetime
    chunk_count: int | None = None


class DocumentsListResponse(BaseModel):
    tenant_id: str
    documents: list[DocumentAdminOut]


class DocumentDeleteResponse(BaseModel):
    deleted: bool
    document_id: str


class PolicyPutRequest(BaseModel):
    policy: dict[str, Any]


class PolicyResponse(BaseModel):
    tenant_id: str
    policy: dict[str, Any]


class PolicyGeneratedResponse(BaseModel):
    tenant_id: str
    document_id: str
    policy: dict[str, Any]


class RetentionConfig(BaseModel):
    audit_days: int = Field(default=90, ge=1, le=3650)
    messages_days: int = Field(default=30, ge=1, le=3650)


class RetentionResponse(BaseModel):
    tenant_id: str
    retention: RetentionConfig


class ConversationAdminOut(BaseModel):
    id: str
    user_id: str
    created_at: datetime
    last_activity_at: datetime
    message_count: int


class ConversationsListResponse(BaseModel):
    tenant_id: str
    conversations: list[ConversationAdminOut]


class MessageAdminOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class ConversationMessagesResponse(BaseModel):
    tenant_id: str
    conversation_id: str
    messages: list[MessageAdminOut]


class AuditReasonCount(BaseModel):
    reason: str
    count: int


class AuditSummary(BaseModel):
    total_requests: int
    refused_requests: int
    refusal_rate: float
    avg_latency_ms: float | None = None
    top_refused_reasons: list[AuditReasonCount]


class AuditLogEntryOut(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    question: str
    answer: str
    retrieved_chunks: list[Any]
    citations: list[Any]
    refused: bool
    model: str | None = None
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    policy_reason: str | None = None
    retrieval_doc_count: int | None = None
    retrieval_chunk_count: int | None = None
    created_at: datetime


class AuditListResponse(BaseModel):
    tenant_id: str
    window_hours: int
    filters: dict[str, bool]
    summary: AuditSummary
    entries: list[AuditLogEntryOut]
