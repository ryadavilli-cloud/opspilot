"""Retrieval capabilities: search_runbooks / search_past_incidents over the Cosmos-backed retriever.

Return the uniform envelope carrying the retrieved passages themselves: each passage holds its
knowledge reference (e.g. `runbook:payment-timeout`, `postmortem:inc-001`), which doubles as the
citation, and the matched text rather than a pointer to it. There is one passage shape, so nothing
here reshapes what retrieval produced. No model call.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from opspilot.retrieval.retriever import ARCHITECTURE, POSTMORTEM, RUNBOOK, Passage, Retriever
from opspilot.tools.contracts import MAX_RESULTS, NonEmptyText
from opspilot.tools.errors import validated

_PassageCount = Annotated[int, Field(ge=1, le=MAX_RESULTS)]


@validated
def search_runbooks(
    retriever: Retriever,
    deadline_s: float,
    *,
    query: NonEmptyText,
    k: _PassageCount = 5,
    service: str | None = None,
) -> tuple[list[Passage], list[str]]:
    passages = retriever.search(
        query,
        k=k,
        collection=(RUNBOOK, ARCHITECTURE),
        services=(service,) if service else None,
        deadline_s=deadline_s,
    )
    return passages, [p.reference for p in passages]


@validated
def search_past_incidents(
    retriever: Retriever,
    deadline_s: float,
    *,
    query: NonEmptyText,
    k: _PassageCount = 5,
    service: str | None = None,
) -> tuple[list[Passage], list[str]]:
    passages = retriever.search(
        query,
        k=k,
        collection=POSTMORTEM,
        services=(service,) if service else None,
        deadline_s=deadline_s,
    )
    return passages, [p.reference for p in passages]
