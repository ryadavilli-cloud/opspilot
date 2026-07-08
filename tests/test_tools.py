"""Contract tests for the Phase 3 deterministic tools.

Covers the required surface: success, unknown, empty, invalid window, unknown service,
deterministic ordering, schema validity, malformed-data handling, metadata, refs resolve, and the
allowlisted dispatcher. Runs against the real corpus except where a hand-built repository is needed
to inject edge cases.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from opspilot.data.repository import Repository
from opspilot.tools.contracts import DeploymentRecord, IncidentRecord
from opspilot.tools.service import ToolService

REPO_ROOT = Path(__file__).resolve().parents[1]
SVC = ToolService()

DEPLOY_IDS = {
    d["deploy_id"]
    for d in json.loads((REPO_ROOT / "data/synthetic/deployments.json").read_text())["deployments"]
}


def _dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)


# --- get_incident -----------------------------------------------------------------------------
def test_get_incident_success():
    r = SVC.get_incident(incident_id="inc-001")
    assert r.status == "ok" and len(r.results) == 1
    assert isinstance(r.results[0], IncidentRecord) and r.results[0].incident_id == "inc-001"
    assert r.metadata.result_count == 1 and r.metadata.duration_ms >= 0


def test_get_incident_unknown_is_empty_not_error():
    r = SVC.get_incident(incident_id="inc-999")
    assert r.status == "ok" and r.results == [] and r.error is None


def test_get_incident_invalid_input_is_error():
    r = SVC.get_incident(incident_id="")
    assert r.status == "error" and r.error and "invalid request" in r.error


def test_known_error_incident_yields_past_incident_ref():
    r = SVC.get_incident(incident_id="inc-001")  # historical -> known error
    assert r.evidence_refs == ["past_incident:inc-001"]


# --- get_correlated_alerts --------------------------------------------------------------------
def test_correlated_alerts_returns_storm():
    r = SVC.get_correlated_alerts(incident_id="inc-004")
    assert r.status == "ok" and len(r.results) >= 2
    assert "root_cause" in {a.role for a in r.results}
    assert sum(a.is_trigger for a in r.results) == 1


def test_correlated_alerts_unknown_incident_empty():
    r = SVC.get_correlated_alerts(incident_id="inc-999")
    assert r.status == "ok" and r.results == []


def test_correlated_alerts_bad_window_is_error():
    r = SVC.get_correlated_alerts(
        incident_id="inc-004", start_time=_dt("2026-02-01"), end_time=_dt("2026-01-01")
    )
    assert r.status == "error"


# --- get_deployments --------------------------------------------------------------------------
def test_get_deployments_success_and_refs_resolve():
    r = SVC.get_deployments(services=["checkout-api"], start_time=_dt("2026-06-01"),
                            end_time=_dt("2026-06-30"))
    assert r.status == "ok" and r.results
    for rec, ref in zip(r.results, r.evidence_refs, strict=True):
        assert ref == f"deploys:{rec.service}:{rec.deploy_id}"
        assert rec.deploy_id in DEPLOY_IDS  # ref resolves to a real corpus row


def test_get_deployments_unknown_service_empty():
    r = SVC.get_deployments(services=["nope-api"], start_time=_dt("2026-06-01"),
                            end_time=_dt("2026-06-30"))
    assert r.status == "ok" and r.results == []


def test_get_deployments_invalid_and_oversized_window_are_errors():
    end_before_start = SVC.get_deployments(services=["checkout-api"], start_time=_dt("2026-06-30"),
                                           end_time=_dt("2026-06-01"))
    oversized = SVC.get_deployments(services=["checkout-api"], start_time=_dt("2026-01-01"),
                                    end_time=_dt("2026-12-31"))
    assert end_before_start.status == "error"
    assert oversized.status == "error"  # > MAX_WINDOW_DAYS


def test_get_deployments_deterministic_ordering():
    scrambled = Repository.from_records(deployments=[
        {"deploy_id": "d-2", "service": "checkout-api", "ts": "2026-06-20T00:00:00Z",
         "version": "v2", "note": ""},
        {"deploy_id": "d-1", "service": "checkout-api", "ts": "2026-06-10T00:00:00Z",
         "version": "v1", "note": ""},
    ])
    r = ToolService(scrambled).get_deployments(
        services=["checkout-api"], start_time=_dt("2026-06-01"), end_time=_dt("2026-06-30"))
    assert [d.deploy_id for d in r.results] == ["d-1", "d-2"]  # sorted by ts


def test_malformed_row_is_skipped_not_fatal():
    repo = Repository.from_records(deployments=[
        {"deploy_id": "ok", "service": "checkout-api", "ts": "2026-06-10T00:00:00Z",
         "version": "v", "note": ""},
        {"deploy_id": "bad", "service": "checkout-api"},  # missing ts/version/note
    ])
    r = ToolService(repo).get_deployments(services=["checkout-api"], start_time=_dt("2026-06-01"),
                                          end_time=_dt("2026-06-30"))
    assert r.status == "ok" and [d.deploy_id for d in r.results] == ["ok"]


def test_results_are_typed():
    r = SVC.get_deployments(services=["checkout-api"], start_time=_dt("2026-06-01"),
                            end_time=_dt("2026-06-30"))
    assert all(isinstance(d, DeploymentRecord) for d in r.results)


# --- dispatcher -------------------------------------------------------------------------------
def test_call_dispatcher_allowlist():
    assert SVC.call("get_incident", incident_id="inc-001").status == "ok"
    denied = SVC.call("delete_everything", target="prod")
    assert denied.status == "error" and denied.error == "unknown tool"
