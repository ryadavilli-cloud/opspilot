"""One incident to a rendered assessment, on a real recorded model response.

The sibling wiring tests script the model, which proves the plumbing but says nothing about
whether a genuine response survives the path. This replays a cassette recorded once against a live
model, so the assertions below run against output a model actually produced: prose it chose,
citations it chose, and candidates it chose.

No model is called. `ReplayChatModel` needs no provider SDK, so this runs in every lane.

The property worth protecting is that the path carries the response through without editing it. A
recorded response is untrusted input exactly like a live one, and the answer to "is this citation
real" belongs to the grounding gate rather than to a filter along the way: an assessment quietly
cleaned up before the gate sees it is one the gate cannot honestly approve.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fake_operational_records import corpus_records
from fastapi.testclient import TestClient

from opspilot.api import app, get_operational_records, get_service, get_synthesis_model
from opspilot.assessment.synthesis import admit_assessment, parse_proposal
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


def _recorded_response() -> str:
    """The one response the cassette holds, read from the file rather than restated here, so the
    comparison below is always against what the model actually said."""
    recorded = json.loads(CASSETTE.read_text(encoding="utf-8"))["interactions"]
    assert len(recorded) == 1, "one synthesis call per turn"
    return str(recorded[0]["response"]["text"])


def _admitted_refs(events: list[dict]) -> set[str]:
    return {ref for event in events for ref in event.get("references", [])}


def _references_in(node: object) -> set[str]:
    """Every reference anywhere in a structure, found structurally rather than by reading the
    fields this particular assessment happens to populate.

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

    walk(node)
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


def test_the_path_neither_adds_nor_drops_a_reference_the_model_proposed(replayed_turn):
    """The point of the whole path, on a response a model really produced.

    What the analyst proposed is what the gate has to see, so nothing between the response and the
    rendered brief may quietly remove a citation or introduce one. Comparing against the recorded
    response itself, rather than against what the turn admitted, is what makes that checkable: a
    reference this run never observed is a grounding failure to report, not a defect for admission
    or the renderer to tidy away first.
    """
    brief = next(event for event in replayed_turn if event["event_type"] == "brief")
    proposed = admit_assessment(parse_proposal(_recorded_response()))

    expected = _references_in(proposed.model_dump())
    assert expected, "the recorded response cited nothing, so the assertion would be vacuous"

    assert _references_in(brief["brief"]) == expected


def test_at_least_one_cited_reference_came_through_admission(replayed_turn):
    """Keeps the case above honest: it compares the brief against the proposal, so a run that
    admitted nothing at all would still satisfy it while proving nothing about the evidence path."""
    brief = next(event for event in replayed_turn if event["event_type"] == "brief")
    assert _admitted_refs(replayed_turn) & _references_in(brief["brief"])


def test_the_turn_still_commits_nothing(replayed_turn):
    """A real response reaches a brief and states the outcome the assessment supports, and still
    nothing is grounded, persisted, or delivered as terminal."""
    assert set(replayed_turn[-1]) == {"event_type", "turn_id"}


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
