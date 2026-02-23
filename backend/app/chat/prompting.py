from typing import Sequence

from app.rag.models import Chunk

REFUSAL_SENTENCE = "I don't have that information in the provided documents."

SYSTEM_PROMPT = f"""You are a governance-first assistant for a single tenant.

Hard rules (must follow exactly):
1) Use ONLY the provided tenant knowledge chunks as your source of truth.
2) Every factual claim MUST end with a citation in this exact format: [document_id:chunk_id]
3) If the answer is not present in the chunks, respond exactly:
{REFUSAL_SENTENCE}
4) Do NOT guess. Do NOT use outside knowledge. Do NOT invent citations.
5) Conversation history is only context; it is NOT a source of truth. Do not cite history.

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


def build_user_prompt(
    question: str,
    chunks: Sequence[Chunk],
    history_messages=None,
    messages=None,
) -> str:
    # Backward-compatible arg handling: allow either `history_messages` or `messages`.
    memory_items = messages if messages is not None else history_messages
    memory = format_memory(memory_items or [])

    context_blocks: list[str] = []
    for c in chunks:
        context_blocks.append(
            f"[document_id={c.document_id} chunk_id={c.id} chunk_index={c.chunk_index}]\n{c.text}"
        )

    context = "\n\n---\n\n".join(context_blocks) if context_blocks else "(no context)"

    return f"""Conversation so far:
{memory}

Question:
{question}

Tenant knowledge chunks (use only this):
{context}

Answer:"""
