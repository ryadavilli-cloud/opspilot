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

# Reviewer/caller identities, keyed by bearer token (G-01 decide role; Stage 8 submit/read roles).
# Token *validation* is covered against real RS256 signatures in `test_auth.py`; this fake exists so
# these lifecycle tests exercise the endpoints' behaviour — which principal reaches the approval
# record, and which HTTP status an unproven or unauthorized caller gets — without minting a JWT per
# request. `authenticate()` only proves identity (matching the real validator post-Stage-8); role
# authorization is enforced by the endpoints themselves via `auth.require_role`/`require_any_role`.
_HUMAN = ReviewerPrincipal(
    subject="oid-human-1", tenant_id="test-tenant", display_name="reviewer@example.com",
    roles=("Approver", "Submitter", "Reader"), auth_method="entra_jwt",
)
_SERVICE = ReviewerPrincipal(
    subject="oid-smoke-sp", tenant_id="test-tenant", display_name="opspilot-smoke",
    roles=("Approver",), auth_method="service_principal",
)
# Authenticates fine, but carries none of the three OpsPilot roles — the "signed in to the tenant,
# not to this app" case the decision-role test already relied on before Stage 8, now shared by all
# three endpoints' role checks.
_NO_ROLE = ReviewerPrincipal(
    subject="oid-guest-1", tenant_id="test-tenant", display_name="guest@example.com",
    roles=(), auth_method="entra_jwt",
)
_PRINCIPALS = {"human-token": _HUMAN, "app-token": _SERVICE, "no-role-token": _NO_ROLE}

HUMAN_AUTH = {"Authorization": "Bearer human-token"}
SERVICE_AUTH = {"Authorization": "Bearer app-token"}
NO_ROLE_AUTH = {"Authorization": "Bearer no-role-token"}


class _FakeAuthenticator:
    """Same contract as `EntraJwtAuthenticator`, same fail-closed shape: an unknown or absent token
    raises rather than falling back to a default principal. Proves identity only — no role logic
    here, matching the real validator (role authorization moved to the endpoint call sites)."""

    def authenticate(self, authorization_header: str | None) -> ReviewerPrincipal:
        if not authorization_header or not authorization_header.lower().startswith("bearer "):
            raise ReviewerAuthError("an Authorization header is required")
        token = authorization_header.split(" ", 1)[1].strip()
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
    r = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH)
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
    posted = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH).json()
    r = client.get(posted["poll_url"], headers=HUMAN_AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "awaiting_approval"  # real hitl_gate pause, not an auto-approved run
    assert body["history"] == ["queued", "running", "awaiting_approval"]
    assert body["result"] is None  # not terminal yet
    assert body["pending_decision"] and body["pending_decision"]["report_hash"]

    _approve(posted["investigation_id"], body["pending_decision"]["report_hash"])

    final = client.get(posted["poll_url"], headers=HUMAN_AUTH).json()
    assert final["status"] == "completed"
    assert final["history"] == [
        "queued", "running", "awaiting_approval", "running", "completed",
    ]
    assert final["result"] and final["result"]["report"]["citations"]
    assert final["error"] is None
    assert final["pending_decision"] is None  # cleared once resolved


def test_failure_is_recorded_not_raised():
    _use_service(lambda: _BoomService())
    posted = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH)
    assert posted.status_code == 202  # accepting the work never 500s, even if the run will fault
    body = client.get(posted.json()["poll_url"], headers=HUMAN_AUTH).json()
    assert body["status"] == "failed"
    assert body["history"] == ["queued", "running", "failed"]
    assert body["result"] is None
    assert body["error"]  # a sanitized, class-level reason — no stack trace


def test_idempotent_repeat_returns_the_same_investigation():
    _use_service(_bm25_service)
    first = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH).json()
    second = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH).json()
    assert first["investigation_id"] == second["investigation_id"]  # no duplicate run

    pending = client.get(second["poll_url"], headers=HUMAN_AUTH).json()
    _approve(second["investigation_id"], pending["pending_decision"]["report_hash"])
    assert client.get(second["poll_url"], headers=HUMAN_AUTH).json()["status"] == "completed"


def test_force_rerun_mints_a_new_investigation_and_becomes_the_new_default():
    _use_service(_bm25_service)
    first = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH).json()

    rerun = client.post("/investigations?force_rerun=true", json=_ALERT, headers=HUMAN_AUTH).json()
    assert rerun["investigation_id"] != first["investigation_id"]

    # the original is untouched and still pollable by its own id
    assert client.get(first["poll_url"], headers=HUMAN_AUTH).status_code == 200

    # a later non-forced POST for the same alert now returns the rerun, not the original
    repeat = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH).json()
    assert repeat["investigation_id"] == rerun["investigation_id"]


def test_a_workflow_version_bump_mints_a_new_investigation(monkeypatch):
    _use_service(_bm25_service)
    first = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH).json()

    monkeypatch.setattr("opspilot.api.WORKFLOW_VERSION", "999.0")
    bumped = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH).json()
    assert bumped["investigation_id"] != first["investigation_id"]


def test_unknown_investigation_is_404():
    r = client.get("/investigations/does-not-exist", headers=HUMAN_AUTH)
    assert r.status_code == 404


def test_investigate_compatibility_endpoint_still_works():
    """The sync compatibility endpoint auto-resolves any hitl_gate pause itself — it must keep
    returning a complete terminal result inline, unlike the async job API.

    It now also requires the submit role (G-03). Proving submit authority is deliberately NOT
    reviewer authority: the approval stays labelled `deterministic_auto_approval`, so
    authenticating the caller cannot quietly promote an auto-approval into human review."""
    _use_service(_bm25_service)
    r = client.post("/investigate", json=_ALERT, headers=HUMAN_AUTH)
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
    posted = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH).json()
    pending = client.get(posted["poll_url"], headers=HUMAN_AUTH).json()
    report_hash = pending["pending_decision"]["report_hash"]
    _approve(posted["investigation_id"], report_hash)  # resolves it -> completed

    body = {"decision": "approve", "submitted_report_hash": report_hash}
    r = client.post(
        f"/investigations/{posted['investigation_id']}/decision", json=body, headers=HUMAN_AUTH,
    )
    assert r.status_code == 409


def test_reject_decision_escalates():
    _use_service(_bm25_service)
    posted = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH).json()
    pending = client.get(posted["poll_url"], headers=HUMAN_AUTH).json()
    report_hash = pending["pending_decision"]["report_hash"]

    r = client.post(
        f"/investigations/{posted['investigation_id']}/decision",
        json={"decision": "reject", "submitted_report_hash": report_hash}, headers=HUMAN_AUTH,
    )
    assert r.status_code == 202

    final = client.get(posted["poll_url"], headers=HUMAN_AUTH).json()
    assert final["status"] == "escalated"


def test_stale_hash_decision_is_rejected_and_escalates():
    _use_service(_bm25_service)
    posted = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH).json()
    client.get(posted["poll_url"], headers=HUMAN_AUTH)  # ensure it's paused before deciding

    r = client.post(
        f"/investigations/{posted['investigation_id']}/decision",
        json={"decision": "approve", "submitted_report_hash": "not-the-real-hash"},
        headers=HUMAN_AUTH,
    )
    assert r.status_code == 202  # accepted for resume; the rejection happens inside the graph

    final = client.get(posted["poll_url"], headers=HUMAN_AUTH).json()
    assert final["status"] == "escalated"


def test_edit_decision_re_pauses_with_a_new_hash_then_approves():
    _use_service(_bm25_service)
    posted = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH).json()
    pending = client.get(posted["poll_url"], headers=HUMAN_AUTH).json()
    first_hash = pending["pending_decision"]["report_hash"]

    r = client.post(
        f"/investigations/{posted['investigation_id']}/decision",
        json={"decision": "edit", "submitted_report_hash": first_hash,
              "edits": {"recommended_next_step": "roll back the deploy"}},
        headers=HUMAN_AUTH,
    )
    assert r.status_code == 202

    repaused = client.get(posted["poll_url"], headers=HUMAN_AUTH).json()
    assert repaused["status"] == "awaiting_approval"  # edit re-enters validation, never finalizes
    second_hash = repaused["pending_decision"]["report_hash"]
    assert second_hash != first_hash  # a different report, a new hash

    _approve(posted["investigation_id"], second_hash)
    final = client.get(posted["poll_url"], headers=HUMAN_AUTH).json()
    assert final["status"] == "completed"
    assert final["result"]["report"]["recommended_next_step"] == "roll back the deploy"


# --- reviewer identity (G-01) --------------------------------------------------------------------
def _pause_one() -> tuple[str, str]:
    """Drive an investigation to its pause and return (investigation_id, report_hash)."""
    _use_service(_bm25_service)
    posted = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH).json()
    pending = client.get(posted["poll_url"], headers=HUMAN_AUTH).json()
    return posted["investigation_id"], pending["pending_decision"]["report_hash"]


def _get(investigation_id: str) -> dict:
    return client.get(f"/investigations/{investigation_id}", headers=HUMAN_AUTH).json()


def test_an_unauthenticated_decision_is_rejected():
    """The gap G-01 named: before this, an anonymous POST approved the report."""
    investigation_id, report_hash = _pause_one()

    r = client.post(
        f"/investigations/{investigation_id}/decision",
        json={"decision": "approve", "submitted_report_hash": report_hash},
    )
    assert r.status_code == 401
    # And the investigation is untouched — a rejected decision must not advance the run.
    assert _get(investigation_id)["status"] == "awaiting_approval"


def test_an_authenticated_principal_without_the_role_is_rejected():
    investigation_id, report_hash = _pause_one()

    r = client.post(
        f"/investigations/{investigation_id}/decision",
        json={"decision": "approve", "submitted_report_hash": report_hash},
        headers={"Authorization": "Bearer no-role-token"},
    )
    assert r.status_code == 403
    assert _get(investigation_id)["status"] == "awaiting_approval"


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

    approval = _get(investigation_id)["result"]["approval"]
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

    approval = _get(investigation_id)["result"]["approval"]
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


# --- submit/read ingress auth (Stage 8, pulled forward: G-03/G-57) ------------------------------
# The gap this slice closes: before it, POST /investigations and GET /investigations/{id} had no
# auth dependency at all — anyone who found the URL could submit unlimited investigations (driving
# Azure OpenAI spend) and read any report. Reuses the same Entra validator as the decision endpoint,
# gated by two new roles (Submitter, Reader) instead of a fixed one.
def test_an_anonymous_submit_is_rejected():
    r = client.post("/investigations", json=_ALERT)
    assert r.status_code == 401


def test_an_anonymous_read_is_rejected():
    investigation_id, _ = _pause_one()
    r = client.get(f"/investigations/{investigation_id}")
    assert r.status_code == 401


def test_authentication_precedes_existence_on_read_too():
    # Same id-oracle reasoning as the decision endpoint, now for GET.
    real_id, _ = _pause_one()
    unknown = client.get("/investigations/does-not-exist")
    known = client.get(f"/investigations/{real_id}")
    assert unknown.status_code == known.status_code == 401


def test_a_principal_without_the_submit_role_cannot_submit():
    r = client.post("/investigations", json=_ALERT, headers=NO_ROLE_AUTH)
    assert r.status_code == 403


def test_a_principal_without_any_read_role_cannot_read():
    investigation_id, _ = _pause_one()
    r = client.get(f"/investigations/{investigation_id}", headers=NO_ROLE_AUTH)
    assert r.status_code == 403


def test_a_reviewer_role_alone_is_sufficient_to_read():
    # Reading is open to submit OR read OR decide — a reviewer who never submitted still needs to
    # see the report before deciding on it.
    reviewer_only = ReviewerPrincipal(
        subject="oid-reviewer-2", tenant_id="test-tenant", display_name="reviewer2@example.com",
        roles=("Approver",), auth_method="entra_jwt",
    )
    _PRINCIPALS["reviewer-only-token"] = reviewer_only
    try:
        investigation_id, _ = _pause_one()
        r = client.get(
            f"/investigations/{investigation_id}",
            headers={"Authorization": "Bearer reviewer-only-token"},
        )
        assert r.status_code == 200
    finally:
        del _PRINCIPALS["reviewer-only-token"]


def test_authorized_submit_and_read_completes_the_existing_flow():
    """The demo path: a properly-authorized caller is unaffected by this slice — submit, poll, and
    decide all still work end to end."""
    _use_service(_bm25_service)
    posted = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH)
    assert posted.status_code == 202

    pending = client.get(posted.json()["poll_url"], headers=HUMAN_AUTH).json()
    assert pending["status"] == "awaiting_approval"

    _approve(posted.json()["investigation_id"], pending["pending_decision"]["report_hash"])
    final = _get(posted.json()["investigation_id"])
    assert final["status"] == "completed"


# --- basic concurrency limits (Stage 8, pulled forward: G-57) -----------------------------------
def test_global_concurrency_limit_returns_429(monkeypatch):
    monkeypatch.setattr("opspilot.config.MAX_CONCURRENT_INVESTIGATIONS_GLOBAL", 1)
    _use_service(_bm25_service)
    first = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH)
    assert first.status_code == 202  # pauses at awaiting_approval -> still occupies the one slot

    other_alert = {"incident_id": "inc-005", "summary": "a distinct incident, different key"}
    second = client.post("/investigations", json=other_alert, headers=HUMAN_AUTH)
    assert second.status_code == 429


def test_per_user_concurrency_limit_returns_429(monkeypatch):
    monkeypatch.setattr("opspilot.config.MAX_CONCURRENT_INVESTIGATIONS_PER_USER", 1)
    _use_service(_bm25_service)
    first = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH)
    assert first.status_code == 202

    other_alert = {"incident_id": "inc-006", "summary": "yet another distinct incident"}
    second = client.post("/investigations", json=other_alert, headers=HUMAN_AUTH)
    assert second.status_code == 429


def test_concurrency_limit_does_not_block_an_idempotent_repeat(monkeypatch):
    # A repeat of the SAME alert never starts a new background job, so it must not be counted
    # against — or rejected by — the concurrency check.
    monkeypatch.setattr("opspilot.config.MAX_CONCURRENT_INVESTIGATIONS_PER_USER", 1)
    _use_service(_bm25_service)
    first = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH)
    assert first.status_code == 202
    repeat = client.post("/investigations", json=_ALERT, headers=HUMAN_AUTH)
    assert repeat.status_code == 202
    assert repeat.json()["investigation_id"] == first.json()["investigation_id"]
