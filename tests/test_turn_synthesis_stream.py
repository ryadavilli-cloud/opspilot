"""The streamed turn, end to end against the real corpus with a scripted model.

No live model is involved: the synthesis call runs against a fake that returns a fixed proposal, so
this asserts the wiring and the ordering rather than the model's judgement.

The property worth protecting is that everything reaching the stream came through admission. A
citation the model invented must not appear, and an authoritative absence must be visible as a
finding rather than as a failure.
"""

from __future__ import annotations

import json

from fake_operational_records import corpus_records
from fastapi.testclient import TestClient

from opspilot.api import app, get_operational_records, get_service, get_synthesis_model
from opspilot.llm.base import ChatResult
from opspilot.tools.service import ToolService
from opspilot.turn.synthesis_step import evidence_plan

# inc-005: a Redis eviction storm. Chosen because its authored answer key records that no
# deployment exists anywhere in its window, which is what makes the empty change history a finding.
INCIDENT = "inc-005"
INVENTED = "logs:payment-api:evt-999-99"


class _ScriptedModel:
    """Returns one proposal, citing both a real reference and an invented one."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def complete(self, messages, **_):
        self.calls += 1
        self.prompt = messages[0].content
        self.evidence_shown = messages[1].content
        return ChatResult(text=json.dumps(self.payload), model_id="fake")


def _events(client: TestClient, incident: str = INCIDENT) -> list[dict]:
    with client.stream("POST", "/turns", json={"incident_id": incident}) as response:
        assert response.status_code == 200
        return [json.loads(line) for line in response.iter_lines() if line.strip()]


def _run(payload: dict) -> tuple[list[dict], _ScriptedModel]:
    model = _ScriptedModel(payload)
    # Restore whatever was there rather than popping: another module installs its own model
    # override at import time, and deleting it would leave that module's tests reaching for a real
    # provider, which blocks on a connection that never resolves rather than failing.
    previous = app.dependency_overrides.get(get_synthesis_model)
    app.dependency_overrides[get_synthesis_model] = lambda: model
    # Inject the record source too: reaching the deployed container from a deterministic test is
    # refused outright, which is the guard working rather than a fixture to route around.
    records = corpus_records()
    app.dependency_overrides[get_operational_records] = lambda: records
    app.dependency_overrides[get_service] = lambda: ToolService(records)
    try:
        with TestClient(app) as client:
            return _events(client), model
    finally:
        app.dependency_overrides.pop(get_operational_records, None)
        app.dependency_overrides.pop(get_service, None)
        if previous is None:
            app.dependency_overrides.pop(get_synthesis_model, None)
        else:
            app.dependency_overrides[get_synthesis_model] = previous


def _first_real_ref(events: list[dict]) -> str:
    for event in events:
        for ref in event.get("references", []):
            return ref
    raise AssertionError("the turn admitted no evidence at all")


# --- ordering and shape ---------------------------------------------------------------------
def test_the_stream_opens_with_identities_and_closes_with_the_marker():
    events, _ = _run({})
    assert events[0]["event_type"] == "identity"
    assert events[-1]["event_type"] == "close"
    assert events[0]["turn_id"] == events[-1]["turn_id"]


def test_the_brief_arrives_before_the_close_marker():
    """A brief after the close marker would be unreadable by a client that stopped at the close."""
    events, _ = _run({"what_happened": "checkout latency rose"})
    kinds = [e["event_type"] for e in events]
    assert "brief" in kinds
    assert kinds.index("brief") < kinds.index("close")


def test_the_turn_is_still_non_terminal():
    """No grounding gate has run, so nothing may present itself as an accepted outcome."""
    events, _ = _run({})
    for event in events:
        assert event.get("status") not in {"complete", "partial", "inconclusive"}
        assert event["event_type"] in {"identity", "activity", "brief", "close"}


# --- evidence actually flows ----------------------------------------------------------------
def test_capabilities_run_and_report_both_axes():
    events, _ = _run({})
    activity = [e for e in events if e["event_type"] == "activity" and e.get("capability")]
    assert activity, "no capability activity reached the stream"
    for event in activity:
        assert event["outcome"] in {
            "succeeded",
            "empty",
            "timed_out",
            "unavailable",
            "rejected",
            "failed",
        }
        assert event["transport"] == "direct"


def test_the_model_is_called_once_and_shown_only_admitted_evidence():
    events, model = _run({})
    assert model.calls == 1
    assert "Admitted evidence:" in model.evidence_shown
    # The answer key must never reach a prompt: it is what the investigation exists to discover.
    assert "root_cause" not in model.evidence_shown
    assert "resolution" not in model.evidence_shown


def test_an_invented_citation_never_reaches_the_brief():
    """The model may name anything. Only what admission produced can be cited, and the brief can
    only render what the assessment holds."""
    events, _ = _run(
        {
            "what_happened": "something happened",
            "leading": {"statement": "an invented cause", "supporting_refs": [INVENTED]},
        }
    )
    body = json.dumps(events)
    assert INVENTED not in body


def test_a_grounded_citation_does_reach_the_brief():
    baseline, _ = _run({})
    real = _first_real_ref(baseline)
    events, _ = _run(
        {
            "what_happened": "checkout latency rose",
            "what_happened_refs": [real],
            "leading": {"statement": "the cache degraded", "supporting_refs": [real]},
        }
    )
    brief = next(e for e in events if e["event_type"] == "brief")
    assert real in json.dumps(brief)


# --- the authoritative absence ----------------------------------------------------------------
def test_an_empty_change_history_is_reported_as_a_finding_not_a_failure():
    """inc-005 has no deployment anywhere in its window. That query succeeds and returns nothing,
    which is an observation about the scope rather than an unanswered question."""
    events, _ = _run({})
    deploys = [
        e
        for e in events
        if e["event_type"] == "activity" and e.get("capability") == "get_deployments"
    ]
    assert deploys, "the change-history check did not run"
    assert deploys[0]["outcome"] == "succeeded"
    assert "empty" in deploys[0]["detail"]


# --- the plan itself ---------------------------------------------------------------------------
def test_the_evidence_plan_is_empty_without_alerts_to_scope_it():
    """Predefined intake carries no affected service, so the alerts are what the rest is scoped to.
    With none, there is nothing to query rather than something to guess."""

    from datetime import UTC, datetime

    class _Ctx:
        symptom = "x"
        time_anchor = datetime(2026, 6, 22, 11, 0, tzinfo=UTC)

    assert evidence_plan(_Ctx(), []) == []
