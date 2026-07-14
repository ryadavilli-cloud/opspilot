"""Conditional routing functions for the investigation graph.

These are the deterministic skeleton: stage order is fixed code, auditable and testable. Routers
are pure functions over the typed state. The interim `confidence >= threshold` stop rule below is
a known locked-decision violation scheduled for replacement by the deterministic sufficiency gate
in the next hardening step — confidence must become an input, never the trigger.
"""

from __future__ import annotations

from opspilot.config import CONFIDENCE_THRESHOLD, MAX_DIAGNOSE_ITERS
from opspilot.state import Intent, InvestigationState


def route_by_intent(state: InvestigationState) -> str:
    if state.intent == Intent.INFO_ONLY.value:
        return "synthesize_report"          # informational reply (exempt from the citation gate)
    if state.intent == Intent.KNOWN_ISSUE.value and state.matched_incident:
        return "known_issue_fast_path"      # short-circuit to the stored resolution
    return "retrieve"                        # novel → full investigation


def diagnose_continue(state: InvestigationState) -> str:
    # Interim stop rule (confidence threshold). The sufficiency gate replaces this next step;
    # confidence now reads off the single-source-of-truth hypothesis rather than a scalar.
    confidence = state.hypothesis.confidence if state.hypothesis else 0.0
    if confidence >= CONFIDENCE_THRESHOLD:
        return "synthesize_report"
    if state.diagnose_iters >= MAX_DIAGNOSE_ITERS:  # circuit breaker
        return "escalate"
    return "diagnose"


def after_safety_validate(state: InvestigationState) -> str:
    # NOTE: still fails open (missing safety → proceed). Fail-closed routing + edit-revalidation
    # land together in the routing-hardening step; kept as-is here so this state migration is a
    # pure no-behavior-change refactor.
    safety = state.safety or {}
    return "hitl_gate" if safety.get("passed", True) else "escalate"


def after_approval(state: InvestigationState) -> str:
    decision = (state.approval or {}).get("decision")
    return "finalize_report" if decision in ("approve", "edit") else "escalate"
