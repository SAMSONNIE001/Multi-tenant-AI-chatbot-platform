import secrets
from sqlalchemy.orm import Session

from app.audit.models import ChatAuditLog


def write_chat_audit_log(
    db: Session,
    tenant_id: str,
    user_id: str,
    question: str,
    answer: str,
    retrieved_chunks: list,
    citations: list,
    refused: bool,
    model: str | None = None,
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    policy_reason: str | None = None,
    retrieval_doc_count: int | None = None,
    retrieval_chunk_count: int | None = None,
) -> None:
    log = ChatAuditLog(
        id=f"al_{secrets.token_hex(12)}",
        tenant_id=tenant_id,
        user_id=user_id,
        question=question,
        answer=answer,
        retrieved_chunks=retrieved_chunks,
        citations=citations,
        refused=refused,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        policy_reason=policy_reason,
        retrieval_doc_count=retrieval_doc_count,
        retrieval_chunk_count=retrieval_chunk_count,
    )
    db.add(log)
    db.commit()
