"""Contract tests for the deterministic tools.

Covers the required surface: success, unknown, empty, invalid window, unknown service,
deterministic ordering, schema validity, malformed-data handling, metadata, refs resolve, and the
allowlisted dispatcher. Runs against the authored corpus, container-shaped, except where
hand-built documents are needed to inject edge cases.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fake_operational_records import corpus_records, deployment_documents, records_from

from opspilot.tools.contracts import (
    Completeness,
    DeploymentRecord,
    ExecutionOutcome,
)
from opspilot.tools.service import ToolService

REPO_ROOT = Path(__file__).resolve().parents[1]
SVC = ToolService(corpus_records())

DEPLOY_IDS = {
    d["deploy_id"]
    for d in json.loads((REPO_ROOT / "data/synthetic/deployments.json").read_text())["deployments"]
}


def _dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)


# --- get_incident -----------------------------------------------------------------------------
def test_get_incident_success():
    r = SVC.get_incident(incident_id="inc-001")
    assert r.outcome is ExecutionOutcome.SUCCEEDED and r.completeness is Completeness.COMPLETE
    assert len(r.results) == 1
    assert r.results[0]["incident_id"] == "inc-001"
    assert r.metadata.result_count == 1 and r.metadata.duration_ms >= 0


def test_get_incident_unknown_is_empty_not_error():
    r = SVC.get_incident(incident_id="inc-999")
    assert r.outcome is ExecutionOutcome.SUCCEEDED and r.completeness is Completeness.EMPTY
    assert r.results == [] and r.error is None


def test_get_incident_invalid_input_is_error():
    r = SVC.get_incident(incident_id="")
    assert r.outcome is ExecutionOutcome.REJECTED
    assert r.completeness is Completeness.NOT_APPLICABLE
    assert r.error and "invalid request" in r.error


def test_the_incident_is_cited_as_the_record_it_is():
    """The incident record is an operational observation about this incident, so its citation names
    the record. Pointing at the postmortem instead would let a document stand as current proof."""
    r = SVC.get_incident(incident_id="inc-001")
    assert r.evidence_refs == ["incident:inc-001"]


def test_the_incident_record_reaches_the_caller_without_its_stored_answers():
    """The corpus carries its own root cause and resolution. Narrowing to the approved surface here
    is what makes them unreachable rather than merely unread."""
    fields = set(SVC.get_incident(incident_id="inc-001").results[0])
    assert {"incident_id", "category", "priority", "opened_at", "state"} <= fields
    assert fields.isdisjoint({"root_cause", "resolution", "close_code", "short_description"})


# --- get_correlated_alerts --------------------------------------------------------------------
def test_correlated_alerts_returns_storm():
    r = SVC.get_correlated_alerts(incident_id="inc-004")
    assert r.outcome is ExecutionOutcome.SUCCEEDED and r.completeness is Completeness.COMPLETE
    assert len(r.results) >= 2
    assert "root_cause" in {a.role for a in r.results}
    assert sum(a.is_trigger for a in r.results) == 1


def test_correlated_alerts_are_cited_as_the_alerts_they_are():
    """An alert is an observation of the running system at a moment, so it is citable like a log
    line. Returning the storm uncited would make the entities it names unusable as support."""
    r = SVC.get_correlated_alerts(incident_id="inc-004")
    assert r.results
    assert r.evidence_refs == [f"alert:{a.service}:{a.alert_id}" for a in r.results]


def test_correlated_alerts_unknown_incident_empty():
    r = SVC.get_correlated_alerts(incident_id="inc-999")
    assert r.outcome is ExecutionOutcome.SUCCEEDED and r.completeness is Completeness.EMPTY
    assert r.results == []


def test_correlated_alerts_bad_window_is_error():
    r = SVC.get_correlated_alerts(
        incident_id="inc-004", start_time=_dt("2026-02-01"), end_time=_dt("2026-01-01")
    )
    assert r.outcome is ExecutionOutcome.REJECTED


# --- get_deployments --------------------------------------------------------------------------
def test_get_deployments_success_and_refs_resolve():
    r = SVC.get_deployments(
        services=["checkout-api"], start_time=_dt("2026-06-01"), end_time=_dt("2026-06-30")
    )
    assert r.outcome is ExecutionOutcome.SUCCEEDED and r.results
    for rec, ref in zip(r.results, r.evidence_refs, strict=True):
        assert ref == f"deploys:{rec.service}:{rec.deploy_id}"
        assert rec.deploy_id in DEPLOY_IDS  # ref resolves to a real corpus row


def test_get_deployments_unknown_service_empty():
    r = SVC.get_deployments(
        services=["nope-api"], start_time=_dt("2026-06-01"), end_time=_dt("2026-06-30")
    )
    assert r.outcome is ExecutionOutcome.SUCCEEDED and r.completeness is Completeness.EMPTY
    assert r.results == []


def test_get_deployments_invalid_and_oversized_window_are_errors():
    end_before_start = SVC.get_deployments(
        services=["checkout-api"], start_time=_dt("2026-06-30"), end_time=_dt("2026-06-01")
    )
    oversized = SVC.get_deployments(
        services=["checkout-api"], start_time=_dt("2026-01-01"), end_time=_dt("2026-12-31")
    )
    assert end_before_start.outcome is ExecutionOutcome.REJECTED
    assert oversized.outcome is ExecutionOutcome.REJECTED  # > MAX_WINDOW_DAYS


def test_get_deployments_deterministic_ordering():
    scrambled = records_from(
        deployment_documents(
            [
                {
                    "deploy_id": "d-2",
                    "service": "checkout-api",
                    "ts": "2026-06-20T00:00:00Z",
                    "version": "v2",
                    "note": "",
                },
                {
                    "deploy_id": "d-1",
                    "service": "checkout-api",
                    "ts": "2026-06-10T00:00:00Z",
                    "version": "v1",
                    "note": "",
                },
            ]
        )
    )
    r = ToolService(scrambled).get_deployments(
        services=["checkout-api"], start_time=_dt("2026-06-01"), end_time=_dt("2026-06-30")
    )
    assert [d.deploy_id for d in r.results] == ["d-1", "d-2"]  # sorted by ts


def test_malformed_row_is_skipped_not_fatal():
    records = records_from(
        deployment_documents(
            [
                {
                    "deploy_id": "ok",
                    "service": "checkout-api",
                    "ts": "2026-06-10T00:00:00Z",
                    "version": "v",
                    "note": "",
                },
                {"deploy_id": "bad", "service": "checkout-api"},  # missing ts/version/note
            ]
        )
    )
    r = ToolService(records).get_deployments(
        services=["checkout-api"], start_time=_dt("2026-06-01"), end_time=_dt("2026-06-30")
    )
    assert r.outcome is ExecutionOutcome.SUCCEEDED
    assert [d.deploy_id for d in r.results] == ["ok"]


def test_results_are_typed():
    r = SVC.get_deployments(
        services=["checkout-api"], start_time=_dt("2026-06-01"), end_time=_dt("2026-06-30")
    )
    assert all(isinstance(d, DeploymentRecord) for d in r.results)


# --- dispatcher -------------------------------------------------------------------------------
def test_call_dispatcher_allowlist():
    assert SVC.call("get_incident", incident_id="inc-001").answered
    denied = SVC.call("delete_everything", target="prod")
    assert denied.outcome is ExecutionOutcome.REJECTED and denied.error == "unknown tool"
