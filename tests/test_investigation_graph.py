"""The investigation graph: what code decides, and what it refuses to let a model decide.

Every case here scripts the model and then checks what the run did with what it was told. That is
the arrangement worth protecting: the roles propose, and authorization, counting, admission,
grounding, the outcome, and the save are all code. A test that let the model decide any of those
would be testing the model.

The failure cases carry as much weight as the successful one. A run that observed nothing, or that
could not ground what it proposed, has to end without a record: collapsing it into a thin brief
would turn a broken investigation into a clean bill of health, which is the one reading none of
this may support.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from fake_operational_records import corpus_records

from opspilot.api import initial_state
from opspilot.assessment.contracts import Outcome
from opspilot.investigation.graph import MODEL, RECORD, SERVICE, build_graph
from opspilot.investigation.state import FailureCategory
from opspilot.llm.base import ChatResult
from opspilot.record.memory import InMemoryInvestigationRecord
from opspilot.record.port import RecordSaveError
from opspilot.tools.contracts import ExecutionOutcome, IncidentRecord
from opspilot.tools.errors import error_result
from opspilot.tools.service import ToolService

INCIDENT = "inc-005"
ALERTS = {"capability": "get_correlated_alerts", "arguments": {"incident_id": INCIDENT}}


class ScriptedModel:
    """One stand-in for all three roles, answering by task.

    Each task gets a queue of responses; the last repeats once exhausted, so a test states only the
    turns it cares about and gathering can run as long as the bounds allow.
    """

    deployment = "scripted"

    def __init__(self, **by_task: list[str]) -> None:
        self._by_task = by_task
        self.calls: list[str] = []

    def complete(self, task: str, messages: list[Any]) -> ChatResult:
        self.calls.append(task)
        queued = self._by_task.get(task)
        if not queued:
            return ChatResult(text="{}", task=task, deployment=self.deployment)
        index = min(len([c for c in self.calls if c == task]) - 1, len(queued) - 1)
        return ChatResult(text=queued[index], task=task, deployment=self.deployment)

    def count(self, task: str) -> int:
        return len([c for c in self.calls if c == task])


class FailingService:
    """A registry whose every call reports the source unreachable."""

    tool_names = ("get_correlated_alerts", "query_logs")

    def call(self, tool_name: str, **_: Any) -> Any:
        return error_result(
            tool_name, "unreachable", time.perf_counter(), ExecutionOutcome.UNAVAILABLE
        )


class RefusingRecord:
    """A record that cannot be written. A save that fails must not deliver anything."""

    def save(self, record: Any) -> None:
        raise RecordSaveError("the store refused the write")

    def get(self, investigation_id: str) -> Any:
        return None


def _action(**overrides: Any) -> str:
    payload = {**ALERTS, "question": "which alerts correlate with this incident"}
    payload.update(overrides)
    return json.dumps(payload)


def _finished(why: str = "the evidence is ready to interpret") -> str:
    return json.dumps({"capability": "", "finished_because": why})


def _assessment(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "what_happened": "checkout latency rose while the cache evicted keys",
        "what_happened_refs": ["REF"],
        "candidates": [
            {
                "statement": "redis-cache reached its memory ceiling",
                "label": "leading",
                "established": True,
                "supporting": ["REF"],
            }
        ],
        "actions": [{"action": "raise the cache memory ceiling", "now": True}],
    }
    payload.update(overrides)
    return json.dumps(payload)


@pytest.fixture
def records():
    return corpus_records()


@pytest.fixture
def incident(records) -> IncidentRecord:
    return IncidentRecord(**records.incident(INCIDENT, deadline_s=10))


def run(
    incident: IncidentRecord,
    model: ScriptedModel,
    *,
    service: Any,
    record: Any = None,
    prepare: Any = None,
) -> tuple[dict[str, Any], Any]:
    """Drive one investigation to its end and return the final state and the record it used."""
    record = record if record is not None else InMemoryInvestigationRecord()
    state = initial_state("inv-1", incident)
    if prepare is not None:
        prepare(state)
    final: dict[str, Any] = {}
    for step in build_graph().stream(
        state,
        config={
            "configurable": {MODEL: model, SERVICE: service, RECORD: record},
            "recursion_limit": 60,
        },
        stream_mode="values",
    ):
        final = step
    return final, record


def _admitted_ref(final: dict[str, Any]) -> str:
    return final["evidence"].admitted_refs[0]


# --- one incident, end to end -------------------------------------------------------------------
def test_an_incident_runs_to_a_saved_brief(incident, records):
    """The whole path: objective, one authorized call, admission, synthesis, grounding, save."""
    model = ScriptedModel(
        investigation_objective=['{"objective": "establish why checkout latency rose"}'],
        evidence_selection=[_action(), _finished()],
    )
    # Two passes: the first learns which reference admission assigned, the second cites it.
    first, _ = run(incident, model, service=ToolService(records))
    reference = _admitted_ref(first)

    model = ScriptedModel(
        investigation_objective=['{"objective": "establish why checkout latency rose"}'],
        evidence_selection=[_action(), _finished()],
        rca_synthesis=[_assessment().replace("REF", reference)],
    )
    final, record = run(incident, model, service=ToolService(records))

    assert final.get("failure") is None
    assert final["outcome"] is Outcome.COMPLETE
    saved = record.get("inv-1")
    assert saved is not None
    assert saved.brief.text and saved.assessment.candidates
    assert saved.operations, "the record accounts for what was attempted"


def test_the_activity_feed_carries_no_prompt_or_hidden_reasoning(incident, records):
    model = ScriptedModel(
        investigation_objective=['{"objective": "establish why checkout latency rose"}'],
        evidence_selection=[_action(), _finished()],
    )
    final, _ = run(incident, model, service=ToolService(records))

    body = " ".join(f"{e.action} {e.detail}" for e in final["events"])
    assert "You are the" not in body  # no prompt text
    assert "hypothesis" not in body.lower()  # no working hypothesis


# --- deterministic authorization ----------------------------------------------------------------
def test_an_unregistered_capability_ends_gathering_with_the_reason(incident, records):
    """Refused rather than filtered out, so the refusal is visible in the feed and in the reason."""
    model = ScriptedModel(
        evidence_selection=[_action(capability="restart_service", arguments={})],
    )
    final, _ = run(incident, model, service=ToolService(records))

    assert "not a registered capability" in final["stopped_because"]
    assert final["capability_calls_made"] == 0


def test_an_already_answered_question_ends_gathering(incident, records):
    same = "which alerts correlate with this incident"
    model = ScriptedModel(evidence_selection=[_action(question=same), _action(question=same)])
    final, _ = run(incident, model, service=ToolService(records))

    assert "already answered" in final["stopped_because"]
    assert final["capability_calls_made"] == 1


def test_the_same_call_reworded_as_a_different_question_still_ends_gathering(incident, records):
    """The question is the model's own prose, and it can phrase the same call two different ways.
    What decides whether it is a repeat is the capability and its arguments, not the wording."""
    model = ScriptedModel(
        evidence_selection=[
            _action(question="which alerts correlate with this incident"),
            _action(question="what alerts were correlated to this incident, restated"),
        ]
    )
    final, _ = run(incident, model, service=ToolService(records))

    assert "already called" in final["stopped_because"]
    assert final["capability_calls_made"] == 1


def test_an_exhausted_capability_cap_ends_gathering(incident, records):
    """The cap is state code owns. Nothing the investigator returns widens it."""

    def one_call_only(state):
        state.bounds.capability_calls = 1

    model = ScriptedModel(
        evidence_selection=[
            _action(question="first"),
            _action(question="second", arguments={"incident_id": INCIDENT, "start_time": "later"}),
        ]
    )
    final, _ = run(incident, model, service=ToolService(records), prepare=one_call_only)

    assert "capability-call cap is spent" in final["stopped_because"]
    assert final["capability_calls_made"] == 1


def test_the_model_call_count_never_exceeds_its_cap(incident, records):
    def two_calls_only(state):
        state.bounds.model_calls = 2

    model = ScriptedModel(evidence_selection=[_action(question=f"q{n}") for n in range(10)])
    final, _ = run(incident, model, service=ToolService(records), prepare=two_calls_only)

    assert final["model_calls_made"] <= 2
    assert len(model.calls) <= 2


# --- failed execution leaves no record ----------------------------------------------------------
def test_a_run_whose_sources_all_fail_is_a_failed_execution(incident):
    """Zero admitted observations means nothing could rest on anything observed."""
    model = ScriptedModel(evidence_selection=[_action(), _finished()])
    final, record = run(incident, model, service=FailingService())

    assert final["failure"] is FailureCategory.NO_EVIDENCE
    assert record.get("inv-1") is None
    assert final["evidence"].limitations, "the unreachable source is disclosed"


def test_an_ungroundable_assessment_fails_after_the_one_correction(incident, records):
    """The model cites what this run never admitted, twice. The gate refuses both times."""
    invented = _assessment().replace("REF", "logs:payment-api:evt-999-99")
    model = ScriptedModel(
        evidence_selection=[_action(), _finished()],
        rca_synthesis=[invented],
        assessment_correction=[invented],
    )
    final, record = run(incident, model, service=ToolService(records))

    assert final["failure"] is FailureCategory.UNGROUNDED_ASSESSMENT
    assert record.get("inv-1") is None
    assert model.count("assessment_correction") == 1, "the correction is spent exactly once"


def test_a_correction_that_grounds_the_assessment_is_accepted(incident, records):
    """The correction is another proposal, re-checked rather than trusted."""
    model = ScriptedModel(
        investigation_objective=['{"objective": "establish why checkout latency rose"}'],
        evidence_selection=[_action(), _finished()],
    )
    first, _ = run(incident, model, service=ToolService(records))
    reference = _admitted_ref(first)

    model = ScriptedModel(
        evidence_selection=[_action(), _finished()],
        rca_synthesis=[_assessment().replace("REF", "logs:payment-api:evt-999-99")],
        assessment_correction=[_assessment().replace("REF", reference)],
    )
    final, record = run(incident, model, service=ToolService(records))

    assert final.get("failure") is None
    assert record.get("inv-1") is not None


def test_a_failed_save_is_a_failed_execution(incident, records):
    """Nothing is delivered on a save that did not happen."""
    model = ScriptedModel(
        evidence_selection=[_action(), _finished()],
    )
    first, _ = run(incident, model, service=ToolService(records))
    reference = _admitted_ref(first)

    model = ScriptedModel(
        evidence_selection=[_action(), _finished()],
        rca_synthesis=[_assessment().replace("REF", reference)],
    )
    final, _ = run(incident, model, service=ToolService(records), record=RefusingRecord())

    assert final["failure"] is FailureCategory.SAVE_FAILED
    assert final.get("outcome") is None


def test_a_deadline_that_expires_before_synthesis_is_a_failed_execution(incident, records):
    def already_expired(state):
        state.bounds.expires_at = time.monotonic() - 1

    model = ScriptedModel(evidence_selection=[_finished()])
    final, record = run(incident, model, service=ToolService(records), prepare=already_expired)

    assert final["failure"] is FailureCategory.DEADLINE_EXPIRED
    assert record.get("inv-1") is None


# --- the outcome follows the evidence, not the model --------------------------------------------
def test_an_investigation_that_establishes_nothing_is_inconclusive_and_still_saved(
    incident, records
):
    """A real result rather than a failure: it observed something and could not settle a cause."""
    model = ScriptedModel(
        evidence_selection=[_action(), _finished()],
    )
    first, _ = run(incident, model, service=ToolService(records))
    reference = _admitted_ref(first)

    open_assessment = _assessment(
        candidates=[
            {
                "statement": "the cache may have evicted session keys",
                "label": "plausible",
                "established": False,
                "supporting": ["REF"],
            }
        ]
    ).replace("REF", reference)

    model = ScriptedModel(
        evidence_selection=[_action(), _finished()],
        rca_synthesis=[open_assessment],
    )
    final, record = run(incident, model, service=ToolService(records))

    assert final.get("failure") is None
    assert final["outcome"] is Outcome.INCONCLUSIVE
    assert record.get("inv-1") is not None, "an inconclusive investigation is still a result"
