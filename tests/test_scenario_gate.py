"""Step 5 gate: the connected slice scored against a versioned baseline (CI fails on regression).

Runs all six scenarios end to end and asserts no material regression vs eval/baselines/
slice_baseline.json. Skipped without the retrieval extras.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("sentence_transformers")
pytest.importorskip("rank_bm25")

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads((REPO_ROOT / "eval/baselines/slice_baseline.json").read_text())
EPS = 0.01

_spec = importlib.util.spec_from_file_location("scenario_eval", REPO_ROOT / "eval/scenario_eval.py")
assert _spec and _spec.loader
scenario_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scenario_eval)


@pytest.fixture(scope="module")
def scorecard() -> dict:
    return scenario_eval.evaluate()


def test_all_scenarios_run_through_the_slice(scorecard):
    assert scorecard["n_scenarios"] == 7


def test_no_material_regression_vs_baseline(scorecard):
    for metric in ("routing_accuracy", "category_accuracy", "evidence_recall",
                   "rca_correctness", "tool_call_validity", "iteration_limit_compliance"):
        assert scorecard[metric] >= BASELINE[metric] - EPS, (
            f"{metric} regressed: {scorecard[metric]} < baseline {BASELINE[metric]}")
    assert scorecard["unsupported_evidence_rate"] <= BASELINE["unsupported_evidence_rate"] + EPS
    assert scorecard["mcp_parity"] is True is BASELINE["mcp_parity"]


def _run_scenario(inc_id: str) -> dict:
    from opspilot.graph import _initial_state, build_graph
    from opspilot.tools.service import ToolService

    by_id = {s["id"]: s for s in scenario_eval._load_scenarios()}
    root = {i: (s.get("impacted_chain") or [None])[0] for i, s in by_id.items()}
    state = build_graph().invoke(
        _initial_state({"incident_id": inc_id, "summary": by_id[inc_id]["alert"]["summary"]}),
        config={"configurable": {"tool_service": ToolService()}})
    return scenario_eval._score_one(by_id[inc_id], state, root)


def test_red_herring_is_grounded_but_scored_wrong():
    """inc-004: the deterministic slice cites real evidence (unsupported_rate 0) but names the
    coincidental deploy as the root -> rca_correct 0. Grounding and correctness are separate axes;
    this is the honest floor the LLM diagnosis loop must beat."""
    s = _run_scenario("inc-004")
    assert s["unsupported_rate"] == 0.0   # every citation is real (grounded)
    assert s["rca_correct"] == 0.0        # but the named root is wrong (the red herring)


def test_true_deploy_regression_is_scored_correct():
    assert _run_scenario("inc-006")["rca_correct"] == 1.0
