"""Retriever — dense baseline, hybrid (dense + BM25 via RRF), and reranked, over the chunked corpus.

Builds the index once (embeds every chunk), then answers queries in any mode. Results are chunk
hits aggregated to doc ids (max chunk score), optionally filtered by kind/services. The dense mode
is the baseline; hybrid adds a lexical (BM25) ranker and fuses with reciprocal-rank fusion; rerank
takes the hybrid candidate chunks and re-scores them with a cross-encoder. The "hybrid beats
vector-only" and "rerank lifts precision" proofs both live in the eval.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rank_bm25 import BM25Okapi

from opspilot.config import DISTRACTOR_DIR, KB_DIR, RERANK_CANDIDATES
from opspilot.retrieval.base import Hit, aggregate_to_docs, allowed_chunk_ids, tokenize
from opspilot.retrieval.corpus import Chunk, chunk, load_docs
from opspilot.retrieval.embeddings import Embedder
from opspilot.retrieval.index import InMemoryVectorIndex

if TYPE_CHECKING:
    from opspilot.retrieval.reranker import Reranker

__all__ = ["Hit", "Retriever"]


class Retriever:
    """The dense/hybrid/rerank evaluation backend. The runtime tool path uses the lighter
    `bm25.BM25Retriever`; both satisfy `base.SearchRetriever` via an adapter."""

    def __init__(
        self,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        kb_dir: Path | str | None = None,
        distractor_dir: Path | str | None = None,
        include_distractors: bool = True,
    ) -> None:
        self.embedder = embedder or Embedder()
        self._reranker = reranker  # lazily constructed on first rerank() call
        self.docs = load_docs(kb_dir or KB_DIR, distractor_dir or DISTRACTOR_DIR,
                              include_distractors)
        self.chunks: list[Chunk] = [c for d in self.docs for c in chunk(d)]
        self._doc_kind = {d.doc_id: d.kind for d in self.docs}

        vectors = self.embedder.encode_docs([c.text for c in self.chunks])
        self.index = InMemoryVectorIndex()
        self.index.add([c.chunk_id for c in self.chunks], vectors)
        self._bm25 = BM25Okapi([tokenize(c.text) for c in self.chunks])
        self._chunk_by_id = {c.chunk_id: c for c in self.chunks}

    @property
    def reranker(self) -> Reranker:
        if self._reranker is None:
            from opspilot.retrieval.reranker import Reranker

            self._reranker = Reranker()
        return self._reranker

    def _to_docs(self, chunk_scores: dict[str, float], k: int) -> list[Hit]:
        return aggregate_to_docs(chunk_scores, self._chunk_by_id, self._doc_kind, k)

    # --- modes --------------------------------------------------------------------------------
    def dense(self, query: str, k: int = 5, kinds=None, services=None) -> list[Hit]:
        allowed = allowed_chunk_ids(self.chunks, kinds, services)
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

        bm25_scores = self._bm25.get_scores(tokenize(query))
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
        allowed = allowed_chunk_ids(self.chunks, kinds, services)
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
        allowed = allowed_chunk_ids(self.chunks, kinds, services)
        fused = self._hybrid_chunk_scores(query, allowed, rrf_k)
        candidates = [cid for cid, _ in sorted(fused.items(), key=lambda kv: -kv[1])[:cand_k]]
        if not candidates:
            return []
        scores = self.reranker.score(query, [self._chunk_by_id[cid].text for cid in candidates])
        reranked = dict(zip(candidates, scores, strict=True))
        return self._to_docs(reranked, k)
