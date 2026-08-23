"""The injection seam and the two controlled comparisons.

The seam's most important property is negative: nothing a caller can send reaches it. That is
asserted against the route's own construction rather than by reasoning about it, because a seam
that became reachable would still pass every test about what it does.

The comparisons themselves are checked on constructed records. What two live conditions would
actually produce is a fact about the model, not about this code, and asserting it here would be
asserting something no test can hold steady.
"""

from __future__ import annotations

from pathlib import Path

import answer_key
import comparisons
import pytest
import run_evaluation
from comparisons import (
    _condensed,
    adaptive_value,
    historical_answer,
    nearest_history,
    nearest_history_query,
    retrieval_influence,
)
from evaluation import Provenance, Source
from fake_knowledge import hash_embed, knowledge_retriever, retriever_from
from fake_operational_records import corpus_records
from fixed_path import ORDER, fixed_path
from judge import DIAGNOSIS_MATCH, Judged, Verdict
from test_completed_record import _record

from opspilot.assessment.contracts import Action, Candidate, SupportLabel
from opspilot.evidence.operations import Operation
from opspilot.investigation.harness import HARNESS, Harness, knowledge_for_prompts
from opspilot.llm import client as llm_client
from opspilot.retrieval.retriever import POSTMORTEM, Passage
from opspilot.tools.contracts import ExecutionOutcome, IncidentRecord

LIVE = Source(Provenance.OBTAINED, "live")
OTHER_LIVE = Source(Provenance.OBTAINED, "live")


def _with(**update):
    return _record().model_copy(update=update)


def _candidate(
    statement: str,
    supporting: tuple[str, ...] = (),
    label: SupportLabel = SupportLabel.LEADING,
):
    return Candidate(statement=statement, label=label, supporting=list(supporting))


def _assessed(candidates=(), actions=()):
    return _record().assessment.model_copy(
        update={"candidates": list(candidates), "actions": list(actions)}
    )


def _judgement(category: str) -> Judged:
    return Judged("inc-004", {DIAGNOSIS_MATCH: Verdict(category, "because")}, "a-deployment")


# --- the seam is unreachable from the API ---------------------------------------------------------
def test_the_streaming_route_never_passes_a_harness():
    """Asserted against the route's own source, because this is the property that matters and it
    would survive every behavioural test if it broke."""
    api = (Path(run_evaluation.REPO_ROOT) / "src" / "opspilot" / "api.py").read_text(
        encoding="utf-8"
    )

    assert "HARNESS" not in api
    assert "Harness" not in api
    assert "harness" not in api


def test_the_harness_is_not_a_setting():
    """A configuration setting would put it in reach of the deployed environment."""
    config = (Path(run_evaluation.REPO_ROOT) / "src" / "opspilot" / "config.py").read_text(
        encoding="utf-8"
    )

    assert "HARNESS" not in config and "harness" not in config


def test_a_run_given_no_harness_behaves_as_though_there_were_none():
    passages = [PASSAGE]

    assert knowledge_for_prompts(passages, None) == passages
    assert knowledge_for_prompts(passages, Harness()) == passages


def test_withholding_keeps_passages_from_prompts_only():
    """Retrieval still ran and the record still carries it; the roles simply were not shown it."""
    passages = [PASSAGE]

    assert knowledge_for_prompts(passages, Harness(withhold_knowledge=True)) == []
    assert passages, "the run's own knowledge set is untouched"


def test_the_seam_travels_under_one_key():
    assert HARNESS == "harness"


# --- the fixed path issues its order whatever it observes ----------------------------------------
class _Evidence:
    def __init__(self, operations, observations=()):
        self.operations = list(operations)
        self.observations = list(observations)


class _Incident:
    incident_id = "inc-004"
    scope = "checkout-api"
    time_anchor = None


def _step(n: int):
    operations = [Operation(f"op-{i:04d}", "x", ExecutionOutcome.SUCCEEDED) for i in range(n)]
    action, result = fixed_path(None, _Incident(), "objective", _Evidence(operations), [], (), 8)
    return action, result


def test_the_fixed_path_issues_the_same_order_regardless_of_what_it_observed():
    assert [_step(n)[0].capability for n in range(len(ORDER))] == list(ORDER)


def test_the_fixed_path_makes_no_model_call():
    """The proposal is what is being replaced, so a run on this path must not account for calls it
    never made."""
    assert _step(0)[1] is None


def test_the_fixed_path_finishes_once_its_order_is_spent():
    action, _ = _step(len(ORDER))

    assert action.is_finished


def test_the_fixed_path_does_not_branch_on_what_it_found():
    """Same step, wildly different evidence, same capability. This is the control's whole claim."""
    operations = [Operation("op-0001", "x", ExecutionOutcome.SUCCEEDED)]
    empty = fixed_path(None, _Incident(), "o", _Evidence(operations), [], (), 8)[0]
    full = fixed_path(
        None, _Incident(), "o", _Evidence(operations, _record().observations), [], (), 8
    )[0]

    assert empty.capability == full.capability == ORDER[1]


def test_a_target_the_fixed_path_learns_from_dependencies_arrives_too_late_to_query():
    """The structural claim the adaptive-value comparison rests on.

    Dependencies are the last thing the script asks for, so a service it first hears about there
    is a service it can never go and query: the step that would have asked for that service's
    metrics is spent, and the path has no way back to it. This is not an argument that a fixed
    order is a worse order. No rearrangement helps, because whichever step runs last learns
    something the steps before it could have used.
    """
    assert ORDER[-1] == "get_service_dependencies"

    after_dependencies, _ = _step(len(ORDER))
    assert after_dependencies.is_finished
    assert after_dependencies.capability == ""

    # And the one metrics step it does get is bound to the alerting service, never to a service
    # the run has yet to hear of.
    metrics_step, _ = _step(ORDER.index("get_metrics"))
    assert metrics_step.capability == "get_metrics"
    assert metrics_step.arguments["service"] == _Incident.scope
    assert "metric" not in metrics_step.arguments, (
        "the fixed metrics step asks for every series the service has, so hiding one behind a "
        "name would not put it out of reach; only a different service does that"
    )


# --- adaptive value ------------------------------------------------------------------------------
SCENARIO = {
    "id": "inc-004",
    "expected_evidence": ["logs:checkout-api:evt-005-01", "deploys:checkout-api:dep-1"],
    "red_herring": "deploys:checkout-api:dep-1",
}


def test_evidence_only_the_adaptive_path_reached_is_reported():
    adaptive = _record()
    fixed = _with(observations=[])

    result = adaptive_value(SCENARIO, adaptive, fixed, LIVE, OTHER_LIVE)

    assert result.differed
    assert any(d.dimension == "required evidence" for d in result.differences)


def test_a_red_herring_only_the_fixed_path_rested_on_is_reported():
    fixed = _with(
        assessment=_assessed([_candidate("a deploy did it", ("deploys:checkout-api:dep-1",))])
    )
    adaptive = _with(assessment=_assessed([_candidate("the pool exhausted")]))

    result = adaptive_value(SCENARIO, adaptive, fixed, LIVE, OTHER_LIVE)

    assert any(d.dimension == "red herring" for d in result.differences)


def test_the_cause_signal_comes_from_the_one_judge_asked_of_each_condition():
    """Not a second judge and not a new rubric: the same judgement, made once per record, compared
    here."""
    same = _with(observations=[], assessment=_assessed())

    result = adaptive_value(
        SCENARIO, same, same, LIVE, OTHER_LIVE, _judgement("leads"), _judgement("absent")
    )

    difference = next(d for d in result.differences if d.dimension == "the cause")
    assert "leads" in difference.detail and "absent" in difference.detail


def test_the_cause_signal_is_silent_where_the_fixed_path_did_as_well():
    same = _with(observations=[], assessment=_assessed())

    result = adaptive_value(
        SCENARIO, same, same, LIVE, OTHER_LIVE, _judgement("leads"), _judgement("leads")
    )

    assert not any(d.dimension == "the cause" for d in result.differences)


def test_no_difference_is_a_result_rather_than_a_failure():
    same = _with(observations=[], assessment=_assessed())

    result = adaptive_value(SCENARIO, same, same, LIVE, OTHER_LIVE)

    assert result.ran and not result.differed


def test_two_conditions_replaying_one_recording_are_refused():
    cassette = Source(Provenance.REPLAYED, "eval/cassettes/inc-004.json")

    with pytest.raises(ValueError, match="identical whatever the condition"):
        adaptive_value(SCENARIO, _record(), _record(), cassette, cassette)


# --- retrieval influence -------------------------------------------------------------------------
RETRIEVAL = {"id": "inc-007"}
PASSAGE = Passage(
    reference="postmortem:inc-003",
    category="postmortem",
    title="An earlier backlog",
    text="The consumer crash-looped on a poison message.",
    services=("notification-worker",),
    score=0.1,
)


def test_a_scenario_that_retrieved_nothing_is_not_evaluable():
    """No influence to withhold, which is not the same as withholding it and seeing no change."""
    result = retrieval_influence(
        RETRIEVAL, _with(passages=[]), _with(passages=[]), LIVE, OTHER_LIVE
    )

    assert not result.ran
    assert "no influence" in result.note


def test_a_different_leading_candidate_is_reported():
    shown = _with(passages=[PASSAGE], assessment=_assessed([_candidate("a recurrence")]))
    withheld = _with(passages=[PASSAGE], assessment=_assessed([_candidate("something new")]))

    result = retrieval_influence(RETRIEVAL, shown, withheld, LIVE, OTHER_LIVE)

    assert any(d.dimension == "the leading candidate" for d in result.differences)


def test_a_different_action_is_reported():
    shown = _with(
        passages=[PASSAGE], assessment=_assessed(actions=[Action(action="roll back", now=True)])
    )
    withheld = _with(
        passages=[PASSAGE], assessment=_assessed(actions=[Action(action="wait", now=False)])
    )

    result = retrieval_influence(RETRIEVAL, shown, withheld, LIVE, OTHER_LIVE)

    assert any(d.dimension == "an action recommended" for d in result.differences)


def test_every_difference_names_the_condition_it_fell_on():
    """The direction is the finding. A difference reporting only that the two conditions differed
    cannot say whether knowledge reaching reasoning changed anything, which is the question."""
    shown = _with(
        passages=[PASSAGE],
        assessment=_assessed([_candidate("a recurrence")], [Action(action="roll back", now=True)]),
    )
    withheld = _with(
        passages=[PASSAGE],
        assessment=_assessed([_candidate("something new")], [Action(action="wait", now=False)]),
        operations=[
            *_record().operations,
            Operation("op-99", "search_past_incidents", ExecutionOutcome.SUCCEEDED),
        ],
    )

    result = retrieval_influence(RETRIEVAL, shown, withheld, LIVE, OTHER_LIVE)

    assert result.differences, "the two conditions plainly differ"
    for difference in result.differences:
        assert "shown" in difference.detail or "withheld" in difference.detail, (
            f"{difference.dimension} does not say which condition it fell on: {difference.detail}"
        )
    capability = next(d for d in result.differences if d.dimension == "a capability proposed")
    assert "withheld" in capability.detail and "search_past_incidents" in capability.detail


def test_a_capability_only_one_condition_asked_for_is_reported():
    shown = _with(passages=[PASSAGE])
    withheld = _with(
        passages=[PASSAGE],
        operations=[
            *_record().operations,
            Operation("op-99", "search_past_incidents", ExecutionOutcome.SUCCEEDED),
        ],
    )

    result = retrieval_influence(RETRIEVAL, shown, withheld, LIVE, OTHER_LIVE)

    assert any(d.dimension == "a capability proposed" for d in result.differences)


def test_retrieval_differing_between_conditions_is_noted_as_a_second_variable():
    """Withholding influence keeps the tool counts comparable. If they moved anyway then more than
    the one variable did, and the comparison says so rather than reading the difference as the
    effect of the variable."""
    shown = _with(passages=[PASSAGE, _record().passages[0]])
    withheld = _with(passages=[PASSAGE])

    result = retrieval_influence(RETRIEVAL, shown, withheld, LIVE, OTHER_LIVE)

    assert "more than the one variable moved" in result.note


# --- a throttled condition is a comparison nobody could set up, not a lost report ----------------
def test_a_condition_that_cannot_be_obtained_is_reported_rather_than_ending_the_run(monkeypatch):
    """Both conditions are live calls, the one part of a comparison that can fail for reasons
    outside the repository. Losing an otherwise good report to a throttled deployment would throw
    away every scenario result that had already been computed."""
    monkeypatch.setattr(run_evaluation.config, "AZURE_OPENAI_DEPLOYMENT", "gpt-x")
    monkeypatch.setattr(
        run_evaluation,
        "build_chat_model",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429 rate limit")),
    )

    result = run_evaluation.compare_adaptive({"id": "inc-004", "expected_evidence": []})

    assert not result.ran
    assert "429 rate limit" in result.note


def test_a_throttled_retrieval_condition_is_reported_the_same_way(monkeypatch):
    monkeypatch.setattr(run_evaluation.config, "AZURE_OPENAI_DEPLOYMENT", "gpt-x")
    monkeypatch.setattr(
        run_evaluation,
        "build_chat_model",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429 rate limit")),
    )

    result = run_evaluation.compare_retrieval_influence({"id": "inc-007"})

    assert not result.ran and "429" in result.note


# --- the nearest-history shortcut ----------------------------------------------------------------
# What is asserted here is that the shortcut is a shortcut: that it reasons about nothing, reads no
# current evidence, and reports what retrieval actually returned. What is deliberately not asserted
# is that the authored precedent ranks first. The embedder these fixtures use is 32 hashed
# dimensions against the deployed 1536, so its ordering is not evidence about the deployed one, and
# a local assertion of semantic rank would be a claim this fixture cannot support.
_SHORTCUT_SCENARIOS = ("inc-004", "inc-007")


def _scenario(scenario_id: str) -> dict:
    return next(s for s in answer_key.SCENARIOS if s["id"] == scenario_id)


def _incident(scenario_id):
    return IncidentRecord(**corpus_records().incident(scenario_id, deadline_s=10))


def _returning(*references: str):
    """A real retriever over hand-built write-ups, for the tops the authored corpus will not
    produce on demand. Real, because the capability accepts nothing else: it is typed to the
    retriever, so a duck-typed stand-in would be testing a path production cannot take."""
    body = "checkout deployment queue notification cache"
    documents = [
        {
            "id": f"{ref}#0",
            "chunk_id": f"{ref}#0",
            "category": POSTMORTEM,
            "doc_id": ref,
            "title": ref,
            "text": f"{ref} {body}",
            "services": ["checkout-api"],
            "identifiers": [],
            "date": None,
            "provenance": {},
            "embedding": hash_embed(f"{ref} {body}", 32),
        }
        for ref in references
    ]
    return retriever_from(documents)


class _Spy:
    """Records the search the shortcut issued, standing in for the capability it calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def __call__(self, _retriever, _deadline, *, query, k, service=None):
        self.calls.append((query, k))
        passage = Passage(
            reference="postmortem:inc-104",
            category=POSTMORTEM,
            title="t",
            text="",
            services=(),
            score=1.0,
        )
        return [passage], [passage.reference]


def test_the_shortcut_runs_on_the_scenarios_that_name_a_precedent_and_no_others():
    """Which scenarios carry it is decided by the answer key naming the precedent a reasoning-free
    lookup should reach. Elsewhere there is nothing for the shortcut to be right or wrong about."""
    carrying = tuple(
        s["id"] for s in answer_key.SCENARIOS if "nearest_history_should_select" in s["evaluation"]
    )
    assert carrying == _SHORTCUT_SCENARIOS

    ran = [
        c
        for c in run_evaluation.run_comparisons(answer_key.SCENARIOS)
        if c.name == "nearest history"
    ]
    assert [c.scenario_id for c in ran] == list(_SHORTCUT_SCENARIOS)


def test_the_shortcut_makes_no_model_call(monkeypatch):
    """Not by instruction but by construction: it is handed no model and reaches for none. A
    baseline that reasoned would be a second investigation, and beating that would say nothing
    about whether retrieval on its own is enough."""

    def _refuse(*_, **__):
        raise AssertionError("the shortcut built a model")

    monkeypatch.setattr(llm_client, "build_chat_model", _refuse)

    result = nearest_history(_scenario("inc-004"), _incident("inc-004"), knowledge_retriever())

    assert result.ran and result.conclusion


def test_the_shortcut_searches_once_on_the_incident_as_reported(monkeypatch):
    """The whole of what a shortcut has to work with. Searching on the authored cause would be
    searching with the answer already in hand, and one search is the whole mechanism."""
    incident = _incident("inc-004")
    spy = _Spy()
    monkeypatch.setattr(comparisons, "search_past_incidents", spy)

    nearest_history(_scenario("inc-004"), incident, knowledge_retriever())

    assert [query for query, _ in spy.calls] == [incident.short_description]
    assert nearest_history_query(incident) == incident.short_description


def test_the_shortcut_reuses_the_recorded_answer_rather_than_the_current_one():
    """It copies what the past incident says, which is the point: on the misdirection scenario that
    recorded answer is a rollback, and the current incident's own cause is nowhere in it."""
    result = nearest_history(_scenario("inc-004"), _incident("inc-004"), knowledge_retriever())

    cause, resolution = historical_answer("postmortem:inc-104")
    assert cause and resolution
    assert _condensed(cause) in result.conclusion
    assert "payment-gateway" not in result.conclusion, "the current incident's cause leaked in"


def test_a_precedent_other_than_the_authored_one_is_reported_rather_than_replaced():
    """A failed premise, not a reason to fake the experiment. The shortcut is only interesting
    where it lands where a shortcut would land, so a different top means the thing this scenario
    exists to test did not happen, and the report says which incident actually came first."""
    result = nearest_history(
        _scenario("inc-004"), _incident("inc-004"), _returning("postmortem:inc-101")
    )

    assert not result.ran
    assert "postmortem:inc-101" in result.note, "the report does not say what actually came first"
    assert "postmortem:inc-104" in result.note, "the report does not say what was expected"
    assert not result.conclusion, "an answer was produced for an experiment that did not run"


def test_a_search_that_returns_nothing_is_reported_rather_than_guessed():
    result = nearest_history(_scenario("inc-007"), _incident("inc-007"), _returning())

    assert not result.ran and not result.conclusion


def test_the_shortcut_names_the_incident_retrieval_actually_returned():
    result = nearest_history(
        _scenario("inc-007"), _incident("inc-007"), _returning("postmortem:inc-003")
    )

    assert result.ran
    assert "postmortem:inc-003" in result.conclusion
