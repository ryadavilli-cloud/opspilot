"""Retrieval capabilities: search_runbooks / search_past_incidents over the Cosmos-backed retriever.

Return the uniform envelope carrying the retrieved passages themselves: each passage holds its
knowledge reference (e.g. `runbook:payment-timeout`, `postmortem:inc-001`), which doubles as the
citation, and the matched text rather than a pointer to it. There is one passage shape, so nothing
here reshapes what retrieval produced. No model call.

Two capabilities rather than one, each naming a fixed collection: the difference between "how is
this handled" and "has this happened before" is a real investigative choice, and it is the
investigator's to make by picking a capability rather than by filling in an argument.

What comes back is knowledge, not operational evidence. Admission never turns these passages into
observations about the current incident, and a call that does not answer becomes a limitation like
any other capability's.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from opspilot.retrieval.retriever import (
    ARCHITECTURE,
    PASSAGE_BUDGET,
    POSTMORTEM,
    RUNBOOK,
    Passage,
    Retriever,
)
from opspilot.tools.contracts import NonEmptyText
from opspilot.tools.errors import validated

# A caller may narrow the budget but cannot widen it: asking for more passages than the budget
# allows has no expressible form here rather than being accepted and quietly clipped.
_PassageCount = Annotated[int, Field(ge=1, le=PASSAGE_BUDGET)]


@validated
def search_runbooks(
    retriever: Retriever,
    deadline_s: float,
    *,
    query: NonEmptyText,
    k: _PassageCount = PASSAGE_BUDGET,
    service: str | None = None,
) -> tuple[list[Passage], list[str]]:
    """Runbooks and architecture notes: how this system is meant to work, and what to check when
    it does not. Use it when you do not yet know where to look."""
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
    k: _PassageCount = PASSAGE_BUDGET,
    service: str | None = None,
) -> tuple[list[Passage], list[str]]:
    """Write-ups of incidents that already happened: what was wrong then, and what settled it.
    Use it when this looks like something the system has done before."""
    passages = retriever.search(
        query,
        k=k,
        collection=POSTMORTEM,
        services=(service,) if service else None,
        deadline_s=deadline_s,
    )
    return passages, [p.reference for p in passages]
