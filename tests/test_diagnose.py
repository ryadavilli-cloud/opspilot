"""Step 3 gate: one deterministic diagnostic cycle produces a grounded hypothesis.

Retrieval runs over a fake Cosmos container (triage, which seeds the cycle's context, uses
retrieval), so this needs no live Azure dependency. Covers: a hypothesis from real tool
observations, every citation backed by a run observation, the hard iteration limit, and
determinism.
"""

from __future__ import annotations

from fake_knowledge import knowledge_retriever
from fake_operational_records import corpus_records

from opspilot.diagnosis.contracts import (
    DiagnosisContext,
    DiagnosticQuestion,
    InvestigationPlan,
    ToolCallRequest,
)
from opspilot.diagnosis.cycle import plan_investigation, run_cycle
from opspilot.nodes.investigation import diagnose, ingest, triage_router
from opspilot.state import InvestigationState
from opspilot.tools.service import ToolService


def _service() -> ToolService:
    return ToolService(corpus_records(), retriever_factory=knowledge_retriever)


def _front(inc_id: str, summary: str) -> InvestigationState:
    # One service for the whole investigation, injected through every node that resolves one.
    # A node called without it falls back to the deployed default, which reaches Cosmos.
    config = {"configurable": {"tool_service": _service()}}
    state = InvestigationState(alert={"incident_id": inc_id, "summary": summary})
    state = state.model_copy(update=ingest(state))
    state = state.model_copy(update=triage_router(state, config))
    state = state.model_copy(update=diagnose(state, config))
    return state


def test_deployment_hypothesis_from_real_observations():
    s = _front("inc-006", "Reservation conflicts and oversells at checkout.")
    assert s.hypothesis and "deployment" in s.hypothesis.statement.lower()
    assert 0.0 < s.hypothesis.confidence <= 1.0
    assert s.evidence_by_id  # explicit supporting evidence
    # the causal deploy is surfaced and cited
    assert "deploys:inventory-api:dep-20260625-01" in s.evidence_refs()
    assert s.diagnosis and s.diagnosis.observations
    assert s.diagnosis.stop_reason and s.diagnosis.stop_reason.reason == "hypothesis_supported"


def test_every_citation_is_backed_by_a_run_observation():
    s = _front("inc-006", "Reservation conflicts and oversells at checkout.")
    assert s.diagnosis and s.hypothesis
    observed = {ref for o in s.diagnosis.observations for ref in o.evidence_refs}
    for citation in s.hypothesis.citations:
        assert citation.ref in observed, f"{citation.ref} was not produced this run"


def test_loop_obeys_hard_iteration_limit():
    plan = InvestigationPlan(
        max_iters=2,
        questions=[
            DiagnosticQuestion(
                key=f"q{i}", question=f"q{i}", call=ToolCallRequest(tool="get_service_dependencies")
            )
            for i in range(5)
        ],
    )
    ctx = DiagnosisContext(incident_id="inc-006", onset="2026-06-25T16:20:00+00:00")
    _, observations, stop, _ = run_cycle(_service(), ctx, plan)
    assert len(observations) == 2 and stop.reason == "iteration_limit"


def test_novel_scenario_reaches_sufficiency_with_counter_evidence():
    s = _front("inc-006", "Reservation conflicts and oversells at checkout.")
    assert s.sufficiency is not None and s.sufficiency.ready
    assert s.sufficiency.evidence_coverage == 1.0
    # the counter-evidence questions gathered dependency + metric classes, not just deploys/logs
    classes = set(s.sufficiency.evidence_classes)
    assert {"deps", "metrics"} <= classes, classes


def test_plan_advancement_does_not_reask_answered_questions():
    ctx = DiagnosisContext(
        incident_id="inc-006", affected_services=["checkout-api"], onset="2026-06-25T16:20:00+00:00"
    )
    plan = plan_investigation(ctx)
    svc = _service()
    _, obs1, _, answered1 = run_cycle(svc, ctx, plan)
    assert obs1 and answered1 == {q.key for q in plan.questions}  # first pass answers everything
    _, obs2, _, answered2 = run_cycle(svc, ctx, plan, answered=answered1)
    assert obs2 == [] and answered2 == set()  # re-entry re-asks nothing (no spin)


def test_diagnosis_is_deterministic():
    a = _front("inc-006", "Reservation conflicts and oversells at checkout.")
    b = _front("inc-006", "Reservation conflicts and oversells at checkout.")
    assert a.hypothesis and b.hypothesis
    assert a.hypothesis.statement == b.hypothesis.statement
    assert a.evidence_refs() == b.evidence_refs()
    assert a.hypothesis.confidence == b.hypothesis.confidence
