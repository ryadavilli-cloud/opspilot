"""RCAEval wild-slice harness (Stage 4d) — no ML stack; runs against a committed OB fixture.

The real generalization probe needs the gitignored RE1-OB data (see eval/record_wild.py); these
tests exercise the adapter, corpus, and scoring on a tiny synthetic fixture so CI can verify the
harness end to end without it.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "wild_ob"
sys.path.insert(0, str(REPO_ROOT / "eval"))

import wild  # noqa: E402


def test_load_cases_from_fixture():
    cases = wild.load_cases(FIXTURE)
    by_root = {c.root_service: c for c in cases}
    assert set(by_root) == {"cartservice", "paymentservice"}
    cart = by_root["cartservice"]
    assert cart.fault_type == "cpu"
    assert "cartservice" in cart.services
    # the metric series carry real values — the model must be able to SEE the injected anomaly
    cpu = [s for s in cart.metric_series if s["service"] == "cartservice" and s["metric"] == "cpu"]
    assert cpu and max(sp["value"] for sp in cpu[0]["samples"]) > 80


def test_build_wild_repository_is_queryable():
    from opspilot.tools.service import ToolService

    case = wild.load_cases(FIXTURE)[0]
    svc = ToolService(repo=wild.build_wild_repository([case]), retriever_factory=wild._NoRetriever)
    result = svc.call("get_metrics", service=case.root_service)
    assert result.status == "ok" and result.results  # the tools query the converted wild corpus


def _hyp(refs: list[str]):
    return type("H", (), {"citations": [type("C", (), {"ref": r})() for r in refs]})()


def test_implicated_prefers_metric_then_dep_toside():
    assert wild._implicated_service({"hypothesis": _hyp(["metrics:cartservice:cpu@t"])}) == \
        "cartservice"
    # a dependency-star citation resolves to the TO side (the from side is the synthetic entry)
    assert wild._implicated_service({"hypothesis": _hyp(["deps:frontend-lb->paymentservice"])}) == \
        "paymentservice"
    assert wild._implicated_service({"hypothesis": None}) is None


def test_deterministic_harness_runs_end_to_end():
    # The harness runs the real graph; the deterministic planner does not generalize to OB (its
    # trigger has no metrics), so it grounds nothing -> rca 0.0. This pins that the plumbing works.
    scorecard = wild.evaluate_wild("deterministic", cache_dir=FIXTURE)
    assert scorecard["n_cases"] == 2
    assert scorecard["rca_correctness"] == 0.0
