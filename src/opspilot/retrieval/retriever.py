"""Retriever — dense baseline, hybrid (dense + BM25 via RRF), and reranked, over the chunked corpus.

Builds the index once (embeds every chunk), then answers queries in any mode. Results are chunk
hits aggregated to doc ids (max chunk score), optionally filtered by kind/services. The dense mode
is the baseline; hybrid adds a lexical (BM25) ranker and fuses with reciprocal-rank fusion; rerank
takes the hybrid candidate chunks and re-scores them with a cross-encoder. The "hybrid beats
vector-only" and "rerank lifts precision" proofs both live in the eval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rank_bm25 import BM25Okapi

from opspilot.config import RERANK_CANDIDATES
from opspilot.retrieval.corpus import Chunk, chunk, load_docs
from opspilot.retrieval.embeddings import Embedder
from opspilot.retrieval.index import InMemoryVectorIndex

if TYPE_CHECKING:
    from opspilot.retrieval.reranker import Reranker

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass(frozen=True)
class Hit:
    doc_id: str
    score: float
    kind: str


class Retriever:
    def __init__(
        self,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        include_distractors: bool = True,
    ) -> None:
        self.embedder = embedder or Embedder()
        self._reranker = reranker  # lazily constructed on first rerank() call
        self.docs = load_docs(include_distractors)
        self.chunks: list[Chunk] = [c for d in self.docs for c in chunk(d)]
        self._doc_kind = {d.doc_id: d.kind for d in self.docs}

        vectors = self.embedder.encode_docs([c.text for c in self.chunks])
        self.index = InMemoryVectorIndex()
        self.index.add([c.chunk_id for c in self.chunks], vectors)
        self._bm25 = BM25Okapi([_tokenize(c.text) for c in self.chunks])
        self._chunk_by_id = {c.chunk_id: c for c in self.chunks}

    @property
    def reranker(self) -> Reranker:
        if self._reranker is None:
            from opspilot.retrieval.reranker import Reranker

            self._reranker = Reranker()
        return self._reranker

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

    def _hybrid_chunk_scores(
        self, query: str, allowed: set[str] | None, rrf_k: int
    ) -> dict[str, float]:
        """Fused RRF score per chunk id — the shared first stage for hybrid and rerank."""
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
        return fused

    def hybrid(
        self, query: str, k: int = 5, kinds=None, services=None, rrf_k: int = 60
    ) -> list[Hit]:
        allowed = self._allowed(kinds, services)
        fused = self._hybrid_chunk_scores(query, allowed, rrf_k)
        return self._to_docs(fused, k)

    def rerank(
        self,
        query: str,
        k: int = 5,
        kinds=None,
        services=None,
        rrf_k: int = 60,
        cand_k: int = RERANK_CANDIDATES,
    ) -> list[Hit]:
        """Hybrid to pull `cand_k` candidate chunks, then a cross-encoder re-scores them."""
        allowed = self._allowed(kinds, services)
        fused = self._hybrid_chunk_scores(query, allowed, rrf_k)
        candidates = [cid for cid, _ in sorted(fused.items(), key=lambda kv: -kv[1])[:cand_k]]
        if not candidates:
            return []
        scores = self.reranker.score(query, [self._chunk_by_id[cid].text for cid in candidates])
        reranked = dict(zip(candidates, scores, strict=True))
        return self._to_docs(reranked, k)
