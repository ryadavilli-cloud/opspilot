"""Adapter presenting the hybrid/eval `Retriever` through the `SearchRetriever` seam.

The evaluation `Retriever` exposes dense/hybrid/rerank modes; the tools only know `search()`. This
wraps its `hybrid()` mode so the same tool code runs over either backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opspilot.retrieval.base import Hit

if TYPE_CHECKING:
    from opspilot.retrieval.corpus import Doc
    from opspilot.retrieval.retriever import Retriever


class HybridRetrieverAdapter:
    backend_name = "hybrid"

    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever

    @property
    def docs(self) -> list[Doc]:
        return self._retriever.docs

    def search(
        self,
        query: str,
        *,
        k: int,
        kinds: tuple[str, ...] | None = None,
        services: tuple[str, ...] | None = None,
    ) -> list[Hit]:
        return self._retriever.hybrid(query, k=k, kinds=kinds, services=services)
