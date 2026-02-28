from typing import Sequence
import re

from app.rag.models import Chunk

REFUSAL_SENTENCE = "I don't have that information in the provided documents."

SYSTEM_PROMPT = f"""You are a governance-first assistant for a single tenant.

Hard rules (must follow exactly):
1) Use ONLY the provided tenant knowledge chunks as your source of truth.
2) Include at least one citation for every answer with factual content in this exact format: [document_id:chunk_id]
3) If the answer is not present in the chunks, respond exactly:
{REFUSAL_SENTENCE}
4) Do NOT guess. Do NOT use outside knowledge. Do NOT invent citations.
5) Conversation history is only context; it is NOT a source of truth. Do not cite history.
6) If conversation history provides user's preferred name, use it naturally.
7) Keep answers concise, helpful, and human support-like (short paragraphs or bullets).

Be concise, professional, and helpful.
"""


def format_memory(messages) -> str:
    if not messages:
        return "(no prior messages)"

    out: list[str] = []
    for m in messages:
        role = "User" if m.role == "user" else "Assistant"
        out.append(f"{role}: {m.content}")
    return "\n".join(out)


def extract_preferred_name(messages) -> str | None:
    if not messages:
        return None
    patterns = [
        re.compile(r"\bmy name is\s+([A-Za-z][A-Za-z '\-]{1,40})\b", re.IGNORECASE),
        re.compile(r"\bi am\s+([A-Za-z][A-Za-z '\-]{1,40})\b", re.IGNORECASE),
        re.compile(r"\bcall me\s+([A-Za-z][A-Za-z '\-]{1,40})\b", re.IGNORECASE),
    ]
    for m in reversed(messages):
        if getattr(m, "role", "") != "user":
            continue
        text = str(getattr(m, "content", "") or "").strip()
        for p in patterns:
            hit = p.search(text)
            if hit:
                name = re.sub(r"\s+", " ", hit.group(1)).strip()
                if 2 <= len(name) <= 40:
                    return name
    return None


def build_user_prompt(
    question: str,
    chunks: Sequence[Chunk],
    history_messages=None,
    messages=None,
) -> str:
    # Backward-compatible arg handling: allow either `history_messages` or `messages`.
    memory_items = messages if messages is not None else history_messages
    memory = format_memory(memory_items or [])
    preferred_name = extract_preferred_name(memory_items or [])

    context_blocks: list[str] = []
    for c in chunks:
        context_blocks.append(
            f"[document_id={c.document_id} chunk_id={c.id} chunk_index={c.chunk_index}]\n{c.text}"
        )

    context = "\n\n---\n\n".join(context_blocks) if context_blocks else "(no context)"
    profile = f"Preferred user name: {preferred_name}" if preferred_name else "Preferred user name: (unknown)"

    return f"""Conversation so far:
{memory}

User profile:
{profile}

Question:
{question}

Tenant knowledge chunks (use only this):
{context}

Answer:"""
