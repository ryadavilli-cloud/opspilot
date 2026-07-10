"""Embedding model wrapper.

Config-driven: dev defaults to the small, CPU-fast `bge-small-en-v1.5`; set OPSPILOT_EMBED_MODEL
to swap in BGE-M3 (or any sentence-transformers model). The bge family wants a query instruction
for short-query → passage retrieval, applied to queries only.
"""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np

DEFAULT_MODEL = os.getenv("OPSPILOT_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=2)
def _model(name: str):
    from sentence_transformers import SentenceTransformer  # heavy import; keep lazy

    return SentenceTransformer(name)


class Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name

    def encode_docs(self, texts: list[str]) -> np.ndarray:
        return _model(self.model_name).encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )

    def encode_query(self, text: str) -> np.ndarray:
        return _model(self.model_name).encode(
            [QUERY_INSTRUCTION + text], normalize_embeddings=True, convert_to_numpy=True
        )[0]
