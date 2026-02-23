
from time import perf_counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.auth.deps import get_current_user
from app.auth.models import User
from app.db.session import get_db

from app.chat.schemas import AskRequest, AskResponse, SourceChunk, Citation, Coverage
from app.chat.llm import CHAT_MODEL, generate_answer
from app.chat.memory_service import (
    append_message,
    fetch_recent_messages,
    get_or_create_conversation,
    touch_conversation,
)
from app.chat.prompting import SYSTEM_PROMPT, build_user_prompt
from app.chat.citations import validate_citations, REFUSAL_SENTENCE, is_refusal

from app.rag.service import search_chunks
from app.rag.models import Document

from app.audit.service import write_chat_audit_log
from app.system.rate_limit import check_rate_limit

# 8.2 policy guardrails
from app.governance.policy_engine import evaluate_question_policy
from app.governance.doc_policy import evaluate_doc_policy

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    started_at = perf_counter()

    conversation = get_or_create_conversation(
        db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        conversation_id=payload.conversation_id,
    )
    history_messages = fetch_recent_messages(
        db,
        conversation_id=conversation.id,
        limit=payload.memory_turns,
    )

    def _respond_and_log(
        *,
        answer: str,
        refused: bool,
        policy_reason: str | None,
        retrieved_chunks: list[dict],
        citations_json: list[dict],
        retrieval_doc_count: int,
        retrieval_chunk_count: int,
        coverage: Coverage,
        citations: list[Citation],
        sources: list[SourceChunk],
    ) -> AskResponse:
        latency_ms = int((perf_counter() - started_at) * 1000)

        append_message(
            db,
            conversation_id=conversation.id,
            role="user",
            content=payload.question,
        )
        append_message(
            db,
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
        )
        touch_conversation(db, conversation=conversation)

        write_chat_audit_log(
            db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            question=payload.question,
            answer=answer,
            retrieved_chunks=retrieved_chunks,
            citations=citations_json,
            refused=refused,
            model=CHAT_MODEL,
            latency_ms=latency_ms,
            policy_reason=policy_reason,
            retrieval_doc_count=retrieval_doc_count,
            retrieval_chunk_count=retrieval_chunk_count,
        )

        return AskResponse(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            question=payload.question,
            conversation_id=conversation.id,
            answer=answer,
            citations=citations,
            coverage=coverage,
            sources=sources,
        )

    allowed, rate_reason = check_rate_limit(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    if not allowed:
        answer = "Rate limit exceeded. Please retry shortly."
        return _respond_and_log(
            answer=answer,
            refused=True,
            policy_reason=rate_reason,
            retrieved_chunks=[],
            citations_json=[],
            retrieval_doc_count=0,
            retrieval_chunk_count=0,
            coverage=Coverage(doc_count=0, chunk_count=0),
            citations=[],
            sources=[],
        )

    # ------------------------------------------------------------------
    # 8.2.2 Question-based policy guardrails (PRE-retrieval)
    # ------------------------------------------------------------------
    policy = evaluate_question_policy(db, tenant_id=current_user.tenant_id, question=payload.question)
    if policy.action == "refuse":
        answer = policy.message or "Request refused by policy."
        return _respond_and_log(
            answer=answer,
            refused=True,
            policy_reason=policy.reason,
            retrieved_chunks=[],
            citations_json=[],
            retrieval_doc_count=0,
            retrieval_chunk_count=0,
            coverage=Coverage(doc_count=0, chunk_count=0),
            citations=[],
            sources=[],
        )

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    chunks = search_chunks(
        db=db,
        tenant_id=current_user.tenant_id,
        question=payload.question,
        top_k=payload.top_k,
    )

    # Refuse immediately if no context
    if not chunks:
        answer = REFUSAL_SENTENCE
        return _respond_and_log(
            answer=answer,
            refused=True,
            policy_reason="retrieval:no_context",
            retrieved_chunks=[],
            citations_json=[],
            retrieval_doc_count=0,
            retrieval_chunk_count=0,
            coverage=Coverage(doc_count=0, chunk_count=0),
            citations=[],
            sources=[],
        )

    # ------------------------------------------------------------------
    # 8.2.3 Document-based policy hook (POST-retrieval, PRE-LLM)
    # ------------------------------------------------------------------
    doc_ids = list({c.document_id for c in chunks})
    documents = (
        db.execute(
            select(Document).where(
                Document.id.in_(doc_ids),
                Document.tenant_id == current_user.tenant_id,
            )
        )
        .scalars()
        .all()
    )

    doc_policy = evaluate_doc_policy(documents=documents, current_user=current_user)
    if doc_policy.action == "refuse":
        answer = doc_policy.message or "Request refused by document access policy."
        retrieved_chunks = [
            {
                "document_id": c.document_id,
                "chunk_id": c.id,
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ]
        return _respond_and_log(
            answer=answer,
            refused=True,
            policy_reason=doc_policy.reason,
            retrieved_chunks=retrieved_chunks,
            citations_json=[],
            retrieval_doc_count=len({c.document_id for c in chunks}),
            retrieval_chunk_count=len(chunks),
            coverage=Coverage(
                doc_count=len({c.document_id for c in chunks}),
                chunk_count=len(chunks),
            ),
            citations=[],
            sources=[],
        )

    # ------------------------------------------------------------------
    # LLM answer (doc-only)
    # ------------------------------------------------------------------
    user_prompt = build_user_prompt(payload.question, chunks, messages=history_messages)
    answer = generate_answer(SYSTEM_PROMPT, user_prompt).strip()

    # ------------------------------------------------------------------
    # 8.1 Citation validation
    # ------------------------------------------------------------------
    ok, citation_keys = validate_citations(answer, chunks)
    if not ok:
        answer = REFUSAL_SENTENCE
        citation_keys = []

    # Build citation objects from retrieved chunks
    chunk_map = {(c.document_id, c.id): c for c in chunks}
    citations_out: list[Citation] = []

    for k in citation_keys:
        c = chunk_map.get((k.document_id, k.chunk_id))
        if c:
            citations_out.append(
                Citation(
                    document_id=c.document_id,
                    chunk_id=c.id,
                    chunk_index=c.chunk_index,
                    score=None,
                )
            )

    # Coverage
    coverage = Coverage(
        doc_count=len({c.document_id for c in chunks}),
        chunk_count=len(chunks),
    )

    # Audit log (store IDs only)
    retrieved_chunks = [
        {
            "document_id": c.document_id,
            "chunk_id": c.id,
            "chunk_index": c.chunk_index,
        }
        for c in chunks
    ]
    citations_json = [
        {
            "document_id": c.document_id,
            "chunk_id": c.chunk_id,
            "chunk_index": c.chunk_index,
        }
        for c in citations_out
    ]

    sources = [
        SourceChunk(
            document_id=c.document_id,
            chunk_id=c.id,
            chunk_index=c.chunk_index,
            text=c.text,
        )
        for c in chunks
    ]

    return _respond_and_log(
        answer=answer,
        refused=is_refusal(answer),
        policy_reason="citation_validation:failed" if not ok else None,
        retrieved_chunks=retrieved_chunks,
        citations_json=citations_json,
        retrieval_doc_count=coverage.doc_count,
        retrieval_chunk_count=coverage.chunk_count,
        coverage=coverage,
        citations=citations_out,
        sources=sources,
    )
