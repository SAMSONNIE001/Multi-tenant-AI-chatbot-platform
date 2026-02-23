import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.governance.models import TenantPolicy

Action = Literal["allow", "refuse", "escalate"]


@dataclass
class PolicyResult:
    action: Action
    reason: str | None = None
    message: str | None = None


DEFAULT_REFUSAL = "I can't help with that request based on your organization's policy."


def _safe_lower(s: str) -> str:
    return (s or "").lower()


def evaluate_question_policy(db: Session, *, tenant_id: str, question: str) -> PolicyResult:
    """
    8.2.4: policies are tenant-driven from stored policy_json.
    """
    q = question or ""
    ql = _safe_lower(q)

    row = db.execute(select(TenantPolicy).where(TenantPolicy.tenant_id == tenant_id)).scalar_one_or_none()
    policy = row.policy_json if row and row.policy_json else {}

    refusal_message = policy.get("refusal_message") or DEFAULT_REFUSAL
    rules = policy.get("rules") or []

    for r in rules:
        rtype = r.get("type")

        if rtype == "deny_keywords":
            keywords = [k for k in (r.get("keywords") or []) if isinstance(k, str)]
            if any(_safe_lower(k) in ql for k in keywords):
                return PolicyResult(
                    action="refuse",
                    reason="policy:deny_keywords",
                    message=r.get("message") or refusal_message,
                )

        if rtype == "deny_regex":
            pattern = r.get("pattern")
            if isinstance(pattern, str) and pattern:
                if re.search(pattern, q):
                    return PolicyResult(
                        action="refuse",
                        reason="policy:deny_regex",
                        message=r.get("message") or refusal_message,
                    )

    return PolicyResult(action="allow")