"""Cross-encoder reranker wrapper.

Layers *after* the hybrid candidate set: a cross-encoder scores each (query, chunk) pair
jointly, which is more precise than the bi-encoder cosine used for first-stage retrieval but
too expensive to run over the whole corpus — hence retrieve-then-rerank. Config-driven and
lazy, mirroring `embeddings.Embedder`: dev defaults to `bge-reranker-v2-m3`; set
OPSPILOT_RERANKER_MODEL to swap it.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the heavy dependency is imported lazily inside the function below
    from sentence_transformers import CrossEncoder

DEFAULT_RERANKER = os.getenv("OPSPILOT_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")


@lru_cache(maxsize=2)
def _cross_encoder(name: str) -> CrossEncoder:
    from sentence_transformers import CrossEncoder  # heavy import; keep lazy

    # The package resolves its exports lazily, so the imported name carries no type of its own.
    # Naming it here is what gives the cached encoder a type, whether or not the optional dependency
    # is installed in the environment doing the checking.
    encoder: CrossEncoder = CrossEncoder(name)
    return encoder


class Reranker:
    def __init__(self, model_name: str = DEFAULT_RERANKER) -> None:
        self.model_name = model_name

    def score(self, query: str, passages: list[str]) -> list[float]:
        """Relevance score per passage for the query (higher = more relevant)."""
        if not passages:
            return []
        scores = _cross_encoder(self.model_name).predict([(query, p) for p in passages])
        return [float(s) for s in scores]
