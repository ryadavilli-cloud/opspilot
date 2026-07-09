"""The full-coverage proof: the tool set surfaces every scenario's expected evidence.

For each scenario, each `expected_evidence` ref is routed to the tool that owns its source
(logs → query_logs, metrics → get_metrics, deploys → get_deployments, deps →
get_service_dependencies) and asserted to appear in that tool's `evidence_refs`. The expected refs
come from the answer key, so this fails if the tools, the corpus, or the labels drift apart — the
end-to-end proof that the tools can reach the labeled evidence with no LLM involved.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from opspilot.tools.contracts import to_utc
from opspilot.tools.service import ToolService

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SCENARIOS = _load("build_goldens", "data/answer_key/build_goldens.py").load_scenarios()
SVC = ToolService()


def _center(scenario) -> datetime:
    oa = scenario["occurred_at"]
    if not isinstance(oa, datetime):
        oa = datetime.strptime(oa, "%Y-%m-%dT%H:%M:%SZ")
    return to_utc(oa)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["id"])
def test_all_expected_evidence_is_surfaced(scenario):
    center = _center(scenario)
    w_start, w_end = center - timedelta(minutes=30), center + timedelta(minutes=30)
    dep_start = center - timedelta(hours=24)

    for ref in scenario["expected_evidence"]:
        source, rest = ref.split(":", 1)
        if source == "logs":
            svc = rest.split(":", 1)[0]
            refs = SVC.query_logs(service=svc, start_time=w_start, end_time=w_end).evidence_refs
        elif source == "metrics":
            svc = rest.split(":", 1)[0]
            refs = SVC.get_metrics(service=svc, start_time=w_start, end_time=w_end).evidence_refs
        elif source == "deploys":
            svc = rest.split(":", 1)[0]
            refs = SVC.get_deployments(
                services=[svc], start_time=dep_start, end_time=w_end).evidence_refs
        elif source == "deps":
            frm = rest.split("->", 1)[0]
            refs = SVC.get_service_dependencies(service=frm).evidence_refs
        else:
            refs = []
        assert ref in refs, f"{scenario['id']}: {source} tool did not surface {ref}"
