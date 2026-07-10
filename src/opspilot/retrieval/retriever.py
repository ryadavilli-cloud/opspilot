"""Retriever — dense baseline and hybrid (dense + BM25 via RRF) over the chunked corpus.

Builds the index once (embeds every chunk), then answers queries in either mode. Results are
chunk hits aggregated to doc ids (max chunk score), optionally filtered by kind/services. The
dense mode is the baseline; hybrid adds a lexical (BM25) ranker and fuses with reciprocal-rank
fusion — the "hybrid beats vector-only" proof lives in the eval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from opspilot.retrieval.corpus import Chunk, chunk, load_docs
from opspilot.retrieval.embeddings import Embedder
from opspilot.retrieval.index import InMemoryVectorIndex

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass(frozen=True)
class Hit:
    doc_id: str
    score: float
    kind: str


class Retriever:
    def __init__(self, embedder: Embedder | None = None, include_distractors: bool = True) -> None:
        self.embedder = embedder or Embedder()
        self.docs = load_docs(include_distractors)
        self.chunks: list[Chunk] = [c for d in self.docs for c in chunk(d)]
        self._doc_kind = {d.doc_id: d.kind for d in self.docs}

        vectors = self.embedder.encode_docs([c.text for c in self.chunks])
        self.index = InMemoryVectorIndex()
        self.index.add([c.chunk_id for c in self.chunks], vectors)
        self._bm25 = BM25Okapi([_tokenize(c.text) for c in self.chunks])
        self._chunk_by_id = {c.chunk_id: c for c in self.chunks}

    # --- filtering + aggregation --------------------------------------------------------------
    def _allowed(self, kinds: tuple[str, ...] | None, services: tuple[str, ...] | None):
        if not kinds and not services:
            return None
        allowed = set()
        for c in self.chunks:
            if kinds and c.kind not in kinds:
                continue
            if services and not (set(c.services) & set(services)):
                continue
            allowed.add(c.chunk_id)
        return allowed

    def _to_docs(self, chunk_scores: dict[str, float], k: int) -> list[Hit]:
        best: dict[str, float] = {}
        for cid, score in chunk_scores.items():
            doc_id = self._chunk_by_id[cid].doc_id
            if doc_id not in best or score > best[doc_id]:
                best[doc_id] = score
        ranked = sorted(best.items(), key=lambda kv: -kv[1])[:k]
        return [Hit(d, s, self._doc_kind.get(d, "")) for d, s in ranked]

    # --- modes --------------------------------------------------------------------------------
    def dense(self, query: str, k: int = 5, kinds=None, services=None) -> list[Hit]:
        allowed = self._allowed(kinds, services)
        qv = self.embedder.encode_query(query)
        hits = self.index.search(qv, k=len(self.chunks), allowed=allowed)
        return self._to_docs(dict(hits), k)

    def hybrid(
        self, query: str, k: int = 5, kinds=None, services=None, rrf_k: int = 60
    ) -> list[Hit]:
        allowed = self._allowed(kinds, services)
        qv = self.embedder.encode_query(query)
        dense_rank = {cid: i for i, (cid, _) in enumerate(
            self.index.search(qv, k=len(self.chunks), allowed=allowed))}

        bm25_scores = self._bm25.get_scores(_tokenize(query))
        bm25_rank: dict[str, int] = {}
        rank = 0
        for i in sorted(range(len(self.chunks)), key=lambda j: -bm25_scores[j]):
            cid = self.chunks[i].chunk_id
            if allowed is not None and cid not in allowed:
                continue
            bm25_rank[cid] = rank
            rank += 1

        fused: dict[str, float] = {}
        for cid in set(dense_rank) | set(bm25_rank):
            score = 0.0
            if cid in dense_rank:
                score += 1.0 / (rrf_k + dense_rank[cid])
            if cid in bm25_rank:
                score += 1.0 / (rrf_k + bm25_rank[cid])
            fused[cid] = score
        return self._to_docs(fused, k)
