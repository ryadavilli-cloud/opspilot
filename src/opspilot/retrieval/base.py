"""Retrieval seam — the `SearchRetriever` interface the tools bind to, plus the shared chunk
tokenizer, `Hit` type, and filter/aggregate helpers used by every backend.

Tools depend on `search()`, never on whether the implementation is BM25, hybrid, rerank, or (in a
later slice) Azure AI Search. This keeps a lightweight lexical runtime backend swappable for the
heavy dense/rerank evaluation backend without touching tool code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from opspilot.retrieval.corpus import Chunk, Doc

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass(frozen=True)
class Hit:
    doc_id: str
    score: float
    kind: str


class SearchRetriever(Protocol):
    """The contract the retrieval tools use. `docs` exposes the indexed corpus for title/service
    lookup; `search` returns doc-level hits, optionally filtered by kind and service."""

    backend_name: str

    @property
    def docs(self) -> list[Doc]: ...

    def search(
        self,
        query: str,
        *,
        k: int,
        kinds: tuple[str, ...] | None = None,
        services: tuple[str, ...] | None = None,
    ) -> list[Hit]: ...


def allowed_chunk_ids(
    chunks: list[Chunk], kinds: tuple[str, ...] | None, services: tuple[str, ...] | None
) -> set[str] | None:
    """Chunk ids permitted by the kind/service filter, or None when no filter is applied."""
    if not kinds and not services:
        return None
    allowed = set()
    for c in chunks:
        if kinds and c.kind not in kinds:
            continue
        if services and not (set(c.services) & set(services)):
            continue
        allowed.add(c.chunk_id)
    return allowed


def aggregate_to_docs(
    chunk_scores: dict[str, float],
    chunk_by_id: dict[str, Chunk],
    doc_kind: dict[str, str],
    k: int,
) -> list[Hit]:
    """Aggregate chunk scores to the top-k doc hits (a doc scores as its best chunk)."""
    best: dict[str, float] = {}
    for cid, score in chunk_scores.items():
        doc_id = chunk_by_id[cid].doc_id
        if doc_id not in best or score > best[doc_id]:
            best[doc_id] = score
    ranked = sorted(best.items(), key=lambda kv: -kv[1])[:k]
    return [Hit(d, s, doc_kind.get(d, "")) for d, s in ranked]
