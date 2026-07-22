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
    get_corpus_status,
    get_service,
)
from opspilot.config import RETRIEVAL_BACKEND  # noqa: E402
from opspilot.data.repository import CORPUS_FILES, RuntimeAssetStatus  # noqa: E402

client = TestClient(app)


# --- fakes ------------------------------------------------------------------------------------
def _result(status: str = "ok", results=None) -> SimpleNamespace:
    return SimpleNamespace(status=status, results=results if results is not None else [])


class _FakeService:
    """A ToolService stand-in for readiness tests — each check independently controllable."""

    def __init__(self, *, backend=RETRIEVAL_BACKEND, incident=True, logs=True, retrieval=True):
        self.retrieval_backend = backend
        self._incident, self._logs, self._retrieval = incident, logs, retrieval

    def get_incident(self, **_):
        return _result("ok", [{"incident_id": "inc-004"}]) if self._incident else _result("ok", [])

    def query_logs(self, **_):
        return _result("ok") if self._logs else _result("error")

    def search_runbooks(self, **_):
        return _result("ok", [1]) if self._retrieval else _result("error")


def _healthy_corpus():
    return RuntimeAssetStatus(root=api.config.CORPUS_DIR, present=CORPUS_FILES, missing=())


def _missing_corpus():
    return RuntimeAssetStatus(root=api.config.CORPUS_DIR, present=(), missing=CORPUS_FILES)


def _override(service_factory=None, corpus_factory=None):
    if service_factory is not None:
        app.dependency_overrides[get_service] = service_factory
    if corpus_factory is not None:
        app.dependency_overrides[get_corpus_status] = corpus_factory


@pytest.fixture(autouse=True)
def _clear_overrides():
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
    _override(lambda: _FakeService(), _healthy_corpus)
    r = client.get("/health/ready")
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "ready"
    assert body["checks"] == {"corpus": "ok", "repository": "ok", "logs": "ok", "retrieval": "ok"}
    assert body["errors"] is None


def test_readiness_missing_corpus_is_503():
    _override(lambda: _FakeService(), _missing_corpus)
    r = client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready" and body["checks"]["corpus"] == "failed"
    assert {"component": "corpus", "code": "CORPUS_INCOMPLETE"} in body["errors"]


def test_readiness_repository_failure_is_503():
    _override(lambda: _FakeService(incident=False), _healthy_corpus)
    r = client.get("/health/ready")
    assert r.status_code == 503 and r.json()["checks"]["repository"] == "failed"


def test_readiness_log_failure_is_503():
    _override(lambda: _FakeService(logs=False), _healthy_corpus)
    r = client.get("/health/ready")
    assert r.status_code == 503 and r.json()["checks"]["logs"] == "failed"


def test_readiness_retrieval_unavailable_is_503():
    _override(lambda: _FakeService(backend="unavailable"), _healthy_corpus)
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

    _override(lambda: _Leaky(), _healthy_corpus)
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
def _bm25_service():
    from opspilot.retrieval.factory import build_retriever
    from opspilot.tools.service import ToolService

    return ToolService(retriever_factory=lambda: build_retriever("bm25", include_distractors=False))


def test_investigation_smoke_path_over_bm25():
    _override(_bm25_service)
    r = client.post("/investigate", json={
        "incident_id": "inc-004",
        "summary": "checkout-api returning 500s shortly after this morning's deployment.",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["incident_id"] == "inc-004"
    assert body["status"] in ("completed", "degraded", "escalated")  # explicit terminal status
    assert body["status"] == "completed"
    assert body["report"] and body["report"]["hypothesis"]
    assert body["report"]["citations"]
    assert body["safety"] is not None and body["safety"]["passed"] is True
    assert body["runtime"]["retrieval_backend"] == "bm25"
    assert body["approval"]["kind"] == "deterministic_auto_approval"
    InvestigationResponse.model_validate(body)  # validates against the typed contract


def test_investigation_unknown_incident_does_not_report_success():
    _override(_bm25_service)
    r = client.post("/investigate", json={
        "incident_id": "inc-does-not-exist",
        "summary": "unknown incident with no corpus record.",
    })
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
    _override(_bm25_service)
    r = client.post("/investigate", json={"incident_id": "inc-999", "summary": "x"})
    body = r.json()
    assert body["status"] == "escalated"
    assert body["reason"] == "iteration_budget_exhausted: diagnose_iters=5"
    InvestigationResponse.model_validate(body)


def test_degraded_response_surfaces_a_reason(monkeypatch):
    _override(_bm25_service)
    monkeypatch.setattr(api, "_safe_backend", lambda svc: "unavailable")
    r = client.post("/investigate", json={
        "incident_id": "inc-004",
        "summary": "checkout-api returning 500s shortly after this morning's deployment.",
    })
    body = r.json()
    assert body["status"] == "degraded"
    assert body["reason"] and "unavailable" in body["reason"]
    InvestigationResponse.model_validate(body)
