"""Retrieval backend factory — selects a `SearchRetriever` from config.

`bm25` builds the lightweight lexical runtime backend (no ML import); `hybrid` builds the dense +
BM25 evaluation backend behind an adapter. Heavy imports stay inside their branch so choosing
`bm25` never pulls in sentence-transformers, numpy, or the vector index. An unknown backend is a
configuration error, surfaced loudly rather than silently degraded.
"""

from __future__ import annotations

from pathlib import Path

from opspilot import config
from opspilot.retrieval.base import SearchRetriever

_VALID = ("bm25", "hybrid", "rerank")


def build_retriever(
    backend: str | None = None,
    kb_dir: Path | str | None = None,
    distractor_dir: Path | str | None = None,
    include_distractors: bool = False,
) -> SearchRetriever:
    backend = (backend or config.RETRIEVAL_BACKEND).lower()
    kb_dir = Path(kb_dir) if kb_dir is not None else config.KB_DIR

    if backend == "bm25":
        from opspilot.retrieval.bm25 import BM25Retriever

        return BM25Retriever(kb_dir, distractor_dir, include_distractors)

    if backend in ("hybrid", "rerank"):
        from opspilot.retrieval.adapters import HybridRetrieverAdapter
        from opspilot.retrieval.retriever import Retriever

        return HybridRetrieverAdapter(
            Retriever(kb_dir=kb_dir, distractor_dir=distractor_dir,
                      include_distractors=include_distractors))

    raise ValueError(
        f"unknown retrieval backend {backend!r}; expected one of {', '.join(_VALID)}")
