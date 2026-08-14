"""Embedding model wrapper.

Config-driven: dev defaults to the small, CPU-fast `bge-small-en-v1.5`; set OPSPILOT_EMBED_MODEL
to swap in BGE-M3 (or any sentence-transformers model). The bge family wants a query instruction
for short-query → passage retrieval, applied to queries only.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # the heavy dependency is imported lazily inside the function below
    from sentence_transformers import SentenceTransformer

DEFAULT_MODEL = os.getenv("OPSPILOT_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=2)
def _model(name: str) -> SentenceTransformer:
    from sentence_transformers import SentenceTransformer  # heavy import; keep lazy

    # The package resolves its exports lazily, so the imported name carries no type of its own.
    # Naming it here is what gives the cached model a type, whether or not the optional dependency
    # is installed in the environment doing the checking.
    model: SentenceTransformer = SentenceTransformer(name)
    return model


class Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name

    def encode_docs(self, texts: list[str]) -> np.ndarray:
        # `convert_to_numpy=True` is what makes the result an array, and the encoder's own signature
        # cannot express that, so the array type is established here. Already an array on this path,
        # so `asarray` returns it unchanged rather than converting anything.
        encoded = _model(self.model_name).encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return np.asarray(encoded)

    def encode_query(self, text: str) -> np.ndarray:
        encoded = _model(self.model_name).encode(
            [QUERY_INSTRUCTION + text], normalize_embeddings=True, convert_to_numpy=True
        )
        return np.asarray(encoded[0])
