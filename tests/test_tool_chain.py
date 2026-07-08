"""Answer-key chain test — the Phase 3 quality proof.

Runs the deterministic investigation path end to end, with NO LLM:

    get_incident -> get_correlated_alerts -> (affected services + onset) -> get_deployments

and asserts that the deployment evidence the *answer key* expects for each scenario is actually
surfaced. The expected refs come from the scenarios, not hard-coded here — so this fails if the
tools, the corpus, or the answer key drift apart.
"""

from __future__ import annotations

import importlib.util
from datetime import timedelta
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

DEPLOY_SCENARIOS = [
    s for s in SCENARIOS if any(r.startswith("deploys:") for r in s["expected_evidence"])
]


@pytest.mark.parametrize("scenario", DEPLOY_SCENARIOS, ids=lambda s: s["id"])
def test_chain_reconstructs_expected_deploy_evidence(scenario):
    incident_id = scenario["id"]

    incident = SVC.get_incident(incident_id=incident_id)
    assert incident.status == "ok" and incident.results, f"{incident_id}: no incident"
    opened_at = to_utc(incident.results[0].opened_at)

    alerts = SVC.get_correlated_alerts(incident_id=incident_id)
    assert alerts.status == "ok" and alerts.results, f"{incident_id}: no alert storm"
    affected_services = sorted({a.service for a in alerts.results})

    # Deployments in the window leading up to onset — "what changed" before the incident.
    deploys = SVC.get_deployments(
        services=affected_services,
        start_time=opened_at - timedelta(hours=24),
        end_time=opened_at + timedelta(minutes=15),
    )
    assert deploys.status == "ok"

    expected = [r for r in scenario["expected_evidence"] if r.startswith("deploys:")]
    for ref in expected:
        assert ref in deploys.evidence_refs, (
            f"{incident_id}: chain did not surface expected deploy {ref} "
            f"(services={affected_services}, got={deploys.evidence_refs})"
        )
