"""Conditional routing functions for the investigation graph.

These are the deterministic skeleton: stage order is fixed code, auditable and testable.
The known-issue fast path collapses to the full path in Phase 1 and becomes real in Phase 5.
"""

from __future__ import annotations

from opspilot.config import CONFIDENCE_THRESHOLD, MAX_DIAGNOSE_ITERS
from opspilot.state import IncidentState, Intent


def route_by_intent(state: IncidentState) -> str:
    if state.get("intent") == Intent.INFO_ONLY.value:
        return "synthesize_report"          # informational reply (exempt from the citation gate)
    if state.get("intent") == Intent.KNOWN_ISSUE.value and state.get("matched_incident"):
        return "known_issue_fast_path"      # short-circuit to the stored resolution
    return "retrieve"                        # novel → full investigation


def diagnose_continue(state: IncidentState) -> str:
    if state.get("confidence", 0.0) >= CONFIDENCE_THRESHOLD:
        return "synthesize_report"
    if state.get("diagnose_iters", 0) >= MAX_DIAGNOSE_ITERS:  # circuit breaker
        return "escalate"
    return "diagnose"


def after_approval(state: IncidentState) -> str:
    decision = state.get("approval", {}).get("decision")
    return "finalize_report" if decision in ("approve", "edit") else "escalate"
