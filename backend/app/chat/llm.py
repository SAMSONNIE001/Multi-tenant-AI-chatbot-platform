import os
from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, RateLimitError

CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
FALLBACK_ANSWER = "I don't have that information in the provided documents."


def generate_answer(system_prompt: str, user_prompt: str) -> str:
    try:
        resp = _client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""
    except (RateLimitError, APIConnectionError, APITimeoutError, APIError):
        return FALLBACK_ANSWER
