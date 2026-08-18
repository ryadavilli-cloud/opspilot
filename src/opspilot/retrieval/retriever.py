"""The retrieval subsystem.

Dense search (Cosmos vector search over the query embedding) and lexical search (an in-process
term-overlap scorer, BM25-style, run over the same filtered candidates) are fused by reciprocal
rank fusion. What a query names as its collection selects the categories searched; where it names
none, routing selects from the question's shape. Passages the question names by an exact identifier
are then promoted, and what survives the passage budget is returned as the matched passage itself,
never a pointer.

No local embedding model is loaded here, and no model ranks anything: the query vector comes from
the same Azure OpenAI deployment corpus preparation used to embed every passage
(`retrieval/embeddings.py`), and every step after it is deterministic.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

from opspilot.data.knowledge_records import (
    MAX_CANDIDATES,
    KnowledgeRecords,
    default_knowledge_records,
)
from opspilot.retrieval.base import tokenize
from opspilot.retrieval.embeddings import QueryEmbedder, default_query_embedder

# The three routed logical collections. Fixed at three; a fourth would need its own accepted
# collection.
RUNBOOK = "runbook"
ARCHITECTURE = "architecture"
POSTMORTEM = "postmortem"
CATEGORIES = (RUNBOOK, ARCHITECTURE, POSTMORTEM)

# Reciprocal rank fusion constant. 60 is the RRF paper's own default and the value the superseded
# hybrid retriever already used; nothing in the accepted retrieval design asks for a different one.
_RRF_K = 60

# How much retrieved text may reach an agent from one call. An engineering limit rather than a tuned
# value: passages are section-sized, and a budget is what keeps a prompt from filling with
# near-misses. It is a ceiling, so a caller may ask for fewer but never for more.
PASSAGE_BUDGET = 5

# Deterministic collection routing from question shape: procedural questions favor runbooks,
# structural questions favor service knowledge, and precedent questions favor prior incidents. A
# question matching none of these defaults to runbooks, the most common investigative ask, rather
# than searching every collection at once.
_PROCEDURAL_HINTS = (
    "how to",
    "how do",
    "runbook",
    "remediate",
    "remediation",
    "restart",
    "rollback",
    "mitigat",
    "steps to",
    "procedure",
    "fix ",
)
_STRUCTURAL_HINTS = (
    "depend",
    "architecture",
    "topology",
    "upstream",
    "downstream",
    "service map",
    "integrat",
    "owns",
    "blast radius",
)
_PRECEDENT_HINTS = (
    "similar incident",
    "past incident",
    "previous incident",
    "before",
    "history",
    "precedent",
    "recurr",
    "last time",
    "happened again",
)


def route_category(question: str) -> str:
    """The single collection a question with no named collection routes to."""
    text = question.lower()
    scored = {
        RUNBOOK: sum(1 for hint in _PROCEDURAL_HINTS if hint in text),
        ARCHITECTURE: sum(1 for hint in _STRUCTURAL_HINTS if hint in text),
        POSTMORTEM: sum(1 for hint in _PRECEDENT_HINTS if hint in text),
    }
    best = max(CATEGORIES, key=lambda category: scored[category])
    return best if scored[best] > 0 else RUNBOOK


@dataclass(frozen=True)
class Passage:
    """One retrieved passage: the matched content itself, never a pointer to it.

    The one shape a retrieval result travels in. Everything downstream of the retriever reads this
    and nothing else, so a passage cannot arrive at an agent in one shape and at the knowledge set
    in another. Corpus preparation has its own shapes for the documents it chunks; they stop at the
    container and never appear on this path.
    """

    reference: str  # the knowledge reference, e.g. "runbook:payment-timeout"
    category: str  # runbook | architecture | postmortem
    title: str
    text: str  # the matched passage
    services: tuple[str, ...]
    score: float


def _question_names(identifiers: Iterable[str], question: str) -> bool:
    """Whether the question mentions an identifier this passage was found to carry.

    Corpus preparation extracted those identifiers by looking for exactly these strings in the
    passage text: service and infrastructure names, deploy identifiers, error codes. Matching them
    back against the question the same way keeps one notion of "this names that" at both ends. A
    second extractor reading identifiers out of the question would be a second notion, free to
    drift from the one that wrote the field.
    """
    text = question.lower()
    return any(identifier and identifier.lower() in text for identifier in identifiers)


def _promote(ranked: list[str], rows: dict[str, dict[str, Any]], question: str) -> list[str]:
    """Stable promotion: passages the question names by identifier first, the rest after, each
    keeping the order fusion gave it.

    This runs over the whole fused list rather than over the budget's worth of it, and truncation
    comes after. That ordering is the point: an exact service name, error code, or deploy id is
    worth trusting precisely where it would otherwise fall just below the cutoff, and promoting
    within an already-truncated list could never rescue it.

    Nothing here scores or re-ranks. A passage either carries an identifier the question names or
    it does not, so the result is the same on every run over the same inputs.
    """
    named: list[str] = []
    rest: list[str] = []
    for row_id in ranked:
        identifiers = rows[row_id].get("identifiers") or ()
        target = named if _question_names(identifiers, question) else rest
        target.append(row_id)
    return named + rest


def _to_passage(row: dict[str, Any], score: float) -> Passage:
    return Passage(
        reference=str(row["doc_id"]),
        category=str(row["category"]),
        title=str(row.get("title", "")),
        text=str(row["text"]),
        services=tuple(row.get("services") or ()),
        score=score,
    )


class Retriever:
    """Dense + lexical retrieval over the `knowledge` container, fused by RRF.

    `records` and `embedder` are injected so a test holds fakes and the deployed path holds the real
    Cosmos container and Azure OpenAI deployment; there is one retrieval algorithm, only the sources
    it reads differ.
    """

    def __init__(self, records: KnowledgeRecords, embedder: QueryEmbedder) -> None:
        self._records = records
        self._embedder = embedder

    def search(
        self,
        query: str,
        *,
        k: int,
        collection: str | tuple[str, ...] | None = None,
        services: tuple[str, ...] | None = None,
        deadline_s: float,
    ) -> list[Passage]:
        categories = self._categories_for(query, collection)

        dense_rows = self._records.nearest(
            categories,
            self._embedder.embed(query, deadline_s=deadline_s),
            services,
            deadline_s=deadline_s,
        )
        candidate_rows = self._records.by_categories(categories, services, deadline_s=deadline_s)

        rows_by_id = {row["id"]: row for row in (*dense_rows, *candidate_rows)}
        fused = _fuse(query, dense_rows, candidate_rows)
        ranked = [row_id for row_id, _ in sorted(fused.items(), key=lambda item: -item[1])]
        chosen = _promote(ranked, rows_by_id, query)[: min(k, PASSAGE_BUDGET)]
        return [_to_passage(rows_by_id[row_id], fused[row_id]) for row_id in chosen]

    @staticmethod
    def _categories_for(query: str, collection: str | tuple[str, ...] | None) -> tuple[str, ...]:
        if collection is None:
            return (route_category(query),)
        if isinstance(collection, str):
            return (collection,)
        return tuple(collection)


def _fuse(
    query: str, dense_rows: list[dict[str, Any]], candidate_rows: list[dict[str, Any]]
) -> dict[str, float]:
    """Reciprocal rank fusion over the dense candidate set and the lexically re-ranked candidate
    set. Both stay within `MAX_CANDIDATES` (D-003's fused-candidate ceiling)."""
    dense_rank = {row["id"]: i for i, row in enumerate(dense_rows)}

    lexical_rank: dict[str, int] = {}
    if candidate_rows:
        bm25 = BM25Okapi([tokenize(row["text"]) for row in candidate_rows])
        scores = bm25.get_scores(tokenize(query))
        order = sorted(range(len(candidate_rows)), key=lambda i: -scores[i])[:MAX_CANDIDATES]
        lexical_rank = {candidate_rows[i]["id"]: rank for rank, i in enumerate(order)}

    fused: dict[str, float] = {}
    for row_id in set(dense_rank) | set(lexical_rank):
        score = 0.0
        if row_id in dense_rank:
            score += 1.0 / (_RRF_K + dense_rank[row_id])
        if row_id in lexical_rank:
            score += 1.0 / (_RRF_K + lexical_rank[row_id])
        fused[row_id] = score
    return fused


_default: Retriever | None = None


def default_retriever() -> Retriever:
    """The process-wide retriever (lazy, built once), over the deployed knowledge container and
    embedding deployment."""
    global _default
    if _default is None:
        _default = Retriever(default_knowledge_records(), default_query_embedder())
    return _default
