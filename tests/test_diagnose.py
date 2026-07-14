"""Step 3 gate: one deterministic diagnostic cycle produces a grounded hypothesis.

Skipped without the retrieval extras (triage, which seeds the cycle's context, uses retrieval).
Covers: a hypothesis from real tool observations, every citation backed by a run observation, the
hard iteration limit, and determinism.
"""

from __future__ import annotations

import pytest

pytest.importorskip("sentence_transformers")
pytest.importorskip("rank_bm25")

from opspilot.diagnosis.contracts import (  # noqa: E402
    DiagnosisContext,
    DiagnosticQuestion,
    InvestigationPlan,
    ToolCallRequest,
)
from opspilot.diagnosis.cycle import run_cycle  # noqa: E402
from opspilot.nodes.investigation import diagnose, ingest, triage_router  # noqa: E402
from opspilot.state import InvestigationState  # noqa: E402
from opspilot.tools.service import ToolService  # noqa: E402


def _front(inc_id: str, summary: str) -> InvestigationState:
    state = InvestigationState(alert={"incident_id": inc_id, "summary": summary})
    state = state.model_copy(update=ingest(state))
    state = state.model_copy(update=triage_router(state))
    state = state.model_copy(update=diagnose(state))
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
            DiagnosticQuestion(question=f"q{i}",
                               call=ToolCallRequest(tool="get_service_dependencies"))
            for i in range(5)
        ],
    )
    ctx = DiagnosisContext(incident_id="inc-006", onset="2026-06-25T16:20:00+00:00")
    _, observations, stop = run_cycle(ToolService(), ctx, plan)
    assert len(observations) == 2 and stop.reason == "iteration_limit"


def test_diagnosis_is_deterministic():
    a = _front("inc-006", "Reservation conflicts and oversells at checkout.")
    b = _front("inc-006", "Reservation conflicts and oversells at checkout.")
    assert a.hypothesis and b.hypothesis
    assert a.hypothesis.statement == b.hypothesis.statement
    assert a.evidence_refs() == b.evidence_refs()
    assert a.hypothesis.confidence == b.hypothesis.confidence
