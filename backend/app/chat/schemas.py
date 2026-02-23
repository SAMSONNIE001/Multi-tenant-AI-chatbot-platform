from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)

    # 8.3 Conversation Memory
    conversation_id: str | None = None
    memory_turns: int = Field(default=8, ge=0, le=40)


class SourceChunk(BaseModel):
    document_id: str
    chunk_id: str
    chunk_index: int
    text: str


class Citation(BaseModel):
    document_id: str
    chunk_id: str
    chunk_index: int | None = None
    score: float | None = None  # populate later if your retriever returns similarity score


class Coverage(BaseModel):
    doc_count: int
    chunk_count: int


class AskResponse(BaseModel):
    tenant_id: str
    user_id: str
    question: str

    # 8.3 Conversation Memory
    conversation_id: str

    answer: str
    citations: list[Citation]
    coverage: Coverage

    # Keep sources for debugging; can be removed later
    sources: list[SourceChunk] = []