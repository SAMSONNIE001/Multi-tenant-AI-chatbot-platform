from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    filename: str
    content_type: str


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    chunk_index: int
    text: str


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class QueryResultChunk(BaseModel):
    document_id: str
    chunk_index: int
    text: str


class QueryResponse(BaseModel):
    tenant_id: str
    question: str
    results: list[QueryResultChunk]
