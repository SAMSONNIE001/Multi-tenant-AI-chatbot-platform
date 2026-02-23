from dataclasses import dataclass
from typing import Literal, Sequence

Action = Literal["allow", "refuse"]


@dataclass
class DocPolicyResult:
    action: Action
    reason: str | None = None
    message: str | None = None


def evaluate_doc_policy(*, documents: Sequence, current_user) -> DocPolicyResult:
    """
    Enforce document-level restrictions.

    Assumptions based on your codebase:
    - current_user has .role (e.g. "admin", "user")
    - Document has .visibility ("public" | "internal_only")
    - Document has .tags (JSON list) like ["hr_only"]
    """

    role = (getattr(current_user, "role", "") or "").lower()
    is_admin = role == "admin"

    for d in documents:
        visibility = (getattr(d, "visibility", "public") or "public").lower()
        tags = getattr(d, "tags", []) or []

        # Restrict internal_only docs to admins
        if visibility == "internal_only" and not is_admin:
            return DocPolicyResult(
                action="refuse",
                reason="doc_visibility:internal_only",
                message="This information is restricted to admins.",
            )

        # Example tag restriction (expand later)
        if "hr_only" in tags and not is_admin:
            return DocPolicyResult(
                action="refuse",
                reason="doc_tag:hr_only",
                message="This information is restricted based on document access rules.",
            )

    return DocPolicyResult(action="allow")