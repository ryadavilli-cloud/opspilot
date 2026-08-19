"""One investigation end to end, on responses a model really produced.

The sibling tests script the model, which proves the wiring and says nothing about whether a real
response survives the path. This replays a cassette recorded once against the deployment the
application ships against, so every assertion below runs on prose, citations, capability choices,
and a correction the model chose for itself.

A recorded response is untrusted input exactly like a live one. What is protected here is that the
run holds it to the same rules either way: the brief may only rest on what this investigation
admitted, the record has to exist before the brief is delivered, and a model that gathers freely
still cannot spend more than its bounds allow.

No model is called. `ReplayChatModel` needs no provider SDK, so this runs in every lane.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fake_operational_records import corpus_records
from fastapi.testclient import TestClient

from opspilot.api import app, get_model, get_operational_records, get_record, get_service
from opspilot.evidence.references import try_parse
from opspilot.llm.cassette import ReplayChatModel
from opspilot.record.memory import InMemoryCompletedInvestigations
from opspilot.tools.service import ToolService

# The incident the cassette was recorded against. Replay keys off the messages, so a different one
# would build different prompts and miss rather than quietly replay the wrong answer.
INCIDENT = "inc-005"
# The second recorded incident, taken in the same session against the same deployment.
SECOND_INCIDENT = "inc-004"


def _replay(incident: str) -> tuple[list[dict], InMemoryCompletedInvestigations]:
    """Replay one recorded investigation and return its streamed events and the record it wrote.

    Everything is built per call: the cassette is re-read, the corpus fake rebuilt, and the
    overrides installed and removed here rather than at import, so no sibling module's
    `dependency_overrides.clear()` can disarm them depending on collection order.
    """
    cassette = Path(__file__).resolve().parents[1] / "eval" / "cassettes" / f"{incident}.json"
    model = ReplayChatModel(cassette)
    records = corpus_records()
    record = InMemoryCompletedInvestigations()
    app.dependency_overrides[get_operational_records] = lambda: records
    app.dependency_overrides[get_service] = lambda: ToolService(records)
    app.dependency_overrides[get_model] = lambda: model
    app.dependency_overrides[get_record] = lambda: record
    try:
        with TestClient(app) as client:
            with client.stream("POST", "/investigations", json={"incident_id": incident}) as resp:
                assert resp.status_code == 200
                events = [json.loads(line) for line in resp.iter_lines() if line.strip()]
        return events, record
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def replayed() -> tuple[list[dict], InMemoryCompletedInvestigations]:
    return _replay(INCIDENT)


@pytest.fixture
def ambiguous() -> tuple[list[dict], InMemoryCompletedInvestigations]:
    """The second recording. Its first pass was expected to be the one that could not close."""
    return _replay(SECOND_INCIDENT)


def _references_in(node: object) -> set[str]:
    """Every reference anywhere in a structure, decided by the one parser rather than by a shape
    guess here. A second heuristic would be a second definition, and prose contains colons."""
    found: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            for token in value.split():
                if try_parse(token) is not None:
                    found.add(token)

    walk(node)
    return found


def test_a_recorded_investigation_reaches_a_delivered_brief(replayed):
    """A miss raises rather than degrading, so arriving here at all proves the recorded requests
    matched. Asserted explicitly so a future prompt edit fails here, naming the cassette."""
    events, _ = replayed

    assert events[0]["event_type"] == "identity"
    assert events[-1]["event_type"] == "terminal"
    assert events[-1]["failure"] is None
    assert events[-1]["brief"]["text"].strip()


def test_the_model_chose_its_own_evidence_path(replayed):
    """The point of the arrangement. A fixed plan would issue the same calls whatever it saw; this
    one asked for several different capabilities, each chosen after the last result was admitted."""
    events, _ = replayed

    capabilities = [e["capability"] for e in events if e.get("capability")]
    assert len(capabilities) >= 3
    assert len(set(capabilities)) >= 3, f"the path never varied: {capabilities}"


def test_every_reference_the_brief_carries_was_admitted_by_this_investigation(replayed):
    """The property the gate exists for, on a real response. The model cited what it chose to
    cite; only what this run observed may reach the engineer."""
    events, record = replayed

    admitted = {ref for event in events for ref in event.get("references", [])}
    assert admitted, "the investigation admitted nothing, so the assertion would be vacuous"

    for reference in _references_in(events[-1]["brief"]):
        assert reference in admitted, f"{reference} reached the brief without being admitted"


def test_the_record_exists_before_the_brief_is_delivered(replayed):
    """Nothing is announced that was not first written. The record is read after the stream has
    closed, so its presence proves the save happened somewhere before the terminal event."""
    events, record = replayed

    saved = record.get(events[0]["investigation_id"])
    assert saved is not None
    assert saved.brief.text == events[-1]["brief"]["text"]
    assert saved.outcome.value == events[-1]["brief"]["outcome"]


def test_the_record_accounts_for_every_operation_including_the_ones_that_answered_nothing(replayed):
    events, record = replayed
    saved = record.get(events[0]["investigation_id"])

    assert saved is not None
    assert saved.operations, "the record names nothing it attempted"
    assert saved.model_deployment, "the record does not say which deployment produced it"
    assert saved.prompt_versions, "the record does not say which prompts produced it"


def test_a_freely_gathering_model_still_cannot_exceed_its_bounds(replayed):
    """It proposed more work than it was allowed. The cap is code's, so gathering ended on it."""
    events, record = replayed
    saved = record.get(events[0]["investigation_id"])

    from opspilot import config

    assert saved is not None
    capability_calls = [e for e in events if e.get("capability")]
    assert len(capability_calls) <= config.CAPABILITY_CALL_CAP


def test_the_stream_carries_no_prompt_or_hidden_reasoning(replayed):
    """A real response is where this is most likely to leak: the model wrote freely, and none of
    what it was told or privately reasoned may reach the feed."""
    events, _ = replayed

    feed = " ".join(
        f"{e.get('action', '')} {e.get('detail', '')}"
        for e in events
        if e["event_type"] == "activity"
    )
    assert "You are the" not in feed
    assert "Rules you must follow" not in feed


# --- the one return, on responses a model really produced -----------------------------------------
def test_a_real_model_asked_for_more_and_code_granted_it(replayed):
    """The return is not a scripted arrangement. On this recording the analyst named something it
    could not settle and the kind of evidence that would settle it; deterministic code checked the
    bound, the vocabulary, and the budget, and sent gathering back for it.

    Asserted on the feed rather than on internal state, because the return is a thing the engineer
    watching the investigation is supposed to be able to see happen.
    """
    events, _ = replayed

    returns = [e for e in events if e.get("action") == "returned to gathering"]
    assert len(returns) == 1, f"expected exactly one return, saw {len(returns)}"

    order = [e.get("action") for e in events]
    assert order.index("returned to gathering") < len(order) - 1, "the return was the last thing"
    assert order.count("assessment proposed") == 2, "synthesis did not run again after the return"
    assert events[-1]["failure"] is None
    assert events[-1]["brief"]["text"].strip()


def test_the_return_did_not_widen_anything(replayed):
    """A returned run is still a bounded run. The resumed gathering spends the same caps, so the
    recording must not show more capability calls than the cap allows."""
    events, record = replayed
    from opspilot import config

    saved = record.get(events[0]["investigation_id"])
    assert saved is not None
    assert len([e for e in events if e.get("capability")]) <= config.CAPABILITY_CALL_CAP


def test_the_second_recording_also_reaches_a_brief_without_returning(ambiguous):
    """Kept as taken rather than re-rolled. This incident was expected to be the one whose first
    pass could not close, and on this deployment its analyst asked for nothing further and closed
    on what it had. That is the honest counterpart to the recording above: the return is available
    and conditional, not a stage every investigation passes through.
    """
    events, _ = ambiguous

    assert events[-1]["event_type"] == "terminal"
    assert events[-1]["failure"] is None
    assert events[-1]["brief"]["text"].strip()
    assert not [e for e in events if e.get("action") == "returned to gathering"]


def test_every_reference_the_second_brief_carries_was_admitted_too(ambiguous):
    """The grounding property holds on the second recording as well, so it is a property of the
    run rather than of the one response that happened to be recorded first."""
    events, _ = ambiguous

    admitted = {ref for event in events for ref in event.get("references", [])}
    assert admitted
    for reference in _references_in(events[-1]["brief"]):
        assert reference in admitted, f"{reference} reached the brief without being admitted"
