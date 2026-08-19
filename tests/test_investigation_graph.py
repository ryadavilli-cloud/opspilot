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

from opspilot import config
from opspilot.api import initial_state
from opspilot.assessment.contracts import Outcome
from opspilot.investigation.graph import MODEL, RECORD, SERVICE, build_graph
from opspilot.investigation.state import FailureCategory
from opspilot.llm.base import ChatResult
from opspilot.record.memory import InMemoryCompletedInvestigations
from opspilot.record.port import AlreadySaved
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

    def call(self, tool_name: str, remaining_s: float | None = None, /, **_: Any) -> Any:
        return error_result(
            tool_name, "unreachable", time.perf_counter(), ExecutionOutcome.UNAVAILABLE
        )


class RefusingRecord:
    """A record that cannot be written. A save that fails must not deliver anything."""

    def save(self, record: Any) -> None:
        raise AlreadySaved(record.investigation_id)

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
    record = record if record is not None else InMemoryCompletedInvestigations()
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


# --- the run's deadline reaches the capability ---------------------------------------------------
class _RecordingService:
    """A registry that records the deadline each call was given, and answers nothing."""

    tool_names = ("get_correlated_alerts",)

    def __init__(self) -> None:
        self.deadlines: list[float | None] = []

    def call(self, tool_name: str, remaining_s: float | None = None, /, **_: Any) -> Any:
        self.deadlines.append(remaining_s)
        return error_result(
            tool_name, "unreachable", time.perf_counter(), ExecutionOutcome.UNAVAILABLE
        )


def test_a_capability_call_carries_the_investigations_remaining_time(incident):
    """The bound is one deadline over the whole run, so what reaches a source is what the run has
    left, not a ceiling the source picked for itself."""
    service = _RecordingService()
    model = ScriptedModel(evidence_selection=[_action(), _finished()])

    run(incident, model, service=service)

    assert service.deadlines, "no capability was called"
    for remaining in service.deadlines:
        assert remaining is not None, "the call was made without the run's remaining time"
        assert 0 < remaining <= config.INVESTIGATION_DEADLINE_SECONDS


def test_a_run_with_almost_no_time_left_passes_almost_none_of_it_on(incident):
    """What the ceiling alone cannot express: the call inherits how little is left, so it cannot
    run on past the investigation that asked for it."""
    service = _RecordingService()
    model = ScriptedModel(evidence_selection=[_action(), _finished()])

    def nearly_expired(state):
        state.bounds.expires_at = time.monotonic() + 0.5

    run(incident, model, service=service, prepare=nearly_expired)

    assert service.deadlines and all(r is not None and r <= 0.5 for r in service.deadlines)


# --- the one return ------------------------------------------------------------------------------
# Analysis may ask for more, and only code decides whether it gets it. Each condition is stated
# separately, because a return granted for the wrong reason and a return refused for the wrong
# reason look identical from outside: both are one run that ended.
LOGS = {"capability": "query_logs", "arguments": {"service": "checkout-api"}}
RETURN_QUESTION = "what did checkout-api log at the onset"
ASKED_IN_THE_FIRST_PASS = "which alerts correlate with this incident"


class SeenModel(ScriptedModel):
    """A scripted model that keeps what it was asked, for the one test about seeding."""

    def __init__(self, **by_task: list[str]) -> None:
        super().__init__(**by_task)
        self.seen: list[tuple[str, str]] = []

    def complete(self, task: str, messages: list[Any]) -> ChatResult:
        self.seen.append((task, " ".join(str(m.content) for m in messages)))
        return super().complete(task, messages)


def _logs_action(question: str = RETURN_QUESTION) -> str:
    return json.dumps({**LOGS, "question": question})


def _asking(reference: str, *, kind: str = "log_event", question: str = RETURN_QUESTION) -> str:
    """An assessment that grounds on its own and still names something it could not settle."""
    return _assessment(unresolved_question={"question": question, "evidence_kind": kind}).replace(
        "REF", reference
    )


@pytest.fixture
def reference(incident, records) -> str:
    """The reference admission assigns the alerts observation, learned by running for it.

    The same two-pass shape the end-to-end tests use: an assessment can only ground on a reference
    this run really admitted, and only the run knows what that is.
    """
    model = ScriptedModel(evidence_selection=[_action(), _finished()])
    first, _ = run(incident, model, service=ToolService(records))
    return _admitted_ref(first)


def _returning(reference: str, *, model_class: type = ScriptedModel, **asking: Any) -> Any:
    """Gather, ask for more, gather again, settle. The plan a return is supposed to produce."""
    return model_class(
        investigation_objective=['{"objective": "establish why checkout latency rose"}'],
        evidence_selection=[_action(), _finished(), _logs_action(), _finished()],
        rca_synthesis=[
            _asking(reference, **asking),
            _assessment().replace("REF", reference),
        ],
    )


def test_analysis_can_send_the_investigation_back_to_gather_once(incident, records, reference):
    """The designed feedback loop. The analyst names what it could not settle and the kind of
    evidence that would settle it; the Supervisor authorizes, and gathering resumes."""
    model = _returning(reference)

    final, _ = run(incident, model, service=ToolService(records))

    assert final["bounds"].return_used, "the return was never authorized"
    assert model.count("rca_synthesis") == 2, "synthesis did not run again after the return"
    assert "returned to gathering" in [e.action for e in final["events"]]
    assert final.get("failure") is None


def test_the_question_reaches_the_investigator(incident, records, reference):
    """Seeded, not merely recorded. The point of a return is that gathering resumes on the thing
    analysis could not settle, which means the investigator has to be told what that was."""
    model = _returning(reference, model_class=SeenModel)

    run(incident, model, service=ToolService(records))

    selections = [text for task, text in model.seen if task == "evidence_selection"]
    assert not any(RETURN_QUESTION in text for text in selections[:2]), (
        "the question appeared before analysis had asked for it"
    )
    assert any(RETURN_QUESTION in text for text in selections[2:]), (
        "gathering resumed without being told what it was resumed for"
    )


def test_the_return_happens_at_most_once(incident, records, reference):
    """`return_used` is spent by the first return, so a second request is not granted however the
    analyst words it. Without this the two roles could hand work back and forth until a bound
    stopped them, which is the general loop the design does not have."""
    model = ScriptedModel(
        investigation_objective=['{"objective": "establish why checkout latency rose"}'],
        evidence_selection=[_action(), _finished(), _logs_action(), _finished()],
        # The second request is a fresh question with a kind a capability supplies, so every
        # condition except the spent bound would authorize it. Only `return_used` can refuse this.
        rca_synthesis=[
            _asking(reference),
            _asking(reference, question="and what did the metrics show at the onset"),
        ],
    )

    final, _ = run(incident, model, service=ToolService(records))

    assert final.get("failure") is None
    assert model.count("rca_synthesis") == 2, "a second return re-entered gathering"


def test_a_question_no_capability_can_answer_is_not_authorized(incident, records, reference):
    """The evidence kind is a membership test against what the proposable capabilities supply. A
    kind nothing produces cannot be gone and got, so the matter stands as an unknown rather than
    spending a pass that could only come back empty."""
    model = _returning(reference, kind="a signed statement from the vendor")

    final, _ = run(incident, model, service=ToolService(records))

    assert not final["bounds"].return_used
    assert model.count("rca_synthesis") == 1
    assert "returned to gathering" not in [e.action for e in final["events"]]


def test_a_request_naming_no_evidence_kind_is_not_authorized(incident, records, reference):
    """The field is optional and a half-filled one is not a request. Treating a blank kind as
    permission would make the return the default rather than the exception."""
    model = _returning(reference, kind="")

    final, _ = run(incident, model, service=ToolService(records))

    assert not final["bounds"].return_used


def test_a_question_this_run_already_answered_is_not_authorized(incident, records, reference):
    """The same membership test gathering itself uses. A return is a step like any other, so a
    question this run already put does not become askable again by arriving from the analyst."""
    model = _returning(reference, question=ASKED_IN_THE_FIRST_PASS)

    final, _ = run(incident, model, service=ToolService(records))

    assert not final["bounds"].return_used


def test_a_return_is_refused_when_the_model_budget_cannot_afford_what_follows(
    incident, records, reference
):
    """Costed before it is granted. A return needs a proposal, a second synthesis, and the
    correction that synthesis may still need; granting one without room for all three would end a
    run that already held a usable assessment as a failed execution instead."""
    model = _returning(reference)

    def nearly_spent(state):
        state.bounds.model_calls = 4

    final, _ = run(incident, model, service=ToolService(records), prepare=nearly_spent)

    assert not final["bounds"].return_used
    assert final.get("failure") is None, "refusing the return cost the run its assessment"


def test_a_return_is_refused_when_the_capability_cap_is_spent(incident, records, reference):
    """Resuming gathering with no capability call left would spend a model call reaching a
    proposal that nothing could execute."""
    model = _returning(reference)

    def one_call_only(state):
        state.bounds.capability_calls = 1

    final, _ = run(incident, model, service=ToolService(records), prepare=one_call_only)

    assert not final["bounds"].return_used


def test_the_resumed_gathering_is_bounded_like_any_other(incident, records, reference):
    """The return reopens gathering, not the bounds. What it asks for is spent from the same caps,
    so a run that returns cannot make more calls than one that does not."""
    model = _returning(reference)

    final, _ = run(incident, model, service=ToolService(records))

    assert final["capability_calls_made"] <= final["bounds"].capability_calls
    assert final["model_calls_made"] <= final["bounds"].model_calls


def test_the_question_does_not_outlive_the_step_it_was_seeded_into(incident, records, reference):
    """Seeded, then spent. If the investigator proposes something else, the question is not
    re-seeded on the next step, which would be a second return by another name."""
    model = _returning(reference)

    final, _ = run(incident, model, service=ToolService(records))

    assert final["open_question"] == ""


def test_a_refused_return_leaves_the_assessment_untouched(incident, records, reference):
    """When the return is unavailable the edge is not followed and nothing is edited: the
    assessment the analyst proposed is the one that is grounded and delivered."""
    model = _returning(reference, kind="nothing any capability supplies")

    final, _ = run(incident, model, service=ToolService(records))

    assert final.get("failure") is None
    assert final["assessment"].candidates
    assert final["outcome"] is Outcome.COMPLETE
