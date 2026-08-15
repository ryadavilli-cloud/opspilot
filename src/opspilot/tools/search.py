"""Retrieval tools: search_runbooks / search_past_incidents over the Cosmos-backed `Retriever`.

Return the uniform `ToolResult` envelope; each hit's `doc_id` is the knowledge reference (e.g.
`runbook:payment-timeout`, `postmortem:inc-001`) and doubles as the citation, and `text` carries the
matched passage itself rather than a pointer to it (`data-and-evidence.md` §9). No LLM here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opspilot.retrieval.retriever import ARCHITECTURE, POSTMORTEM, RUNBOOK
from opspilot.tools.contracts import (
    DocHit,
    SearchPastIncidentsRequest,
    SearchRunbooksRequest,
    ToolResult,
)
from opspilot.tools.errors import run_tool

if TYPE_CHECKING:  # avoid importing the retriever at module load
    from opspilot.retrieval.retriever import Passage, Retriever


def _to_hits(passages: list[Passage]) -> list[DocHit]:
    return [
        DocHit(
            doc_id=p.reference,
            kind=p.category,
            title=p.title,
            text=p.text,
            services=list(p.services),
            score=round(p.score, 6),
        )
        for p in passages
    ]


def search_runbooks(
    retriever: Retriever, *, deadline_s: float, **kwargs: Any
) -> ToolResult[DocHit]:
    def logic(req: SearchRunbooksRequest) -> tuple[list[DocHit], list[str]]:
        services = (req.service,) if req.service else None
        passages = retriever.search(
            req.query,
            k=req.k,
            collection=(RUNBOOK, ARCHITECTURE),
            services=services,
            deadline_s=deadline_s,
        )
        recs = _to_hits(passages)
        return recs, [h.doc_id for h in recs]

    return run_tool("search_runbooks", SearchRunbooksRequest, logic, **kwargs)


def search_past_incidents(
    retriever: Retriever, *, deadline_s: float, **kwargs: Any
) -> ToolResult[DocHit]:
    def logic(req: SearchPastIncidentsRequest) -> tuple[list[DocHit], list[str]]:
        services = (req.service,) if req.service else None
        passages = retriever.search(
            req.query, k=req.k, collection=POSTMORTEM, services=services, deadline_s=deadline_s
        )
        recs = _to_hits(passages)
        return recs, [h.doc_id for h in recs]

    return run_tool("search_past_incidents", SearchPastIncidentsRequest, logic, **kwargs)
