"""The read-only page over completed investigations and kept evaluation runs, and its routes.

What is asserted is mostly what the surface refuses to be. Every route behind the page reads and
nothing writes: no route under it creates, triggers, edits, or deletes a record or a run, and the
application reaches the run store through the durable factory rather than a process-local one.
The listings come back newest first, an unknown identifier is a clean absence, and the investigation
screen carries the one link that reaches the page.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from test_completed_record import _record  # noqa: E402
from test_evaluation_store import _run  # noqa: E402

from opspilot.api import app, get_evaluation_runs, get_record, get_service  # noqa: E402
from opspilot.evaluation.store import InMemoryEvaluationRuns  # noqa: E402
from opspilot.record.memory import InMemoryCompletedInvestigations  # noqa: E402


class _ForbiddenService:
    """A registry that fails the test if anything on this page reaches it."""

    tool_names = ()

    def call(self, tool_name: str, *args: object, **kwargs: object) -> object:
        raise AssertionError(f"the read-only page called {tool_name}")


@pytest.fixture
def client():
    records = InMemoryCompletedInvestigations()
    records.save(_record("inv-1"))
    records.save(_record("inv-2"))
    runs = InMemoryEvaluationRuns()
    runs.save(_run("2026-08-20-1", taken_at=datetime(2026, 8, 20, 9, tzinfo=UTC), judge="gpt-x"))
    runs.save(_run("2026-08-21-1", taken_at=datetime(2026, 8, 21, 9, tzinfo=UTC)))
    app.dependency_overrides[get_record] = lambda: records
    app.dependency_overrides[get_evaluation_runs] = lambda: runs
    app.dependency_overrides[get_service] = _ForbiddenService
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# --- investigations, listed ---------------------------------------------------------------------
def test_completed_investigations_are_listed_newest_first_as_summaries(client):
    response = client.get("/investigations")

    assert response.status_code == 200
    listed = response.json()
    assert [s["investigation_id"] for s in listed] == ["inv-2", "inv-1"]
    assert listed[0]["incident_id"] == "inc-005"
    assert listed[0]["outcome"] == "partial"
    assert listed[0]["model_calls_made"] == 6
    assert listed[0]["capability_calls_made"] == 4
    assert listed[0]["token_usage"] == {"prompt_tokens": 31_200, "completion_tokens": 4_150}
    assert listed[0]["duration_s"] == 87.4
    assert listed[0]["taken_at"]
    assert "observations" not in listed[0] and "brief" not in listed[0]


def test_each_listed_investigation_is_then_readable_in_full(client):
    listed = client.get("/investigations").json()

    full = client.get(f"/investigations/{listed[0]['investigation_id']}")

    assert full.status_code == 200
    assert full.json()["brief"]["text"]
    assert full.json()["trace_id"] == "inv-1"


# --- evaluation runs, listed and read -----------------------------------------------------------
def test_kept_evaluation_runs_are_listed_newest_first_with_their_configuration(client):
    response = client.get("/evaluations")

    assert response.status_code == 200
    listed = response.json()
    assert [s["run_id"] for s in listed] == ["2026-08-21-1", "2026-08-20-1"]
    assert listed[0]["configuration"]["judge_deployment"] == "gpt-5-mini"
    assert listed[1]["configuration"]["judge_deployment"] == "gpt-x"
    assert "scenarios" not in listed[0]


def test_a_kept_run_reads_back_in_full(client):
    response = client.get("/evaluations/2026-08-21-1")

    assert response.status_code == 200
    run = response.json()
    assert [s["scenario_id"] for s in run["scenarios"]] == ["inc-005", "inc-001"]
    assert run["scenarios"][0]["checks"][1]["passed"] is False
    assert run["scenarios"][0]["verdicts"][0]["category"] == "meets"
    assert run["comparisons"][1]["ran"] is False


def test_an_unknown_run_is_a_clean_not_found(client):
    assert client.get("/evaluations/2000-01-01-1").status_code == 404


# --- nothing here writes ------------------------------------------------------------------------
def test_every_route_over_evaluations_and_the_page_only_reads():
    """Read-only by construction, asserted on the route table rather than on intent: no method
    but GET is served anywhere under the evaluation routes or the page."""
    prefixes = ("/evaluations", "/agentops")
    routes = [r for r in app.routes if getattr(r, "path", "").startswith(prefixes)]

    assert routes, "the routes this page depends on are not registered"
    assert all(getattr(r, "methods", set()) == {"GET"} for r in routes)
    assert {getattr(r, "path", "") for r in routes} == {
        "/evaluations",
        "/evaluations/{run_id}",
        "/agentops",
    }


def test_listing_investigations_is_a_read_and_the_store_does_not_grow(client):
    listing = [r for r in app.routes if getattr(r, "path", "") == "/investigations"]

    assert {m for r in listing for m in getattr(r, "methods", set())} == {"GET", "POST"}
    client.get("/investigations")
    assert len(client.get("/investigations").json()) == 2


def test_the_application_builds_the_durable_run_store_rather_than_a_process_local_one(monkeypatch):
    """Asserted by substituting the factory rather than by building a Cosmos client, so this needs
    no credential and still fails if the application goes back to naming a class directly."""
    import opspilot.api as api
    import opspilot.evaluation.store as store

    sentinel = object()
    monkeypatch.setattr(store, "default_evaluation_runs", lambda: sentinel)
    monkeypatch.setattr(api, "_evaluation_runs", None)
    try:
        assert api.get_evaluation_runs() is sentinel
        assert api.get_evaluation_runs() is sentinel, "built once per process, not per request"
    finally:
        api._evaluation_runs = None


# --- the page ---------------------------------------------------------------------------------
def test_the_page_is_served_and_reads_only_the_listing_and_reading_routes(client):
    page = client.get("/agentops")

    assert page.status_code == 200
    assert 'id="investigations"' in page.text and 'id="evaluations"' in page.text
    assert 'fetch("/investigations")' in page.text
    assert 'fetch("/evaluations")' in page.text
    assert "method:" not in page.text, "the page issues nothing but plain reads"


def test_the_investigation_screen_carries_one_link_to_the_page(client):
    screen = client.get("/investigation").text

    assert screen.count('href="/agentops"') == 1
