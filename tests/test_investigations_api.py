"""Async investigation resource API — lifecycle, failure, idempotency, and unknown-id.

The advertised contract: `POST /investigations` → 202 + a polling URL, work runs in the background,
`GET /investigations/{id}` polls to a terminal state. With the TestClient a BackgroundTask runs to
completion before the POST call returns, so the POST observes the `queued` 202 snapshot while a
follow-up GET observes the terminal state. ML-free: the graph runs over an injected bm25
ToolService; a failure is forced with a service that raises.
"""

from __future__ import annotations

import pytest

pytest.importorskip("httpx")  # FastAPI's TestClient transport

from fastapi.testclient import TestClient  # noqa: E402

from opspilot.api import app, get_repository, get_service  # noqa: E402
from opspilot.investigations import InMemoryInvestigationRepository  # noqa: E402

client = TestClient(app)

_ALERT = {
    "incident_id": "inc-004",
    "summary": "checkout-api returning 500s shortly after this morning's deployment.",
}


def _bm25_service():
    from opspilot.retrieval.factory import build_retriever
    from opspilot.tools.service import ToolService

    return ToolService(retriever_factory=lambda: build_retriever("bm25", include_distractors=False))


class _BoomService:
    """First tool call the graph makes (triage's get_incident) raises — forces a run fault."""

    retrieval_backend = "bm25"

    def get_incident(self, **_):
        raise RuntimeError("repository down")


@pytest.fixture(autouse=True)
def _isolated_deps():
    # A fresh repository per test (the app's is a process singleton), cleared afterwards.
    repo = InMemoryInvestigationRepository()
    app.dependency_overrides[get_repository] = lambda: repo
    yield
    app.dependency_overrides.clear()


def _use_service(factory) -> None:
    app.dependency_overrides[get_service] = factory


def test_post_returns_202_with_id_status_and_poll_url():
    _use_service(_bm25_service)
    r = client.post("/investigations", json=_ALERT)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"  # the 202 snapshot, before the background task runs
    assert body["investigation_id"]
    assert body["poll_url"] == f"/investigations/{body['investigation_id']}"
    assert r.headers["location"] == body["poll_url"]  # 202 Location convention


def _approve(investigation_id: str, report_hash: str, **overrides) -> None:
    body = {
        "decision": "approve", "approver": "test-reviewer", "submitted_report_hash": report_hash,
    }
    body.update(overrides)
    r = client.post(f"/investigations/{investigation_id}/decision", json=body)
    assert r.status_code == 202, r.text


def test_lifecycle_queued_running_awaiting_approval_then_completed():
    _use_service(_bm25_service)
    posted = client.post("/investigations", json=_ALERT).json()
    r = client.get(posted["poll_url"])
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "awaiting_approval"  # real hitl_gate pause, not an auto-approved run
    assert body["history"] == ["queued", "running", "awaiting_approval"]
    assert body["result"] is None  # not terminal yet
    assert body["pending_decision"] and body["pending_decision"]["report_hash"]

    _approve(posted["investigation_id"], body["pending_decision"]["report_hash"])

    final = client.get(posted["poll_url"]).json()
    assert final["status"] == "completed"
    assert final["history"] == [
        "queued", "running", "awaiting_approval", "running", "completed",
    ]
    assert final["result"] and final["result"]["report"]["citations"]
    assert final["error"] is None
    assert final["pending_decision"] is None  # cleared once resolved


def test_failure_is_recorded_not_raised():
    _use_service(lambda: _BoomService())
    posted = client.post("/investigations", json=_ALERT)
    assert posted.status_code == 202  # accepting the work never 500s, even if the run will fault
    body = client.get(posted.json()["poll_url"]).json()
    assert body["status"] == "failed"
    assert body["history"] == ["queued", "running", "failed"]
    assert body["result"] is None
    assert body["error"]  # a sanitized, class-level reason — no stack trace


def test_idempotent_repeat_returns_the_same_investigation():
    _use_service(_bm25_service)
    first = client.post("/investigations", json=_ALERT).json()
    second = client.post("/investigations", json=_ALERT).json()
    assert first["investigation_id"] == second["investigation_id"]  # no duplicate run

    pending = client.get(second["poll_url"]).json()
    _approve(second["investigation_id"], pending["pending_decision"]["report_hash"])
    assert client.get(second["poll_url"]).json()["status"] == "completed"


def test_unknown_investigation_is_404():
    r = client.get("/investigations/does-not-exist")
    assert r.status_code == 404


def test_investigate_compatibility_endpoint_still_works():
    """The sync compatibility endpoint auto-resolves any hitl_gate pause itself — it must keep
    returning a complete terminal result inline, unlike the async job API."""
    _use_service(_bm25_service)
    r = client.post("/investigate", json=_ALERT)
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert r.json()["approval"]["kind"] == "deterministic_auto_approval"


# --- decision endpoint --------------------------------------------------------------------------
def test_decision_unknown_investigation_is_404():
    r = client.post(
        "/investigations/does-not-exist/decision",
        json={"decision": "approve", "approver": "x", "submitted_report_hash": "h"},
    )
    assert r.status_code == 404


def test_decision_against_a_resolved_investigation_is_409():
    _use_service(_bm25_service)
    posted = client.post("/investigations", json=_ALERT).json()
    pending = client.get(posted["poll_url"]).json()
    report_hash = pending["pending_decision"]["report_hash"]
    _approve(posted["investigation_id"], report_hash)  # resolves it -> completed

    body = {"decision": "approve", "approver": "x", "submitted_report_hash": report_hash}
    r = client.post(f"/investigations/{posted['investigation_id']}/decision", json=body)
    assert r.status_code == 409


def test_reject_decision_escalates():
    _use_service(_bm25_service)
    posted = client.post("/investigations", json=_ALERT).json()
    pending = client.get(posted["poll_url"]).json()
    report_hash = pending["pending_decision"]["report_hash"]

    r = client.post(
        f"/investigations/{posted['investigation_id']}/decision",
        json={"decision": "reject", "approver": "reviewer-1", "submitted_report_hash": report_hash},
    )
    assert r.status_code == 202

    final = client.get(posted["poll_url"]).json()
    assert final["status"] == "escalated"


def test_stale_hash_decision_is_rejected_and_escalates():
    _use_service(_bm25_service)
    posted = client.post("/investigations", json=_ALERT).json()
    client.get(posted["poll_url"])  # ensure it's paused before deciding

    r = client.post(
        f"/investigations/{posted['investigation_id']}/decision",
        json={"decision": "approve", "approver": "x", "submitted_report_hash": "not-the-real-hash"},
    )
    assert r.status_code == 202  # accepted for resume; the rejection happens inside the graph

    final = client.get(posted["poll_url"]).json()
    assert final["status"] == "escalated"


def test_edit_decision_re_pauses_with_a_new_hash_then_approves():
    _use_service(_bm25_service)
    posted = client.post("/investigations", json=_ALERT).json()
    pending = client.get(posted["poll_url"]).json()
    first_hash = pending["pending_decision"]["report_hash"]

    r = client.post(
        f"/investigations/{posted['investigation_id']}/decision",
        json={"decision": "edit", "approver": "reviewer-1", "submitted_report_hash": first_hash,
              "edits": {"recommended_next_step": "roll back the deploy"}},
    )
    assert r.status_code == 202

    repaused = client.get(posted["poll_url"]).json()
    assert repaused["status"] == "awaiting_approval"  # edit re-enters validation, never finalizes
    second_hash = repaused["pending_decision"]["report_hash"]
    assert second_hash != first_hash  # a different report, a new hash

    _approve(posted["investigation_id"], second_hash)
    final = client.get(posted["poll_url"]).json()
    assert final["status"] == "completed"
    assert final["result"]["report"]["recommended_next_step"] == "roll back the deploy"
