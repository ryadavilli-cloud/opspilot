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

from opspilot.api import app, get_authenticator, get_repository, get_service  # noqa: E402
from opspilot.auth import ReviewerAuthError, ReviewerPrincipal  # noqa: E402
from opspilot.investigations import InMemoryInvestigationRepository  # noqa: E402

client = TestClient(app)

_ALERT = {
    "incident_id": "inc-004",
    "summary": "checkout-api returning 500s shortly after this morning's deployment.",
}

# Reviewer identities, keyed by bearer token (G-01). Token *validation* is covered against real
# RS256 signatures in `test_auth.py`; this fake exists so these lifecycle tests exercise the
# endpoint's behaviour — which principal reaches the approval record, and which HTTP status an
# unproven or unauthorized caller gets — without minting a JWT per request.
_HUMAN = ReviewerPrincipal(
    subject="oid-human-1", tenant_id="test-tenant", display_name="reviewer@example.com",
    roles=("Approver",), auth_method="entra_jwt",
)
_SERVICE = ReviewerPrincipal(
    subject="oid-smoke-sp", tenant_id="test-tenant", display_name="opspilot-smoke",
    roles=("Approver",), auth_method="service_principal",
)
_PRINCIPALS = {"human-token": _HUMAN, "app-token": _SERVICE}

HUMAN_AUTH = {"Authorization": "Bearer human-token"}
SERVICE_AUTH = {"Authorization": "Bearer app-token"}


class _FakeAuthenticator:
    """Same contract as `EntraJwtAuthenticator`, same fail-closed shape: an unknown or absent token
    raises rather than falling back to a default principal."""

    def authenticate(self, authorization_header: str | None) -> ReviewerPrincipal:
        if not authorization_header or not authorization_header.lower().startswith("bearer "):
            raise ReviewerAuthError("an Authorization header is required")
        token = authorization_header.split(" ", 1)[1].strip()
        if token == "no-role-token":
            raise ReviewerAuthError("principal lacks the 'Approver' role", status_code=403)
        if token not in _PRINCIPALS:
            raise ReviewerAuthError("token is not valid for this API")
        return _PRINCIPALS[token]


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
    # A fresh repository per test (the app's is a process singleton), cleared afterwards. The
    # authenticator is overridden here rather than disabled — the endpoint still runs its full
    # auth path, it just consults a fake key-store.
    repo = InMemoryInvestigationRepository()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_authenticator] = _FakeAuthenticator
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


def _approve(investigation_id: str, report_hash: str, *, headers=None, **overrides) -> None:
    body = {"decision": "approve", "submitted_report_hash": report_hash}
    body.update(overrides)
    r = client.post(
        f"/investigations/{investigation_id}/decision",
        json=body, headers=headers or HUMAN_AUTH,
    )
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


def test_force_rerun_mints_a_new_investigation_and_becomes_the_new_default():
    _use_service(_bm25_service)
    first = client.post("/investigations", json=_ALERT).json()

    rerun = client.post("/investigations?force_rerun=true", json=_ALERT).json()
    assert rerun["investigation_id"] != first["investigation_id"]

    # the original is untouched and still pollable by its own id
    assert client.get(first["poll_url"]).status_code == 200

    # a later non-forced POST for the same alert now returns the rerun, not the original
    repeat = client.post("/investigations", json=_ALERT).json()
    assert repeat["investigation_id"] == rerun["investigation_id"]


def test_a_workflow_version_bump_mints_a_new_investigation(monkeypatch):
    _use_service(_bm25_service)
    first = client.post("/investigations", json=_ALERT).json()

    monkeypatch.setattr("opspilot.api.WORKFLOW_VERSION", "999.0")
    bumped = client.post("/investigations", json=_ALERT).json()
    assert bumped["investigation_id"] != first["investigation_id"]


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
        json={"decision": "approve", "submitted_report_hash": "h"}, headers=HUMAN_AUTH,
    )
    assert r.status_code == 404


def test_decision_against_a_resolved_investigation_is_409():
    _use_service(_bm25_service)
    posted = client.post("/investigations", json=_ALERT).json()
    pending = client.get(posted["poll_url"]).json()
    report_hash = pending["pending_decision"]["report_hash"]
    _approve(posted["investigation_id"], report_hash)  # resolves it -> completed

    body = {"decision": "approve", "submitted_report_hash": report_hash}
    r = client.post(
        f"/investigations/{posted['investigation_id']}/decision", json=body, headers=HUMAN_AUTH,
    )
    assert r.status_code == 409


def test_reject_decision_escalates():
    _use_service(_bm25_service)
    posted = client.post("/investigations", json=_ALERT).json()
    pending = client.get(posted["poll_url"]).json()
    report_hash = pending["pending_decision"]["report_hash"]

    r = client.post(
        f"/investigations/{posted['investigation_id']}/decision",
        json={"decision": "reject", "submitted_report_hash": report_hash}, headers=HUMAN_AUTH,
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
        json={"decision": "approve", "submitted_report_hash": "not-the-real-hash"},
        headers=HUMAN_AUTH,
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
        json={"decision": "edit", "submitted_report_hash": first_hash,
              "edits": {"recommended_next_step": "roll back the deploy"}},
        headers=HUMAN_AUTH,
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


# --- reviewer identity (G-01) --------------------------------------------------------------------
def _pause_one() -> tuple[str, str]:
    """Drive an investigation to its pause and return (investigation_id, report_hash)."""
    _use_service(_bm25_service)
    posted = client.post("/investigations", json=_ALERT).json()
    pending = client.get(posted["poll_url"]).json()
    return posted["investigation_id"], pending["pending_decision"]["report_hash"]


def test_an_unauthenticated_decision_is_rejected():
    """The gap G-01 named: before this, an anonymous POST approved the report."""
    investigation_id, report_hash = _pause_one()

    r = client.post(
        f"/investigations/{investigation_id}/decision",
        json={"decision": "approve", "submitted_report_hash": report_hash},
    )
    assert r.status_code == 401
    # And the investigation is untouched — a rejected decision must not advance the run.
    assert client.get(f"/investigations/{investigation_id}").json()["status"] == "awaiting_approval"


def test_an_authenticated_principal_without_the_role_is_rejected():
    investigation_id, report_hash = _pause_one()

    r = client.post(
        f"/investigations/{investigation_id}/decision",
        json={"decision": "approve", "submitted_report_hash": report_hash},
        headers={"Authorization": "Bearer no-role-token"},
    )
    assert r.status_code == 403
    assert client.get(f"/investigations/{investigation_id}").json()["status"] == "awaiting_approval"


def test_a_client_supplied_approver_is_refused_outright():
    """`approver` is not an ignored field — it is forbidden. An old client that still sends one
    must fail loudly rather than appear to work while its value is silently discarded."""
    investigation_id, report_hash = _pause_one()

    r = client.post(
        f"/investigations/{investigation_id}/decision",
        json={
            "decision": "approve",
            "submitted_report_hash": report_hash,
            "approver": "someone-else",
        },
        headers=HUMAN_AUTH,
    )
    assert r.status_code == 422


def test_the_approval_record_binds_the_verified_principal_not_a_client_string():
    investigation_id, report_hash = _pause_one()
    _approve(investigation_id, report_hash)

    approval = client.get(f"/investigations/{investigation_id}").json()["result"]["approval"]
    assert approval["kind"] == "human"
    # Subject-keyed and method-qualified — the immutable oid, not the display name.
    assert approval["approver"] == "entra_jwt:oid-human-1"
    assert approval["approver_display_name"] == "reviewer@example.com"
    assert approval["approver_tenant_id"] == "test-tenant"


def test_a_service_principal_decision_is_never_reported_as_human():
    """The deploy smoke gate authenticates as a workload. It may drive the path; it may not be
    laundered into human review (code guidelines §15)."""
    investigation_id, report_hash = _pause_one()
    _approve(investigation_id, report_hash, headers=SERVICE_AUTH)

    approval = client.get(f"/investigations/{investigation_id}").json()["result"]["approval"]
    assert approval["kind"] == "service_principal"
    assert approval["approver"] == "service_principal:oid-smoke-sp"


def test_authentication_precedes_existence_so_the_endpoint_is_not_an_id_oracle():
    # An unauthenticated caller must not be able to distinguish a real investigation from a
    # fabricated id by the status code it gets back.
    body = {"decision": "approve", "submitted_report_hash": "h"}
    real_id, _ = _pause_one()

    unknown = client.post("/investigations/does-not-exist/decision", json=body)
    known = client.post(f"/investigations/{real_id}/decision", json=body)
    assert unknown.status_code == known.status_code == 401
