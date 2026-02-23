import os
from typing import List

from openai import OpenAI

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def embed_text(text: str) -> List[float]:
    resp = _client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return resp.data[0].embedding
