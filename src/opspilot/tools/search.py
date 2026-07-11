"""Retrieval tools — search_runbooks / search_past_incidents over the real Retriever.

These graduate the Phase-1 stubs onto hybrid retrieval. They return the uniform ToolResult
envelope; each hit's `doc_id` is the retrieval ref (e.g. `runbook:payment-timeout`,
`postmortem:inc-001`) and doubles as the evidence citation, which always resolves to a KB doc
(the tool retriever indexes the real KB only — no distractors). No LLM here.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from opspilot.data.repository import Repository
from opspilot.tools.contracts import (
    DocHit,
    SearchPastIncidentsRequest,
    SearchRunbooksRequest,
    ToolResult,
    to_utc,
)
from opspilot.tools.errors import run_tool

if TYPE_CHECKING:  # avoid importing the ML stack at module load
    from opspilot.retrieval.retriever import Retriever

RECENCY_BONUS = 0.2  # up to +20% score for the most recent matching incident


def _titles_services(retriever: Retriever) -> tuple[dict[str, str], dict[str, list[str]]]:
    titles = {d.doc_id: d.title for d in retriever.docs}
    services = {d.doc_id: list(d.services) for d in retriever.docs}
    return titles, services


def _to_hits(retriever: Retriever, hits) -> list[DocHit]:
    titles, services = _titles_services(retriever)
    return [
        DocHit(doc_id=h.doc_id, kind=h.kind, title=titles.get(h.doc_id, ""),
               services=services.get(h.doc_id, []), score=round(h.score, 6))
        for h in hits
    ]


def search_runbooks(retriever: Retriever, **kwargs) -> ToolResult[DocHit]:
    def logic(req: SearchRunbooksRequest) -> tuple[list[DocHit], list[str]]:
        services = (req.service,) if req.service else None
        hits = retriever.hybrid(req.query, k=req.k, kinds=("runbook", "architecture"),
                                services=services)
        recs = _to_hits(retriever, hits)
        return recs, [h.doc_id for h in recs]

    return run_tool("search_runbooks", SearchRunbooksRequest, logic, **kwargs)


def search_past_incidents(retriever: Retriever, repo: Repository, **kwargs) -> ToolResult[DocHit]:
    def logic(req: SearchPastIncidentsRequest) -> tuple[list[DocHit], list[str]]:
        services = (req.service,) if req.service else None
        # Over-fetch, then recency-weight the postmortems by their incident's onset.
        hits = retriever.hybrid(req.query, k=max(req.k * 2, req.k), kinds=("postmortem",),
                                services=services)

        def onset(doc_id: str) -> float | None:
            inc_id = doc_id.split(":", 1)[1] if ":" in doc_id else doc_id
            rec = repo.incident(inc_id)
            if not rec or "opened_at" not in rec:
                return None
            try:
                return to_utc(datetime.strptime(rec["opened_at"], "%Y-%m-%dT%H:%M:%SZ")).timestamp()
            except ValueError:
                return None

        ts = {h.doc_id: onset(h.doc_id) for h in hits}
        valid = [t for t in ts.values() if t is not None]
        lo, hi = (min(valid), max(valid)) if valid else (0.0, 0.0)

        def weighted(h) -> float:
            t = ts[h.doc_id]
            norm = (t - lo) / (hi - lo) if (t is not None and hi > lo) else 0.0
            return h.score * (1 + RECENCY_BONUS * norm)

        ranked = sorted(hits, key=weighted, reverse=True)[: req.k]
        recs = _to_hits(retriever, ranked)
        return recs, [h.doc_id for h in recs]

    return run_tool("search_past_incidents", SearchPastIncidentsRequest, logic, **kwargs)
