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
from opspilot.tools.service import ToolService  # noqa: E402


def _front(inc_id: str, summary: str) -> dict:
    state: dict = {"alert": {"incident_id": inc_id, "summary": summary}}
    state.update(ingest(state))
    state.update(triage_router(state))
    state.update(diagnose(state))
    return state


def test_deployment_hypothesis_from_real_observations():
    s = _front("inc-006", "Reservation conflicts and oversells at checkout.")
    assert "deployment" in s["hypothesis"].lower()
    assert 0.0 < s["confidence"] <= 1.0
    assert s["evidence"]  # explicit supporting evidence
    # the causal deploy is surfaced and cited
    assert "deploys:inventory-api:dep-20260625-01" in s["retrieved_sources"]
    diag = s["diagnosis"]
    assert diag["observations"] and diag["stop_reason"]["reason"] == "hypothesis_supported"


def test_every_citation_is_backed_by_a_run_observation():
    s = _front("inc-006", "Reservation conflicts and oversells at checkout.")
    observed = {ref for o in s["diagnosis"]["observations"] for ref in o["evidence_refs"]}
    for citation in s["diagnosis"]["hypothesis"]["citations"]:
        assert citation["ref"] in observed, f"{citation['ref']} was not produced this run"


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
    assert a["hypothesis"] == b["hypothesis"]
    assert a["retrieved_sources"] == b["retrieved_sources"]
    assert a["confidence"] == b["confidence"]
