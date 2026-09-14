"""Production SEC RAG embedding engine with deterministic keyless fallback."""
from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from typing import Callable, Sequence

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 128
_TOKEN_PATTERN = re.compile(r"\b[a-zA-Z0-9_-]+\b")


def _hash_embed_text(text: str, dim: int = EMBEDDING_DIMENSION) -> list[float]:
    """Generate a deterministic, normalized 128-dimensional term-hash embedding vector.

    Fast, zero network, zero dependencies.
    """
    tokens = _TOKEN_PATTERN.findall((text or "").lower())
    if not tokens:
        return [0.0] * dim

    vec = [0.0] * dim
    for token in tokens:
        # Murmur/md5 hash bucket
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        slot = h % dim
        sign = 1.0 if (h // dim) % 2 == 0 else -1.0
        vec[slot] += sign

    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [round(x / norm, 6) for x in vec]
    return vec


def get_sec_embedder() -> Callable[[list[str]], Sequence[Sequence[float]]]:
    """Return a batch text embedder for SEC filing chunks."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)

            def _openai_embed(texts: list[str]) -> list[list[float]]:
                res = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=texts,
                )
                return [d.embedding for d in res.data]

            return _openai_embed
        except Exception as exc:
            logger.warning("OpenAI embedding client initialization failed: %s; falling back to local hash vectorizer", exc)

    def _fallback_batch_embed(texts: list[str]) -> list[list[float]]:
        return [_hash_embed_text(t) for t in texts]

    return _fallback_batch_embed


def get_sec_query_embedder() -> Callable[[str], Sequence[float]]:
    """Return a single query embedder for SEC claim verification."""
    batch_embedder = get_sec_embedder()

    def _query_embed(query: str) -> Sequence[float]:
        return batch_embedder([query])[0]

    return _query_embed
