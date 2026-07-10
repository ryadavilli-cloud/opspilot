"""Vector index abstraction — in-memory dense now, Azure AI Search / Qdrant behind it later.

The `VectorIndex` protocol is the retrieval analogue of the repository seam: the retriever talks
to this interface, so swapping the backing store at the Azure phase does not touch the retriever.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np


class VectorIndex(Protocol):
    def add(self, ids: list[str], vectors: np.ndarray) -> None: ...
    def search(
        self, query_vector: np.ndarray, k: int, allowed: set[str] | None = None
    ) -> list[tuple[str, float]]: ...


class InMemoryVectorIndex:
    """Cosine similarity over normalized vectors (dot product), with an optional id allowlist."""

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._matrix: np.ndarray | None = None

    def add(self, ids: list[str], vectors: np.ndarray) -> None:
        self._ids = list(ids)
        self._matrix = np.asarray(vectors, dtype=np.float32)

    def search(
        self, query_vector: np.ndarray, k: int, allowed: set[str] | None = None
    ) -> list[tuple[str, float]]:
        if self._matrix is None:
            return []
        scores = self._matrix @ np.asarray(query_vector, dtype=np.float32)
        out: list[tuple[str, float]] = []
        for i in np.argsort(-scores):
            cid = self._ids[i]
            if allowed is not None and cid not in allowed:
                continue
            out.append((cid, float(scores[i])))
            if len(out) >= k:
                break
        return out
