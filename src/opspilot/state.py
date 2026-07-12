"""Incident investigation state — the contract between graph nodes.

Reducers define how concurrent writes merge: `evidence` / `retrieved_sources` are
append-only (so diagnosis sees the full trail); `messages` uses add_messages; scalars
are last-write-wins (one node owns each at a time).
"""

from __future__ import annotations

from enum import StrEnum
from operator import add
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class Intent(StrEnum):
    KNOWN_ISSUE = "known_issue"
    NOVEL_INVESTIGATION = "novel_investigation"
    INFO_ONLY = "info_only"


class Evidence(TypedDict):
    source: str  # runbook | past_incident | logs | metrics | deploys | deps
    ref: str  # citation / doc id / query
    content: str


class IncidentState(TypedDict, total=False):
    incident_id: str  # == thread_id for the checkpointer
    alert: dict[str, Any]
    severity: str
    category: str
    intent: str
    matched_incident: str  # set if a past incident matches (fast path)

    affected_services: list[str]  # derived from the alert storm at triage
    onset: str                    # earliest alert / incident open time (ISO)
    triage: dict[str, Any]        # the deterministic triage decision + the evidence behind it

    evidence: Annotated[list[Evidence], add]  # append-only across loop turns
    retrieved_sources: Annotated[list[str], add]

    messages: Annotated[list, add_messages]  # ReAct scratchpad
    hypothesis: str
    confidence: float
    diagnose_iters: int
    diagnosis: dict[str, Any]  # the structured diagnostic cycle (plan/observations/hypothesis)

    report: dict[str, Any]
    approval: dict[str, Any]
    postmortem: dict[str, Any]

    degraded: bool  # set by circuit breaker / fallback
    error: str
