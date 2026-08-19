"""Reading a completed investigation, and asking about one.

Both requests are over something already finished, and the properties worth asserting are about
what they refuse rather than what they return. The question is answered by a model whose only
context is the record; what keeps it from concluding anything new is that constrained context, the
instruction, the structured references, and refusal. Only the last of those is code, and it is what
these tests hold: a citation the record does not carry, or a candidate position it does not have,
replaces the answer instead of being trimmed or repaired.

The other half is that neither request is an investigation. No capability is reached, no record is
written, and an unknown identifier is a clean absence rather than an error.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from test_completed_record import _record  # noqa: E402

from opspilot.api import app, get_model, get_record, get_service  # noqa: E402
from opspilot.llm.base import ChatResult  # noqa: E402
from opspilot.record.memory import InMemoryCompletedInvestigations  # noqa: E402

LOG = "logs:checkout-api:evt-005-01"
RUNBOOK = "runbook:redis-cache-degradation"


class _ScriptedSupervisor:
    """Answers the question with whatever the test wants the model to have said."""

    deployment = "scripted"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls = 0

    def complete(self, task: str, messages: list[Any]) -> ChatResult:
        self.calls += 1
        return ChatResult(text=json.dumps(self.payload), task=task, deployment=self.deployment)


class _ForbiddenService:
    """A registry that fails the test if the question reaches it. Answering is not investigating."""

    tool_names = ()

    def call(self, tool_name: str, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"the question called {tool_name}; it must gather nothing")


def _client(payload: dict[str, Any] | None = None) -> tuple[TestClient, Any, Any]:
    """One app with a saved record, a scripted Supervisor, and a registry that must not be used."""
    store = InMemoryCompletedInvestigations()
    store.save(_record())
    model = _ScriptedSupervisor(payload or {})
    service = _ForbiddenService()
    app.dependency_overrides[get_record] = lambda: store
    app.dependency_overrides[get_model] = lambda: model
    app.dependency_overrides[get_service] = lambda: service
    return TestClient(app), store, model


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    app.dependency_overrides.clear()


# --- reading one back ---------------------------------------------------------------------------
def test_a_saved_investigation_reads_back_by_its_identifier():
    client, _, _ = _client()

    response = client.get("/investigations/inv-1")

    assert response.status_code == 200
    body = response.json()
    assert body["investigation_id"] == "inv-1"
    assert body["brief"]["text"]
    assert [o["evidence_ref"] for o in body["observations"]][0] == LOG


def test_reading_an_identifier_that_names_nothing_is_a_clean_not_found():
    """Absent is an answer. An error here would make "no such investigation" indistinguishable
    from a store that could not be reached."""
    client, _, _ = _client()

    assert client.get("/investigations/inv-never").status_code == 404


# --- the question, when the record supports the answer -------------------------------------------
def test_an_answer_resting_on_the_records_own_references_is_given_as_it_stands():
    client, _, model = _client(
        {"answer": "the cache reached its memory ceiling", "references": [LOG, RUNBOOK]}
    )

    response = client.post("/investigations/inv-1/questions", json={"question": "what happened"})

    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is False
    assert body["answer"] == "the cache reached its memory ceiling"
    assert body["references"] == [LOG, RUNBOOK]
    assert model.calls == 1, "the question is one model call and no more"


def test_a_position_naming_a_candidate_the_record_carries_is_kept():
    client, _, _ = _client(
        {"answer": "the leading candidate", "references": [LOG], "candidate_position": 1}
    )

    body = client.post("/investigations/inv-1/questions", json={"question": "which cause"}).json()

    assert body["refused"] is False
    assert body["candidate_position"] == 1


# --- the question, when it does not --------------------------------------------------------------
def test_an_answer_citing_a_reference_the_record_does_not_carry_is_replaced():
    """The property the check exists for. The citation is plausible and the reference is
    well-formed; what it is not is something this investigation admitted or retrieved."""
    client, _, _ = _client(
        {"answer": "a deployment caused it", "references": ["deploys:checkout-api:dep-999"]}
    )

    body = client.post(
        "/investigations/inv-1/questions", json={"question": "what caused it"}
    ).json()

    assert body["refused"] is True
    assert "a deployment caused it" not in body["answer"]
    assert body["references"] == []


def test_one_unsupported_citation_replaces_the_whole_answer():
    """Not trimmed to the references that did resolve. An answer whose support has been removed is
    no longer the answer that was given, and returning the remainder would be code paraphrasing."""
    client, _, _ = _client(
        {"answer": "both of these", "references": [LOG, "metrics:ghost:cpu@2026-06-22T11:35:00Z"]}
    )

    body = client.post("/investigations/inv-1/questions", json={"question": "why"}).json()

    assert body["refused"] is True
    assert body["references"] == []


def test_a_candidate_position_beyond_the_retained_list_is_rejected():
    client, _, _ = _client(
        {"answer": "the fourth candidate", "references": [LOG], "candidate_position": 4}
    )

    body = client.post("/investigations/inv-1/questions", json={"question": "which one"}).json()

    assert body["refused"] is True


def test_a_position_below_the_first_is_rejected():
    client, _, _ = _client(
        {"answer": "before the first", "references": [], "candidate_position": 0}
    )

    assert client.post("/investigations/inv-1/questions", json={"question": "?"}).json()["refused"]


def test_the_record_saying_nothing_is_an_answer_rather_than_a_refusal():
    """Answering "the record does not say" is the model doing what it was told. It carries no
    references because there are none to carry, and it must not read as a failed check."""
    client, _, _ = _client({"answer": "the record does not say", "references": []})

    body = client.post("/investigations/inv-1/questions", json={"question": "who paged"}).json()

    assert body["refused"] is False
    assert body["answer"] == "the record does not say"


# --- a question is not an investigation ----------------------------------------------------------
def test_the_question_gathers_nothing_and_creates_no_investigation():
    """Asserted through a registry that fails on any call and a store that must not grow: the
    investigation is over, and asking about it does not reopen it."""
    client, store, _ = _client({"answer": "read from the record", "references": [LOG]})

    client.post("/investigations/inv-1/questions", json={"question": "what happened"})

    assert store.get("inv-1") is not None
    assert len(store._records) == 1, "the question wrote a record"


def test_asking_about_an_investigation_that_does_not_exist_is_a_clean_not_found():
    client, _, model = _client({"answer": "should never be asked", "references": []})

    assert (
        client.post("/investigations/inv-none/questions", json={"question": "?"}).status_code == 404
    )
    assert model.calls == 0, "the model was asked about a record that does not exist"


def test_an_empty_question_is_refused_before_any_model_call():
    client, _, model = _client({"answer": "should never be asked", "references": []})

    assert (
        client.post("/investigations/inv-1/questions", json={"question": "  "}).status_code == 422
    )
    assert model.calls == 0


# --- the application writes somewhere a later request can read ----------------------------------
def test_the_application_builds_the_durable_store_rather_than_a_process_local_one(monkeypatch):
    """What makes the question answerable at all on a deployment.

    A question is a second request, and under more than one replica it can land on an instance that
    never ran the investigation. A process-local store would not make that flaky, it would make it
    wrong. Asserted by substituting the factory rather than by building a Cosmos client, so this
    needs no credential and still fails if the application goes back to naming a class directly.
    """
    import opspilot.api as api
    import opspilot.record.cosmos as cosmos

    sentinel = object()
    monkeypatch.setattr(cosmos, "default_completed_investigations", lambda: sentinel)
    monkeypatch.setattr(api, "_record", None)
    try:
        assert api.get_record() is sentinel
        assert api.get_record() is sentinel, "the store is built once per process, not per request"
    finally:
        api._record = None


# --- the screen ---------------------------------------------------------------------------------
def test_the_screen_carries_the_question_box_and_drives_the_question_route():
    """The box is part of the same page as the brief, and posts to the route that answers it."""
    client, _, _ = _client()

    page = client.get("/investigation")

    assert page.status_code == 200
    assert 'id="question-input"' in page.text
    assert 'id="ask-button"' in page.text
    assert "/questions" in page.text
