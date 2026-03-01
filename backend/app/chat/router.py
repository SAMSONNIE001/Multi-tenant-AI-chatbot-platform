
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
from app.chat.prompting import SYSTEM_PROMPT, build_user_prompt, extract_preferred_name
from app.chat.citations import validate_citations, REFUSAL_SENTENCE, is_refusal

from app.rag.service import search_chunks
from app.rag.models import Document
from app.tenants.models import Tenant

from app.audit.service import write_chat_audit_log
from app.system.rate_limit import check_rate_limit
from app.system.usage_service import check_tenant_quota, write_usage_event

# 8.2 policy guardrails
from app.governance.policy_engine import evaluate_question_policy
from app.governance.doc_policy import evaluate_doc_policy
from app.handoff.service import create_handoff_request

router = APIRouter()

_HUMAN_INTENT_RE = re.compile(
    r"("  # broad handoff intent phrases
    r"\b(speak|talk|chat|connect|transfer|escalate)\b.{0,32}\b"
    r"(human|person|someone|agent|representative|support|customer service|help desk)\b"
    r"|"
    r"\b(customer service|support team|help desk|live agent|real person|human agent)\b"
    r"|"
    r"\b(can i|i want to|i need to|let me|please)\b.{0,32}\b"
    r"(speak|talk|chat|connect|transfer|escalate)\b.{0,32}\b"
    r"(to|with)?\b.{0,12}\b(human|person|someone|agent|representative)\b"
    r")",
    re.IGNORECASE,
)

_HUMAN_INTENT_KEYWORDS = (
    "customer service",
    "human support",
    "live support",
    "live chat agent",
    "talk to support",
    "speak to support",
    "connect me to support",
    "transfer me",
    "escalate this",
    "real person",
    "someone from your team",
)

_HUMAN_FALSE_POSITIVES = (
    "human resources",
    "hr policy",
    "human rights",
)

_GREETING_RE = re.compile(r"^\s*(hi|hello|hey|good morning|good afternoon|good evening)\b", re.IGNORECASE)
_THANKS_RE = re.compile(r"\b(thanks|thank you|thx|ty)\b", re.IGNORECASE)
_BYE_RE = re.compile(r"\b(bye|goodbye|see you|talk later)\b", re.IGNORECASE)
_NAME_DIRECT_PATTERNS = (
    re.compile(r"\bmy name is\s+([A-Za-z][A-Za-z '\-]{1,40})\b", re.IGNORECASE),
    re.compile(r"\bi am\s+([A-Za-z][A-Za-z '\-]{1,40})\b", re.IGNORECASE),
    re.compile(r"\bi'm\s+([A-Za-z][A-Za-z '\-]{1,40})\b", re.IGNORECASE),
    re.compile(r"\bcall me\s+([A-Za-z][A-Za-z '\-]{1,40})\b", re.IGNORECASE),
    re.compile(r"\bit's\s+([A-Za-z][A-Za-z '\-]{1,40})\b", re.IGNORECASE),
    re.compile(r"\bthis is\s+([A-Za-z][A-Za-z '\-]{1,40})\b", re.IGNORECASE),
)


def _is_human_handoff_intent(question: str) -> bool:
    q = (question or "").strip().lower()
    if not q:
        return False
    if any(fp in q for fp in _HUMAN_FALSE_POSITIVES):
        return False
    if _HUMAN_INTENT_RE.search(q):
        return True
    return any(k in q for k in _HUMAN_INTENT_KEYWORDS)


def _normalize_name(name: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", (name or "").strip())
    if not (2 <= len(cleaned) <= 40):
        return None
    return cleaned


def _extract_name_from_text(question: str) -> str | None:
    text = (question or "").strip()
    if not text:
        return None
    for pat in _NAME_DIRECT_PATTERNS:
        hit = pat.search(text)
        if hit:
            return _normalize_name(hit.group(1))
    return None


def _is_probable_name_only_reply(question: str) -> str | None:
    text = (question or "").strip()
    if not text:
        return None
    if len(text) > 40:
        return None

    # Names should be short (1-3 words), not full sentences/questions.
    words = text.split()
    if not (1 <= len(words) <= 3):
        return None
    if any(ch in text for ch in "?!,:;./\\"):
        return None

    lowered = text.lower()
    forbidden_tokens = {
        # question words / common support terms that are not names
        "how", "what", "why", "when", "where", "who", "can", "could", "would", "should",
        "password", "login", "account", "billing", "support", "help", "reset", "change",
        "human", "agent", "person", "service", "customer", "issue", "problem",
        # common sentence glue that usually indicates phrase, not name
        "my", "name", "is", "i", "am", "to", "the", "a", "an", "do", "does",
    }
    if any(token in forbidden_tokens for token in lowered.split()):
        return None

    # Accept letters with optional apostrophe/hyphen, e.g. O'Neil, Anne-Marie.
    if re.fullmatch(r"[A-Za-z][A-Za-z'\- ]{1,39}", text):
        return _normalize_name(text)
    return None


def _small_talk_response(
    question: str,
    preferred_name: str | None,
    *,
    company_name: str,
    bot_name: str,
) -> str | None:
    q = (question or "").strip()
    if not q:
        return None
    name_part = f" {preferred_name}" if preferred_name else ""
    if _GREETING_RE.search(q):
        if preferred_name:
            return (
                f"Hi{name_part}, welcome to {company_name}. "
                f"I'm {bot_name}. I can help with anything. What can I do for you today?"
            )
        return (
            f"Welcome to {company_name}. I'm {bot_name}. "
            "Before we start, what name should I call you?"
        )
    if _THANKS_RE.search(q):
        return f"You are welcome{name_part}. If you need anything else, I am here to help."
    if _BYE_RE.search(q):
        return f"Got it{name_part}. If you need help again, just send a message."
    return None


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
    preferred_name = extract_preferred_name(history_messages)
    direct_name = _extract_name_from_text(payload.question)
    if direct_name:
        preferred_name = direct_name
    company_name = (
        str(getattr(current_user, "tenant_name", "") or "").strip()
        or str(
            db.execute(select(Tenant.name).where(Tenant.id == current_user.tenant_id)).scalar_one_or_none()
            or "our company"
        ).strip()
    )
    bot_name = str(getattr(current_user, "bot_display_name", "") or "").strip() or "AI Assistant"

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

    # If an agent has taken over this conversation, pause AI replies.
    if bool(getattr(conversation, "ai_paused", False)):
        return _respond_and_log(
            answer=(
                "A support agent is currently handling this conversation. "
                "Please hold while we connect you."
            ),
            refused=False,
            policy_reason="handoff:ai_paused",
            retrieved_chunks=[],
            citations_json=[],
            retrieval_doc_count=0,
            retrieval_chunk_count=0,
            coverage=Coverage(doc_count=0, chunk_count=0),
            citations=[],
            sources=[],
            total_tokens=0,
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

    # If name is provided explicitly, acknowledge and continue naturally.
    if direct_name:
        return _respond_and_log(
            answer=(
                f"Great to meet you, {direct_name}. "
                f"Welcome to {company_name}. I'm {bot_name}. What do you need help with today?"
            ),
            refused=False,
            policy_reason="conversation:name_captured",
            retrieved_chunks=[],
            citations_json=[],
            retrieval_doc_count=0,
            retrieval_chunk_count=0,
            coverage=Coverage(doc_count=0, chunk_count=0),
            citations=[],
            sources=[],
            total_tokens=0,
        )

    # If we just asked for name, accept short name-only replies.
    last_assistant = next((m for m in reversed(history_messages) if m.role == "assistant"), None)
    asked_for_name = bool(
        last_assistant
        and "what name should i call you" in (last_assistant.content or "").lower()
    )
    if not preferred_name and asked_for_name:
        maybe_name = _is_probable_name_only_reply(payload.question)
        if maybe_name:
            return _respond_and_log(
                answer=f"Nice to meet you, {maybe_name}. How can I help you today?",
                refused=False,
                policy_reason="conversation:name_reply_captured",
                retrieved_chunks=[],
                citations_json=[],
                retrieval_doc_count=0,
                retrieval_chunk_count=0,
                coverage=Coverage(doc_count=0, chunk_count=0),
                citations=[],
                sources=[],
                total_tokens=0,
            )

    # Conversational small-talk that does not require document grounding.
    small_talk = _small_talk_response(
        payload.question,
        preferred_name,
        company_name=company_name,
        bot_name=bot_name,
    )
    if small_talk:
        return _respond_and_log(
            answer=small_talk,
            refused=False,
            policy_reason="conversation:small_talk",
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
    if _is_human_handoff_intent(payload.question):
        handoff = create_handoff_request(
            db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            question=payload.question,
            conversation_id=conversation.id,
            reason="human_requested",
            destination=None,
            source_channel=source_channel,
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
    source_channel = str(getattr(current_user, "source_channel", "") or "").strip().lower() or "api"
