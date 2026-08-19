"""The probes the platform runs, and what they are allowed to cost.

Readiness runs for the life of a revision on a period far shorter than an investigation, so what it
touches it touches continuously. These assert both halves: that it still tells a revision which
cannot work from one which can, and that it does not reach the investigative path to do it.
"""

from __future__ import annotations

from typing import Any

import pytest
from fake_operational_records import FakeContainer, corpus_container, corpus_records
from fastapi.testclient import TestClient

from opspilot.api import app, get_operational_records, get_service
from opspilot.config import RETRIEVAL_BACKEND
from opspilot.data.operational_records import OperationalRecords
from opspilot.tools.service import ToolService


class _CountingService(ToolService):
    """A real service that records which capabilities were asked for."""

    def __init__(self, records: OperationalRecords, backend: str = RETRIEVAL_BACKEND) -> None:
        super().__init__(records)
        self.called: list[str] = []
        self._backend = backend

    @property  # type: ignore[override]
    def retrieval_backend(self) -> str:
        return self._backend

    def get_incident(self, remaining_s: Any = None, /, **kwargs: Any) -> Any:
        self.called.append("get_incident")
        return super().get_incident(remaining_s, **kwargs)

    def query_logs(self, remaining_s: Any = None, /, **kwargs: Any) -> Any:
        self.called.append("query_logs")
        return super().query_logs(remaining_s, **kwargs)

    def search_runbooks(self, remaining_s: Any = None, /, **kwargs: Any) -> Any:
        self.called.append("search_runbooks")
        return super().search_runbooks(remaining_s, **kwargs)


@pytest.fixture
def service() -> _CountingService:
    return _CountingService(corpus_records())


@pytest.fixture
def client(service: _CountingService):
    app.dependency_overrides[get_service] = lambda: service
    app.dependency_overrides[get_operational_records] = corpus_records
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def test_liveness_answers_without_touching_anything(client, service):
    assert client.get("/health/live").status_code == 200
    assert service.called == []


def test_a_seeded_reachable_deployment_is_ready(client):
    body = client.get("/health/ready").json()

    assert body["status"] == "ready"
    assert body["checks"] == {"operational_records": "ok", "retrieval": "ok"}
    assert body["errors"] is None


def test_readiness_never_reaches_the_investigative_path(client, service):
    """The invariant this probe was narrowed to hold: cheap deterministic checks only, and nothing
    that exercises end-to-end behavior. Embedding a query here would repeat a model-serving call
    every few seconds for the life of the revision, and would report the application as not ready
    when it was the embedding endpoint that was rate limited.

    Stated as which capabilities must not be reached rather than as a call count. A later readiness
    check may legitimately need a second cheap read; what it may never do is search, embed, or
    invoke a model.
    """
    client.get("/health/ready")

    assert "search_runbooks" not in service.called
    assert "query_logs" not in service.called
    assert service.called, "the probe read nothing at all, so it proves nothing about the source"


def test_an_unreachable_source_is_not_ready(client):
    app.dependency_overrides[get_service] = lambda: _CountingService(
        OperationalRecords(corpus_container(unreachable=True))
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["operational_records"] == "failed"
    assert body["errors"] == [
        {"component": "operational_records", "code": "OPERATIONAL_RECORDS_UNAVAILABLE"}
    ]


def test_a_reachable_but_unseeded_source_is_not_ready(client):
    """An empty container answers the lookup authoritatively, which is a true answer and still not
    a deployment that can investigate anything."""
    app.dependency_overrides[get_service] = lambda: _CountingService(
        OperationalRecords(FakeContainer([]))
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["operational_records"] == "failed"


def test_retrieval_that_came_up_as_another_backend_is_not_ready(client):
    """Not just initialized: initialized as what this build was configured for. A revision quietly
    serving from a different index would answer every probe and cite the wrong knowledge."""
    app.dependency_overrides[get_service] = lambda: _CountingService(
        corpus_records(), backend="something-else"
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["retrieval"] == "failed"
    assert response.json()["errors"] == [
        {"component": "retrieval", "code": "RETRIEVAL_UNAVAILABLE"}
    ]


def test_no_probe_leaks_an_exception_or_a_stack_trace(client):
    app.dependency_overrides[get_service] = lambda: _CountingService(
        OperationalRecords(corpus_container(unreachable=True))
    )

    raw = client.get("/health/ready").text
    assert "Traceback" not in raw
    assert "ContainerUnreachable" not in raw
