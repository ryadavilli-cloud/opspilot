"""API surface tests — liveness, readiness, version, and the typed investigation contract.

All ML-free: the investigation path runs the deterministic slice over an injected BM25 service,
and readiness is exercised with fake services in each failure mode. Uses FastAPI's TestClient.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("httpx")  # FastAPI's TestClient transport

from fastapi.testclient import TestClient  # noqa: E402

from opspilot import api  # noqa: E402
from opspilot.api import (  # noqa: E402
    InvestigationResponse,
    app,
    get_authenticator,
    get_records_status,
    get_service,
)
from opspilot.auth import ReviewerAuthError, ReviewerPrincipal  # noqa: E402
from opspilot.config import RETRIEVAL_BACKEND  # noqa: E402
from opspilot.data.operational_records import (  # noqa: E402
    RECORD_KINDS,
    PreparationStatus,
)
from opspilot.tools.contracts import Completeness, ExecutionOutcome  # noqa: E402

client = TestClient(app)

# `/investigate` carries the submit role (G-03). Same fake-authenticator shape as the async API
# tests: identity only, so the endpoint's own role check is what these tests exercise.
_SUBMITTER = ReviewerPrincipal(
    subject="oid-submitter-1",
    tenant_id="test-tenant",
    display_name="submitter@example.com",
    roles=("Submitter",),
    auth_method="entra_jwt",
)
_NO_ROLE = ReviewerPrincipal(
    subject="oid-guest-1",
    tenant_id="test-tenant",
    display_name="guest@example.com",
    roles=(),
    auth_method="entra_jwt",
)
_PRINCIPALS = {"submit-token": _SUBMITTER, "no-role-token": _NO_ROLE}

SUBMIT_AUTH = {"Authorization": "Bearer submit-token"}
NO_ROLE_AUTH = {"Authorization": "Bearer no-role-token"}


class _FakeAuthenticator:
    """Fail-closed like the real validator: an absent or unknown token raises rather than
    defaulting to a principal."""

    def authenticate(self, authorization_header: str | None) -> ReviewerPrincipal:
        if not authorization_header or not authorization_header.lower().startswith("bearer "):
            raise ReviewerAuthError("an Authorization header is required")
        token = authorization_header.split(" ", 1)[1].strip()
        if token not in _PRINCIPALS:
            raise ReviewerAuthError("token is not valid for this API")
        return _PRINCIPALS[token]


# --- fakes ------------------------------------------------------------------------------------
def _result(
    outcome: ExecutionOutcome = ExecutionOutcome.SUCCEEDED,
    completeness: Completeness = Completeness.COMPLETE,
    results=None,
) -> SimpleNamespace:
    """A capability result on both axes, carrying `answered` exactly as the envelope derives it.
    The doubles must not be able to satisfy a readiness check by way of a field the contract does
    not have: that is what let a broken check pass while every real result failed it."""
    return SimpleNamespace(
        outcome=outcome,
        completeness=completeness,
        answered=outcome is ExecutionOutcome.SUCCEEDED,
        results=results if results is not None else [],
    )


class _FakeService:
    """A ToolService stand-in for readiness tests — each check independently controllable."""

    def __init__(self, *, backend=RETRIEVAL_BACKEND, incident=True, logs=True, retrieval=True):
        self.retrieval_backend = backend
        self._incident, self._logs, self._retrieval = incident, logs, retrieval

    def get_incident(self, **_):
        # An unseeded repository answers: `succeeded` with `empty`, not a failure.
        if self._incident:
            return _result(results=[{"incident_id": "inc-004"}])
        return _result(completeness=Completeness.EMPTY)

    def query_logs(self, **_):
        if self._logs:
            return _result(completeness=Completeness.EMPTY)
        return _result(ExecutionOutcome.UNAVAILABLE, Completeness.NOT_APPLICABLE)

    def search_runbooks(self, **_):
        if self._retrieval:
            return _result(results=[1])
        return _result(ExecutionOutcome.UNAVAILABLE, Completeness.NOT_APPLICABLE)


def _prepared_records():
    return PreparationStatus(counts=dict.fromkeys(RECORD_KINDS, 1), missing=())


def _unprepared_records():
    # What an unreachable or unseeded container reports: every kind missing, never a partial
    # picture that could read as ready.
    return PreparationStatus(counts={}, missing=RECORD_KINDS)


def _override(service_factory=None, records_factory=None):
    if service_factory is not None:
        app.dependency_overrides[get_service] = service_factory
    if records_factory is not None:
        app.dependency_overrides[get_records_status] = records_factory


@pytest.fixture(autouse=True)
def _clear_overrides():
    # The authenticator is overridden, not disabled: `/investigate` still runs its real role
    # check, so a missing header or a role-less principal is rejected by the endpoint itself.
    app.dependency_overrides[get_authenticator] = _FakeAuthenticator
    yield
    app.dependency_overrides.clear()


# --- liveness ---------------------------------------------------------------------------------
def test_liveness_returns_alive():
    body = client.get("/health/live").json()
    assert body == {"status": "alive", "version": api.__version__}


def test_liveness_ignores_a_broken_service():
    # liveness must not touch corpus/retrieval/tools — a failing service factory is irrelevant
    def _boom():
        raise RuntimeError("repository init failed")

    _override(service_factory=_boom)
    r = client.get("/health/live")
    assert r.status_code == 200 and r.json()["status"] == "alive"


def test_health_is_a_liveness_alias():
    assert client.get("/health").json()["status"] == "alive"


# --- readiness --------------------------------------------------------------------------------
def test_readiness_all_healthy_is_200():
    _override(lambda: _FakeService(), _prepared_records)
    r = client.get("/health/ready")
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "ready"
    assert body["checks"] == {
        "operational_records": "ok",
        "repository": "ok",
        "logs": "ok",
        "retrieval": "ok",
    }
    assert body["errors"] is None


def test_readiness_unprepared_records_is_503():
    _override(lambda: _FakeService(), _unprepared_records)
    r = client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready" and body["checks"]["operational_records"] == "failed"
    assert {
        "component": "operational_records",
        "code": "OPERATIONAL_RECORDS_INCOMPLETE",
    } in body["errors"]


def test_readiness_reads_the_container_and_fails_closed_when_it_cannot():
    """Absent preparation must present as a deployment failure rather than as a turn-time empty
    answer, so readiness runs the real check against a container that will not answer. Every kind
    reports missing; nothing here degrades to ready."""
    from fake_operational_records import corpus_container

    from opspilot.data.operational_records import OperationalRecords

    app.dependency_overrides[api.get_operational_records] = lambda: OperationalRecords(
        corpus_container(unreachable=True)
    )
    _override(lambda: _FakeService())
    r = client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["checks"]["operational_records"] == "failed"


def test_readiness_fails_when_one_record_kind_is_absent():
    """A container holding only some kinds is not partly ready. The capability whose kind is
    missing could only ever answer with nothing, which reads downstream as an authoritative
    absence rather than as an unprepared deployment."""
    from fake_operational_records import FakeContainer, corpus_documents

    from opspilot.data.operational_records import OperationalRecords

    without_metrics = [doc for doc in corpus_documents() if doc["kind"] != "metric_series"]
    app.dependency_overrides[api.get_operational_records] = lambda: OperationalRecords(
        FakeContainer(without_metrics)
    )
    _override(lambda: _FakeService())
    r = client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["checks"]["operational_records"] == "failed"


def test_readiness_passes_the_real_check_against_a_prepared_container():
    from fake_operational_records import corpus_container

    from opspilot.data.operational_records import OperationalRecords

    app.dependency_overrides[api.get_operational_records] = lambda: OperationalRecords(
        corpus_container()
    )
    _override(lambda: _FakeService())
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["checks"]["operational_records"] == "ok"


def test_readiness_repository_failure_is_503():
    _override(lambda: _FakeService(incident=False), _prepared_records)
    r = client.get("/health/ready")
    assert r.status_code == 503 and r.json()["checks"]["repository"] == "failed"


def test_readiness_log_failure_is_503():
    _override(lambda: _FakeService(logs=False), _prepared_records)
    r = client.get("/health/ready")
    assert r.status_code == 503 and r.json()["checks"]["logs"] == "failed"


def test_readiness_retrieval_unavailable_is_503():
    _override(lambda: _FakeService(backend="unavailable"), _prepared_records)
    r = client.get("/health/ready")
    body = r.json()
    assert r.status_code == 503
    assert body["checks"]["retrieval"] == "failed"
    assert body["retrieval_backend"] == "unavailable"
    assert {"component": "retrieval", "code": "RETRIEVAL_INITIALIZATION_FAILED"} in body["errors"]


def test_readiness_never_leaks_exception_text_or_paths():
    secret = "/srv/secret/corpus/incidents.json"

    class _Leaky(_FakeService):
        def search_runbooks(self, **_):
            raise FileNotFoundError(secret)

    _override(lambda: _Leaky(), _prepared_records)
    r = client.get("/health/ready")
    assert r.status_code == 503
    assert secret not in r.text and "FileNotFoundError" not in r.text
    assert r.json()["checks"]["retrieval"] == "failed"


# --- version ----------------------------------------------------------------------------------
def test_version_reports_application_workflow_and_backend():
    body = client.get("/version").json()
    assert body["application"] == "opspilot"
    assert body["version"] == api.__version__
    assert body["workflow_version"] == "1.0"
    assert body["retrieval_backend"] == RETRIEVAL_BACKEND


# --- operator console ---------------------------------------------------------------------------
def test_console_is_served_same_origin():
    r = client.get("/console")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "OpsPilot" in r.text
    # the no-real-HITL disclosure must be present, not just the happy path
    assert "auto-approved" in r.text.lower() or "no durable human approval" in r.text.lower()


def test_root_redirects_to_the_console():
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (307, 308)
    assert r.headers["location"] == "/console"


# --- investigation ----------------------------------------------------------------------------
def _fake_retrieval_service():
    from fake_knowledge import knowledge_retriever
    from fake_operational_records import corpus_records

    from opspilot.tools.service import ToolService

    return ToolService(corpus_records(), retriever_factory=knowledge_retriever)


def test_investigation_smoke_path_over_fake_retrieval():
    _override(_fake_retrieval_service)
    r = client.post(
        "/investigate",
        headers=SUBMIT_AUTH,
        json={
            "incident_id": "inc-004",
            "summary": "checkout-api returning 500s shortly after this morning's deployment.",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["incident_id"] == "inc-004"
    assert body["status"] in ("completed", "degraded", "escalated")  # explicit terminal status
    assert body["status"] == "completed"
    assert body["report"] and body["report"]["hypothesis"]
    assert body["report"]["citations"]
    assert body["safety"] is not None and body["safety"]["passed"] is True
    assert body["runtime"]["retrieval_backend"] == "cosmos"
    assert body["approval"]["kind"] == "deterministic_auto_approval"
    InvestigationResponse.model_validate(body)  # validates against the typed contract


def test_investigation_unknown_incident_does_not_report_success():
    _override(_fake_retrieval_service)
    r = client.post(
        "/investigate",
        headers=SUBMIT_AUTH,
        json={
            "incident_id": "inc-does-not-exist",
            "summary": "unknown incident with no corpus record.",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] != "completed"  # cannot complete without a real incident
    assert body["report"] is None
    InvestigationResponse.model_validate(body)


def test_escalated_response_surfaces_the_graph_escalation_reason(monkeypatch):
    # Drives the response-mapping logic directly with a synthetic terminal state, rather than
    # threading a real investigation through the whole graph into an escalation.
    fake_state = {
        "incident_id": "inc-999",
        "error": "iteration_budget_exhausted: diagnose_iters=5",
        "report": None,
        "safety": {"passed": False, "violations": ["no citations"]},
        "approval": None,
    }
    # `get_graph()` (not the `api._graph` global) — the graph is built lazily, so the global is
    # still None until something asks for it.
    monkeypatch.setattr(api.get_graph(), "invoke", lambda *a, **k: fake_state)
    _override(_fake_retrieval_service)
    r = client.post(
        "/investigate", headers=SUBMIT_AUTH, json={"incident_id": "inc-999", "summary": "x"}
    )
    body = r.json()
    assert body["status"] == "escalated"
    assert body["reason"] == "iteration_budget_exhausted: diagnose_iters=5"
    InvestigationResponse.model_validate(body)


def test_degraded_response_surfaces_a_reason(monkeypatch):
    _override(_fake_retrieval_service)
    monkeypatch.setattr(api, "_safe_backend", lambda svc: "unavailable")
    r = client.post(
        "/investigate",
        headers=SUBMIT_AUTH,
        json={
            "incident_id": "inc-004",
            "summary": "checkout-api returning 500s shortly after this morning's deployment.",
        },
    )
    body = r.json()
    assert body["status"] == "degraded"
    assert body["reason"] and "unavailable" in body["reason"]
    InvestigationResponse.model_validate(body)


# --- /investigate ingress auth (G-03) ----------------------------------------------------------
# The sync endpoint runs the same graph and spends the same model budget as `POST /investigations`,
# so it carries the same submit role. These two cases are the exposure that stayed open after #49.
def test_an_unauthenticated_caller_cannot_run_the_sync_investigation():
    _override(_fake_retrieval_service)
    r = client.post("/investigate", json={"incident_id": "inc-004", "summary": "x"})
    assert r.status_code == 401


def test_a_principal_without_the_submit_role_cannot_run_the_sync_investigation():
    _override(_fake_retrieval_service)
    r = client.post(
        "/investigate", headers=NO_ROLE_AUTH, json={"incident_id": "inc-004", "summary": "x"}
    )
    assert r.status_code == 403
