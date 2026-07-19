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
    """Stop rule. The planner decides when to stop *gathering* (an exhausted plan — the model said
    `done` or has nothing new to run); code decides whether that stop is *legitimate* — synthesize
    only when the deterministic sufficiency gate is satisfied, else escalate with a reason. The
    iteration budget is the circuit breaker. While the plan can still advance and budget remains,
    the loop keeps gathering even once coverage is met, so a dependency-chain investigation can dive
    into the implicated service rather than stopping at first sufficiency."""
    s = state.sufficiency
    ready = s is not None and s.ready
    plan_exhausted = s is not None and not s.plan_can_advance
    if plan_exhausted or state.diagnose_iters >= MAX_DIAGNOSE_ITERS:
        return "synthesize_report" if ready else "escalate"
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
