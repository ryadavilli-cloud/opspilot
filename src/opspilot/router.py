"""Conditional routing functions for the investigation graph.

These are the deterministic skeleton: stage order is fixed code, auditable and testable. Routers
are pure functions over the typed state and fail closed — a missing input routes to the safe branch.
The stop rule is the deterministic sufficiency gate (code decides when the agent may stop);
hypothesis confidence is a recorded input, never the trigger.
"""

from __future__ import annotations

from opspilot.config import MAX_DIAGNOSE_ITERS
from opspilot.state import Intent, InvestigationState


def route_by_intent(state: InvestigationState) -> str:
    if state.intent == Intent.INFO_ONLY.value:
        return "synthesize_report"          # informational reply (exempt from the citation gate)
    if state.intent == Intent.KNOWN_ISSUE.value and state.matched_incident:
        return "known_issue_fast_path"      # short-circuit to the stored resolution
    return "retrieve"                        # novel → full investigation


def diagnose_continue(state: InvestigationState) -> str:
    """Deterministic sufficiency gate: the agent may stop only when code says the evidence is
    sufficient. Exhausting the iteration budget or the plan escalates with a reason, never spins."""
    s = state.sufficiency
    if s is not None and s.ready:
        return "synthesize_report"
    if state.diagnose_iters >= MAX_DIAGNOSE_ITERS:   # circuit breaker
        return "escalate"
    if s is not None and not s.plan_can_advance:      # no unanswered questions remain
        return "escalate"
    return "diagnose"


def after_safety_validate(state: InvestigationState) -> str:
    # Fail closed: missing or unset safety state routes to escalate, not review.
    safety = state.safety
    return "hitl_gate" if (safety is not None and safety.get("passed") is True) else "escalate"


def after_approval(state: InvestigationState) -> str:
    # An edit re-enters validation (apply_edit -> safety_validate -> re-approve); it never
    # shortcuts to finalize. reject / request_more_evidence / a missing decision fail closed.
    decision = (state.approval or {}).get("decision")
    if decision == "approve":
        return "finalize_report"
    if decision == "edit":
        return "apply_edit"
    return "escalate"
