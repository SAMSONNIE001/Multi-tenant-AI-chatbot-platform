import re


def extract_policy_from_text(text: str) -> dict:
    """
    MVP policy extractor:
    - Always blocks credential harvesting via regex
    - Pulls prohibited items from "Prohibited / Not allowed / Disallowed" sections
    - Saves as tenant policy JSON
    """
    t = text or ""
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]

    rules = [
        # Always block credential requests
        {
            "type": "deny_regex",
            "pattern": r"(?i)\b(password|api\s*key|secret|token)\b",
            "message": "Credential-related requests are blocked by policy.",
        }
    ]

    # Heuristic: gather bullet items under prohibited headings
    prohibited_keywords: list[str] = []
    in_prohibited = False

    for ln in lines:
        # Start of prohibited section
        if re.search(r"(?i)\bprohibited\b|\bnot allowed\b|\bdisallowed\b", ln):
            in_prohibited = True
            continue

        # Stop at the next obvious heading
        if re.match(r"^[A-Z][A-Za-z0-9\s&\-]{3,}:$", ln):
            in_prohibited = False

        if in_prohibited:
            if re.match(r"^(-|•|\*|\d+\))\s+", ln):
                item = re.sub(r"^(-|•|\*|\d+\))\s+", "", ln).strip()
                # Keep short-ish items as keyword triggers
                if 3 <= len(item) <= 80:
                    prohibited_keywords.append(item.lower())

    # Add deny_keywords rule if we found any items
    if prohibited_keywords:
        rules.append(
            {
                "type": "deny_keywords",
                "keywords": list(dict.fromkeys(prohibited_keywords))[:80],  # de-dupe + cap
                "message": "This request is not allowed by your organization's policy.",
            }
        )

    return {
        "refusal_message": "I can't help with that request based on your organization's policy.",
        "rules": rules,
    }