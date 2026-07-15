"""BM25-only retrieval — the deterministic runtime backend.

Loads the KB, chunks it with the shared chunker, and builds an in-memory BM25 index. It imports
neither sentence-transformers nor the vector index, so the production image never downloads an
embedding model to answer a lexical query. Distractors default off (evaluation-only).
"""

from __future__ import annotations

from pathlib import Path

from rank_bm25 import BM25Okapi

from opspilot.retrieval.base import Hit, aggregate_to_docs, allowed_chunk_ids, tokenize
from opspilot.retrieval.corpus import Chunk, chunk, load_docs


class BM25Retriever:
    backend_name = "bm25"

    def __init__(
        self,
        kb_dir: Path | str,
        distractor_dir: Path | str | None = None,
        include_distractors: bool = False,
    ) -> None:
        self.docs = load_docs(kb_dir, distractor_dir, include_distractors)
        self.chunks: list[Chunk] = [c for d in self.docs for c in chunk(d)]
        self._doc_kind = {d.doc_id: d.kind for d in self.docs}
        self._chunk_by_id = {c.chunk_id: c for c in self.chunks}
        self._bm25 = BM25Okapi([tokenize(c.text) for c in self.chunks])

    def search(
        self,
        query: str,
        *,
        k: int,
        kinds: tuple[str, ...] | None = None,
        services: tuple[str, ...] | None = None,
    ) -> list[Hit]:
        allowed = allowed_chunk_ids(self.chunks, kinds, services)
        scores = self._bm25.get_scores(tokenize(query))
        chunk_scores = {
            c.chunk_id: float(scores[i])
            for i, c in enumerate(self.chunks)
            if allowed is None or c.chunk_id in allowed
        }
        return aggregate_to_docs(chunk_scores, self._chunk_by_id, self._doc_kind, k)
