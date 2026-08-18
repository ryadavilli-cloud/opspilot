"""The streaming route: identity first, activity as it happens, exactly one terminal event.

The envelope is the contract a client depends on, so it is asserted rather than assumed. What a
client must never have to do is assemble the brief from activity entries or infer that a stream
which simply stopped had finished.
"""

from __future__ import annotations

import asyncio
import json
import threading

import pytest

httpx = pytest.importorskip("httpx")  # the test transport

from fake_operational_records import corpus_records  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from opspilot.api import (  # noqa: E402
    app,
    get_model,
    get_operational_records,
    get_record,
    get_service,
    investigation_stream,
)
from opspilot.config import SOURCE_DEADLINE_SECONDS  # noqa: E402
from opspilot.llm.base import ChatResult  # noqa: E402
from opspilot.record.memory import InMemoryCompletedInvestigations  # noqa: E402
from opspilot.tools.contracts import IncidentRecord  # noqa: E402
from opspilot.tools.service import ToolService  # noqa: E402

RECORDS = corpus_records()


class _QuietModel:
    """Proposes nothing, so the run ends without evidence. These tests assert the envelope."""

    deployment = "fake"

    def complete(self, task, messages):
        return ChatResult(text="{}", task=task, deployment=self.deployment)


class _DisconnectAfter:
    """Reports connected for the first `stay_connected_for` checks, then gone forever."""

    def __init__(self, stay_connected_for: int) -> None:
        self._remaining = stay_connected_for

    async def is_disconnected(self) -> bool:
        if self._remaining > 0:
            self._remaining -= 1
            return False
        return True


@pytest.fixture(autouse=True)
def _injected():
    """One fixture owning every override, installed per test.

    Two autouse fixtures would fight: whichever tears down first calls `clear()` and removes the
    other's override, so which test failed would depend on fixture ordering rather than behavior.
    """
    app.dependency_overrides[get_operational_records] = lambda: RECORDS
    app.dependency_overrides[get_service] = lambda: ToolService(RECORDS)
    app.dependency_overrides[get_model] = _QuietModel
    app.dependency_overrides[get_record] = InMemoryCompletedInvestigations
    yield
    app.dependency_overrides.clear()


def _events(incident_id: str) -> list[dict]:
    with TestClient(app) as client:
        with client.stream("POST", "/investigations", json={"incident_id": incident_id}) as resp:
            assert resp.status_code == 200
            return [json.loads(line) for line in resp.iter_lines() if line.strip()]


def test_identity_first_then_activity_then_exactly_one_terminal_event():
    events = _events("inc-001")

    assert events[0]["event_type"] == "identity"
    assert events[0]["investigation_id"]
    assert events[-1]["event_type"] == "terminal"
    assert [e["event_type"] for e in events].count("terminal") == 1

    activity = [e for e in events if e["event_type"] == "activity"]
    assert [e["sequence"] for e in activity] == list(range(1, len(activity) + 1))


def test_every_event_belongs_to_one_investigation_and_names_no_turn():
    events = _events("inc-001")
    identity = events[0]["investigation_id"]

    assert events[-1]["investigation_id"] == identity
    assert not any("turn_id" in event for event in events)


def test_a_terminal_event_carries_a_brief_or_a_failure_and_never_both():
    terminal = _events("inc-001")[-1]
    assert (terminal["brief"] is None) != (terminal["failure"] is None)


def test_activity_carries_no_answer_key_content():
    raw = json.dumps(_events("inc-001"))
    # inc-001's authored cause and resolution must never reach the stream; the normalized context
    # excludes both by construction.
    assert "connection pool" not in raw
    assert "Reverted" not in raw


def test_an_unknown_incident_is_refused_before_any_stream_opens():
    with TestClient(app) as client:
        assert client.post("/investigations", json={"incident_id": "nope"}).status_code == 404


# --- the in-process cancellation signal ---------------------------------------------------------
def _drive(disconnect_after: int) -> list[dict]:
    async def go() -> list[dict]:
        incident = IncidentRecord(**RECORDS.incident("inc-001", deadline_s=SOURCE_DEADLINE_SECONDS))
        return [
            json.loads(line)
            async for line in investigation_stream(
                incident,
                _DisconnectAfter(disconnect_after),  # type: ignore[arg-type]
                ToolService(RECORDS),
                _QuietModel(),
                InMemoryCompletedInvestigations(),
            )
        ]

    return asyncio.run(go())


def test_a_client_that_left_is_sent_nothing_further():
    events = _drive(disconnect_after=0)
    assert [e["event_type"] for e in events] == ["identity"]


def test_a_stream_never_disconnected_reaches_its_terminal_event():
    events = _drive(disconnect_after=99)
    assert events[0]["event_type"] == "identity"
    assert events[-1]["event_type"] == "terminal"


def test_concurrent_investigations_get_independent_identities_and_sequences():
    first, second = _events("inc-001"), _events("inc-002")

    assert first[0]["investigation_id"] != second[0]["investigation_id"]
    for events in (first, second):
        activity = [e for e in events if e["event_type"] == "activity"]
        assert activity[0]["sequence"] == 1  # no projector state leaked between runs


# --- the run does not hold the process ----------------------------------------------------------
# A run lasts minutes and the process must stay answerable throughout it: whatever else is asked of
# it while an investigation is in flight has to be served, not queued behind the run. The two below
# are what make this provable without a live service.
_BLOCKED_SECONDS = 3.0


class _BlockingModel:
    """Blocks whichever thread the graph runs on, inside its first call, until released.

    A `threading.Event.wait` rather than an awaitable sleep, deliberately: an awaitable sleep hands
    the loop back on its own and would be served fine by a route that never freed it, so it would
    prove nothing. This blocks the thread outright, which is the event loop itself unless the route
    drives the graph off it. Bounded so that a regression fails the test rather than hanging it.
    """

    deployment = "fake"

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.released = threading.Event()

    def complete(self, task, messages):
        self.entered.set()
        self.released.wait(timeout=_BLOCKED_SECONDS)
        return ChatResult(text="{}", task=task, deployment=self.deployment)


def test_the_process_answers_while_an_investigation_holds_a_model_call():
    """Ordering rather than elapsed time, so the assertion is about the mechanism and not the
    machine: the probe releases the model only once it has been answered, so a route that yields
    the loop must answer first, and one that does not cannot answer until the whole run is over."""
    model = _BlockingModel()
    app.dependency_overrides[get_model] = lambda: model
    answered: list[str] = []

    async def go():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://probe") as client:

            async def investigate() -> None:
                await client.post("/investigations", json={"incident_id": "inc-005"})
                answered.append("investigation")

            async def probe():
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, model.entered.wait, _BLOCKED_SECONDS)
                response = await client.get("/health/live")
                answered.append("health")
                model.released.set()
                return response

            _, response = await asyncio.gather(investigate(), probe())
            return response

    response = asyncio.run(go())

    assert model.entered.is_set(), "the run never reached a model call, so nothing was held"
    assert response.status_code == 200
    assert answered == ["health", "investigation"], (
        "the run held the event loop: nothing else could be served until it finished"
    )


# --- the screen ---------------------------------------------------------------------------------
def test_the_screen_is_served_same_origin_and_drives_the_one_route():
    with TestClient(app) as client:
        page = client.get("/investigation")
        assert page.status_code == 200
        assert page.headers["content-type"].startswith("text/html")
        assert "/investigations" in page.text
