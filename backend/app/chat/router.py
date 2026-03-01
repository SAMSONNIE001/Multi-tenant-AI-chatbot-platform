
from time import perf_counter
import re

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
from app.system.usage_service import check_tenant_quota, write_usage_event

# 8.2 policy guardrails
from app.governance.policy_engine import evaluate_question_policy
from app.governance.doc_policy import evaluate_doc_policy
from app.handoff.service import create_handoff_request

router = APIRouter()

_HUMAN_INTENT_RE = re.compile(
    r"\b(human|agent|representative|live agent|support team|talk to .*human|speak to .*human)\b",
    re.IGNORECASE,
)


def _compact_grounded_text(text: str, max_len: int = 260) -> str:
    """Keep grounded fallback concise so widget replies are readable."""
    cleaned = " ".join((text or "").split()).strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


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
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> AskResponse:
        latency_ms = int((perf_counter() - started_at) * 1000)
        channel = "embed" if str(current_user.id).startswith("w_") else "api"

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
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            policy_reason=policy_reason,
            retrieval_doc_count=retrieval_doc_count,
            retrieval_chunk_count=retrieval_chunk_count,
        )
        write_usage_event(
            db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            channel=channel,
            refused=refused,
            total_tokens=int(total_tokens or 0),
            latency_ms=latency_ms,
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
            total_tokens=0,
        )

    quota_ok, quota_reason, _ = check_tenant_quota(
        db=db,
        tenant_id=current_user.tenant_id,
    )
    if not quota_ok:
        answer = "Usage limit reached for this tenant plan. Please contact support."
        return _respond_and_log(
            answer=answer,
            refused=True,
            policy_reason=quota_reason,
            retrieved_chunks=[],
            citations_json=[],
            retrieval_doc_count=0,
            retrieval_chunk_count=0,
            coverage=Coverage(doc_count=0, chunk_count=0),
            citations=[],
            sources=[],
            total_tokens=0,
        )

    # Auto-handoff: detect human-agent intent from normal user messages.
    if _HUMAN_INTENT_RE.search(payload.question or ""):
        handoff = create_handoff_request(
            db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            question=payload.question,
            conversation_id=conversation.id,
            reason="human_requested",
            destination=None,
            source_channel=("embed" if str(current_user.id).startswith("w_") else "api"),
        )
        answer = (
            "I have connected you to our support team. "
            f"Please hold while an agent takes over. Ticket ID: {handoff.id}"
        )
        return _respond_and_log(
            answer=answer,
            refused=False,
            policy_reason="handoff:auto_intent_detected",
            retrieved_chunks=[],
            citations_json=[],
            retrieval_doc_count=0,
            retrieval_chunk_count=0,
            coverage=Coverage(doc_count=0, chunk_count=0),
            citations=[],
            sources=[],
            total_tokens=0,
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
            total_tokens=0,
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
            total_tokens=0,
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
            total_tokens=0,
        )

    # ------------------------------------------------------------------
    # LLM answer (doc-only)
    # ------------------------------------------------------------------
    user_prompt = build_user_prompt(payload.question, chunks, messages=history_messages)
    answer, prompt_tokens, completion_tokens, total_tokens = generate_answer(
        SYSTEM_PROMPT,
        user_prompt,
    )
    answer = answer.strip()
    if len(answer) > 450:
        answer = REFUSAL_SENTENCE

    # ------------------------------------------------------------------
    # 8.1 Citation validation
    # ------------------------------------------------------------------
    ok, citation_keys = validate_citations(answer, chunks)
    citation_fallback_used = False
    if not ok:
        if chunks:
            top = chunks[0]

            # Case 1: model gave a useful answer but missed citation format.
            # Keep the answer and attach a valid citation instead of replacing
            # it with raw chunk text.
            if answer and answer != REFUSAL_SENTENCE and not citation_keys:
                answer = f"{answer.rstrip()} [{top.document_id}:{top.id}]"
                citation_keys = [
                    Citation(
                        document_id=top.document_id,
                        chunk_id=top.id,
                        chunk_index=top.chunk_index,
                        score=None,
                    )
                ]
                citation_fallback_used = True
            else:
                # Case 2: invalid citation or empty answer -> safe refusal.
                # Never dump raw chunk text to end users.
                answer = REFUSAL_SENTENCE
                citation_keys = []
        else:
            answer = REFUSAL_SENTENCE
            citation_keys = []

    # Build citation objects from retrieved chunks
    chunk_map = {(c.document_id, c.id): c for c in chunks}
    citations_out: list[Citation] = []
    if citation_keys and isinstance(citation_keys[0], Citation):
        citations_out = citation_keys  # already normalized from fallback block above
    else:
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
        policy_reason=(
            "citation_validation:fallback_top_chunk"
            if citation_fallback_used
            else ("citation_validation:failed" if not ok else None)
        ),
        retrieved_chunks=retrieved_chunks,
        citations_json=citations_json,
        retrieval_doc_count=coverage.doc_count,
        retrieval_chunk_count=coverage.chunk_count,
        coverage=coverage,
        citations=citations_out,
        sources=sources,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
