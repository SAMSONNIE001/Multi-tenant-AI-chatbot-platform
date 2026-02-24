import os
from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, RateLimitError

CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
FALLBACK_ANSWER = "I don't have that information in the provided documents."


def generate_answer(
    system_prompt: str, user_prompt: str
) -> tuple[str, int | None, int | None, int | None]:
    try:
        resp = _client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        usage = getattr(resp, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        total_tokens = getattr(usage, "total_tokens", None) if usage else None
        return (
            resp.choices[0].message.content or "",
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )
    except (RateLimitError, APIConnectionError, APITimeoutError, APIError):
        return FALLBACK_ANSWER, None, None, None
