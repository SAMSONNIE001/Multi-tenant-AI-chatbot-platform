import re
from dataclasses import dataclass
from typing import Iterable

REFUSAL_SENTENCE = "I don't have that information in the provided documents."

# Matches: [d_abc123:c_xyz789]
_CIT_RE = re.compile(r"\[([^\[\]:\s]+):([^\[\]\s]+)\]")


@dataclass(frozen=True)
class CitationKey:
    document_id: str
    chunk_id: str


def extract_citation_keys(answer: str) -> list[CitationKey]:
    keys: list[CitationKey] = []
    for doc_id, chunk_id in _CIT_RE.findall(answer or ""):
        keys.append(CitationKey(document_id=doc_id, chunk_id=chunk_id))
    # de-dup while preserving order
    seen = set()
    out: list[CitationKey] = []
    for k in keys:
        if k not in seen:
            out.append(k)
            seen.add(k)
    return out


def is_refusal(answer: str) -> bool:
    return (answer or "").strip() == REFUSAL_SENTENCE


def validate_citations(answer: str, retrieved_chunks: Iterable) -> tuple[bool, list[CitationKey]]:
    """
    Valid if:
    - refusal => ok (no citations required)
    - non-refusal => must have >=1 citations AND all citations exist in retrieved set
    """
    if is_refusal(answer):
        return True, []

    keys = extract_citation_keys(answer)
    if not keys:
        return False, []

    valid = {CitationKey(document_id=c.document_id, chunk_id=c.id) for c in retrieved_chunks}
    for k in keys:
        if k not in valid:
            return False, keys
    return True, keys