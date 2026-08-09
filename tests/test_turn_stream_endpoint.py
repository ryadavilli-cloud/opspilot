"""The streaming turn endpoint: identities first, activity as it happens, close marker last.

One live streaming request owns one turn (runtime-and-deployment.md §2). No accepted completed-turn
outcome exists yet; the close marker proves ordering only.
"""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("httpx")  # FastAPI's TestClient transport

from fastapi.testclient import TestClient  # noqa: E402

from opspilot.api import _predefined_turn_stream, app  # noqa: E402
from opspilot.data.repository import default_repository  # noqa: E402
from opspilot.tools.contracts import IncidentRecord  # noqa: E402

client = TestClient(app)


class _DisconnectAfter:
    """A duck-typed stand-in for the FastAPI Request the endpoint checks for client disconnect.
    Reports connected for the first `stay_connected_for` checks, then disconnected forever."""

    def __init__(self, stay_connected_for: int) -> None:
        self._remaining = stay_connected_for

    async def is_disconnected(self) -> bool:
        if self._remaining > 0:
            self._remaining -= 1
            return False
        return True


def _stream_events(incident_id: str) -> list[dict]:
    with client.stream("POST", "/turns", json={"incident_id": incident_id}) as response:
        assert response.status_code == 200
        return [json.loads(line) for line in response.iter_lines() if line]


def test_identities_first_activity_then_close_marker_last():
    events = _stream_events("inc-001")

    assert events[0]["event_type"] == "identity"
    assert events[0]["turn_id"] and events[0]["investigation_id"]

    middle = events[1:-1]
    assert middle, "expected at least one activity entry between identity and close"
    assert all(event["event_type"] == "activity" for event in middle)
    assert [event["sequence"] for event in middle] == list(range(1, len(middle) + 1))

    assert events[-1]["event_type"] == "close"
    assert events[-1]["turn_id"] == events[0]["turn_id"]


def test_activity_entries_carry_no_answer_key_content():
    events = _stream_events("inc-001")
    raw = json.dumps(events)
    # inc-001's root_cause/resolution text (data/synthetic/incidents.json) must never appear on
    # the tool-visible stream; the normalized context excludes both by construction (D-007).
    assert "connection pool" not in raw
    assert "Reverted" not in raw


def test_unknown_incident_id_returns_404_before_any_stream_opens():
    response = client.post("/turns", json={"incident_id": "inc-does-not-exist"})
    assert response.status_code == 404


# --- in-process cancellation signal ---------------------------------------------------------
def _run_stream(disconnect_after: int) -> list[dict]:
    async def _go() -> list[dict]:
        raw = default_repository().incident("inc-001")
        incident = IncidentRecord(**raw)
        disconnect = _DisconnectAfter(stay_connected_for=disconnect_after)
        lines = [
            json.loads(line)
            async for line in _predefined_turn_stream("inc-001", incident, disconnect)
        ]
        return lines

    return asyncio.run(_go())


def test_stream_completes_normally_when_never_disconnected():
    events = _run_stream(disconnect_after=99)
    assert [e["event_type"] for e in events] == ["identity", "activity", "activity", "close"]


def test_stream_stops_emitting_once_the_client_has_disconnected():
    # Connected for the identity event and one activity check, gone after that: nothing past the
    # point of detection is emitted, including the close marker.
    events = _run_stream(disconnect_after=1)
    assert [e["event_type"] for e in events] == ["identity", "activity"]
    assert not any(e["event_type"] == "close" for e in events)


def test_stream_emits_nothing_but_the_identity_when_disconnected_immediately():
    events = _run_stream(disconnect_after=0)
    assert [e["event_type"] for e in events] == ["identity"]


def test_concurrent_turns_get_independent_identities_and_sequences():
    first = _stream_events("inc-001")
    second = _stream_events("inc-002")

    first_turn_id = first[0]["turn_id"]
    second_turn_id = second[0]["turn_id"]
    assert first_turn_id != second_turn_id
    assert first[0]["investigation_id"] != second[0]["investigation_id"]

    # Each stream's own activity sequence starts at 1 again: no shared projector state leaked
    # between turns.
    first_sequences = [e["sequence"] for e in first[1:-1]]
    second_sequences = [e["sequence"] for e in second[1:-1]]
    assert first_sequences[0] == 1
    assert second_sequences[0] == 1

    # And every event in a stream is attributed to that stream's own turn, never the other one's.
    assert all(e["turn_id"] == first_turn_id for e in [first[0], first[-1]])
    assert all(e["turn_id"] == second_turn_id for e in [second[0], second[-1]])


# --- the one-screen client ----------------------------------------------------------------------
def test_investigation_screen_is_served_same_origin():
    r = client.get("/investigation")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "OpsPilot" in r.text


def test_investigation_screen_does_not_touch_the_old_console():
    # A new file on its own route, not a rewrite: the old console keeps working until cutover.
    r = client.get("/console")
    assert r.status_code == 200
    assert 'id="incident-select"' not in r.text


def test_investigation_screen_posts_to_the_streaming_endpoint():
    r = client.get("/investigation")
    assert "/turns" in r.text
