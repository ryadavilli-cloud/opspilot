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


def test_all_six_scenarios_run_through_the_slice(scorecard):
    assert scorecard["n_scenarios"] == 6


def test_no_material_regression_vs_baseline(scorecard):
    for metric in ("routing_accuracy", "category_accuracy", "evidence_recall",
                   "tool_call_validity", "iteration_limit_compliance"):
        assert scorecard[metric] >= BASELINE[metric] - EPS, (
            f"{metric} regressed: {scorecard[metric]} < baseline {BASELINE[metric]}")
    assert scorecard["unsupported_evidence_rate"] <= BASELINE["unsupported_evidence_rate"] + EPS
    assert scorecard["mcp_parity"] is True is BASELINE["mcp_parity"]
