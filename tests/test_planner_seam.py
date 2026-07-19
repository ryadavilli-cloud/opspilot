"""Planner seam + dispatch (Stage 4a) — no ML stack.

The deterministic planner behind the seam must be identical to calling `plan_investigation`
directly (the no-behavior-change guarantee), the `diagnose` node must route through the injected
planner, and an unknown implementation must fail loud rather than silently run the floor.
"""

from __future__ import annotations

import pytest

from opspilot.diagnosis.contracts import DiagnosisContext
from opspilot.diagnosis.cycle import plan_investigation
from opspilot.diagnosis.planner import DeterministicPlanner, build_planner
from opspilot.nodes.investigation import _planner, diagnose
from opspilot.state import InvestigationState
from opspilot.tools.service import ToolService

CTX = DiagnosisContext(
    incident_id="inc-004",
    affected_services=["checkout-api"],
    onset="2026-06-28T10:15:00+00:00",
    category="payment",
)


def test_deterministic_planner_matches_direct_call():
    seam = DeterministicPlanner().plan(CTX, answered=set(), observations=[])
    direct = plan_investigation(CTX)
    assert seam.model_dump() == direct.model_dump()


def test_deterministic_planner_ignores_loop_state():
    # answered/observations must not change the emitted plan — run_cycle handles skipping, so the
    # plan itself stays static (this is what makes the seam byte-identical to the old direct call).
    with_state = DeterministicPlanner().plan(CTX, answered={"deployments"}, observations=[])
    without = DeterministicPlanner().plan(CTX, answered=set(), observations=[])
    assert with_state.model_dump() == without.model_dump()


def test_build_planner_known_and_unknown():
    assert isinstance(build_planner("deterministic"), DeterministicPlanner)
    # single_agent builds the LLM planner (no network at construction — the client is lazy).
    assert build_planner("single_agent").name == "single_agent"
    with pytest.raises(ValueError, match="unknown diagnosis implementation"):
        build_planner("nope")


def test_resolver_defaults_and_injection():
    assert isinstance(_planner(None), DeterministicPlanner)
    assert isinstance(_planner({}), DeterministicPlanner)
    sentinel = object()
    assert _planner({"configurable": {"planner": sentinel}}) is sentinel


def test_node_routes_through_injected_planner():
    calls: list[str] = []

    class SpyPlanner(DeterministicPlanner):
        def plan(self, ctx, *, answered, observations):
            calls.append(ctx.incident_id)
            return super().plan(ctx, answered=answered, observations=observations)

    state = InvestigationState(
        incident_id="inc-004",
        affected_services=["checkout-api"],
        onset="2026-06-28T10:15:00+00:00",
        severity="SEV1",
        category="payment",
    )
    config = {"configurable": {"tool_service": ToolService(), "planner": SpyPlanner()}}
    out = diagnose(state, config)
    assert calls == ["inc-004"]  # the node went through the seam, not a direct plan call
    assert out["hypothesis"] is not None
