"""Локальные эмбеддинги (pgvector-ready fallback без внешнего API)."""
from __future__ import annotations

import hashlib
import math
import re

_DIM = 64
_TOKEN = re.compile(r"\w+", re.UNICODE)


def embed_text(text: str, *, dims: int = _DIM) -> list[float]:
    """Детерминированный псевдо-эмбеддинг для демо / offline."""
    tokens = _TOKEN.findall((text or "").lower())
    if not tokens:
        tokens = ["empty"]
    vec = [0.0] * dims
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for i in range(dims):
            vec[i] += (digest[i % len(digest)] / 255.0) - 0.5
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))
