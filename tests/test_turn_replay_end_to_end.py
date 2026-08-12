"""One incident to a rendered assessment, on a real recorded model response.

The sibling wiring tests script the model, which proves the plumbing but says nothing about
whether a genuine response survives the path. This replays a cassette recorded once against a live
model, so the assertions below run against output a model actually produced: prose it chose,
citations it chose, and candidates it chose.

No model is called. `ReplayChatModel` needs no provider SDK, so this runs in every lane.

The property worth protecting is that admission still decides what survives. A recorded response is
untrusted input exactly like a live one: every reference the brief carries must be one admission
assigned, and a reference the model invented must not reach the engineer merely because a real
model invented it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fake_operational_records import corpus_records
from fastapi.testclient import TestClient

from opspilot.api import app, get_operational_records, get_service, get_synthesis_model
from opspilot.evidence.references import try_parse
from opspilot.llm.cassette import ReplayChatModel
from opspilot.tools.service import ToolService

CASSETTE = Path(__file__).resolve().parents[1] / "eval" / "cassettes" / "turn_synthesis.json"
# The incident the cassette was recorded against. Replay keys off the messages, so a different
# incident would build a different prompt and miss rather than quietly replay the wrong answer.
INCIDENT = "inc-005"


@pytest.fixture
def replayed_turn() -> list[dict]:
    """The streamed events of one turn, synthesized from the recorded response.

    Everything is built per test: the cassette is re-read, the corpus fake is rebuilt, and the
    overrides are installed and removed here rather than at import, so no sibling module's
    `dependency_overrides.clear()` can disarm them depending on collection order.
    """
    model = ReplayChatModel(CASSETTE)
    records = corpus_records()
    app.dependency_overrides[get_operational_records] = lambda: records
    app.dependency_overrides[get_service] = lambda: ToolService(records)
    app.dependency_overrides[get_synthesis_model] = lambda: model
    try:
        with (
            TestClient(app) as client,
            client.stream("POST", "/turns", json={"incident_id": INCIDENT}) as response,
        ):
            assert response.status_code == 200
            return [json.loads(line) for line in response.iter_lines() if line.strip()]
    finally:
        app.dependency_overrides.pop(get_operational_records, None)
        app.dependency_overrides.pop(get_service, None)
        app.dependency_overrides.pop(get_synthesis_model, None)


def _admitted_refs(events: list[dict]) -> set[str]:
    return {ref for event in events for ref in event.get("references", [])}


def _brief_refs(brief: dict) -> set[str]:
    """Every reference anywhere in the rendered brief, found structurally rather than by reading
    the fields this particular assessment happens to populate.

    What counts as a reference is decided by the one parser rather than by a shape guess here. A
    second heuristic would be a second definition, and prose legitimately contains colons.
    """
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str):
            # Rendered sections join several references into one block, so the string is split
            # before parsing rather than tested whole.
            for token in node.split():
                if try_parse(token) is not None:
                    found.add(token)

    walk(brief)
    return found


def test_the_recorded_response_carries_the_turn_to_a_rendered_brief(replayed_turn):
    kinds = [event["event_type"] for event in replayed_turn]
    assert kinds[0] == "identity" and kinds[-1] == "close"
    assert "brief" in kinds
    assert kinds.index("brief") < kinds.index("close")


def test_the_cassette_answers_without_any_live_model(replayed_turn):
    """A miss raises rather than degrading, so reaching the brief at all proves the recorded
    request matched. Asserted explicitly so a future prompt edit fails here, naming the cassette,
    rather than somewhere downstream."""
    brief = next(event for event in replayed_turn if event["event_type"] == "brief")
    assert brief["brief"]


def test_every_reference_the_brief_carries_was_assigned_by_admission(replayed_turn):
    """The point of the whole path. The recorded model named citations of its own choosing; only
    those admission produced may appear, and a real model's invention is no more admissible than a
    scripted one's."""
    brief = next(event for event in replayed_turn if event["event_type"] == "brief")
    admitted = _admitted_refs(replayed_turn)
    assert admitted, "the turn admitted no evidence, so the assertion below would be vacuous"

    for ref in _brief_refs(brief["brief"]):
        assert ref in admitted, f"{ref} reached the brief without being admitted"


def test_the_turn_is_still_non_terminal(replayed_turn):
    """No grounding gate has run, so a real model response must not produce an accepted outcome
    either."""
    for event in replayed_turn:
        assert event.get("status") not in {"complete", "partial", "inconclusive"}


def test_the_recorded_absence_is_carried_as_a_finding(replayed_turn):
    """inc-005 has no deployment in its window. The empty change history must still read as an
    authoritative absence on a real response, not as a failed lookup."""
    deploys = [
        event
        for event in replayed_turn
        if event["event_type"] == "activity" and event.get("capability") == "get_deployments"
    ]
    assert deploys, "the change-history check did not run"
    assert deploys[0]["outcome"] == "succeeded"
    assert "empty" in deploys[0]["detail"]
