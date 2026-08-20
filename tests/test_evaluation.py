"""The offline evaluation's deterministic half.

The checks here are only worth anything if they can fail, and a check that reuses the runtime's
grounding function could be wired so that it never does: supply the admitted references from the
assessment itself and every record grounds against its own claims, including a fabricated one. So
the grounding check is proven by mutation rather than by reading its wiring. A sound record passes,
a record whose assessment cites something the evidence set does not hold fails as unresolved, and
one that offers retrieved knowledge as current operational support fails as knowledge-as-support.

The rest is what the design asks the mechanical layer to establish, and what it must refuse: an
outcome the scenario does not accept, an operation outside the registry, an authored absence the
investigation passed over, and a benign case answered with silence rather than with an affirmative
statement that nothing needs doing.
"""

from __future__ import annotations

import pytest
import run_evaluation
from answer_key import FIXTURE
from evaluation import (
    Provenance,
    ScenarioResult,
    Source,
    check_declared_absence_is_disclosed,
    check_grounding,
    check_no_immediate_action,
    check_no_write_was_attempted,
    check_outcome_is_accepted,
    evaluate,
    require_distinct,
)
from run_evaluation import _fixture_incident, render
from test_completed_record import _record

from opspilot.assessment.contracts import Action
from opspilot.evidence.operations import Operation
from opspilot.tools.contracts import ExecutionOutcome

LOG = "logs:checkout-api:evt-005-01"
RUNBOOK = "runbook:redis-cache-degradation"
GHOST = "logs:checkout-api:evt-does-not-exist"


def _mutated(**update: object):
    """One sound record with something changed. The record is frozen, so a mutation builds a new
    one rather than reaching into the old, which also keeps each test's record its own."""
    return _record().model_copy(update=update)


def _claiming(*references: str):
    """A record whose account rests on the references given, and whose evidence set is untouched."""
    record = _record()
    return _mutated(
        assessment=record.assessment.model_copy(update={"what_happened_refs": list(references)})
    )


# --- the grounding check can fail, and for the right reasons --------------------------------------
def test_a_sound_record_reports_no_grounding_failure():
    assert check_grounding(_record()) == []


def test_a_citation_the_evidence_set_does_not_hold_is_reported_as_unresolved():
    """The mutation that would pass if the admitted references were taken from the assessment.

    Only the assessment is corrupted; the evidence set is untouched, so the two disagree. A check
    that read its references from the claim would find them consistent with themselves.
    """
    failures = check_grounding(_claiming(GHOST))

    assert failures, "a claim resting on a reference this run never admitted was accepted"
    assert any("unresolved_reference" in failure for failure in failures)
    assert any(GHOST in failure for failure in failures)


def test_retrieved_knowledge_offered_as_current_support_is_reported():
    """A passage is what someone wrote down before the incident. It can explain a mechanism and it
    cannot show that anything is true of the system now, and the record carries it, so a check
    reading only whether a reference resolves would accept this."""
    failures = check_grounding(_claiming(RUNBOOK))

    assert any("knowledge_as_support" in failure for failure in failures)


def test_an_assessment_resting_on_nothing_is_reported_rather_than_passed():
    assert any("unsupported_claim" in failure for failure in check_grounding(_claiming()))


# --- read-only, from what the run attempted -------------------------------------------------------
def test_an_operation_outside_the_registry_is_reported():
    record = _mutated(
        operations=[
            *_record().operations,
            Operation("op-0099", "delete_deployments", ExecutionOutcome.SUCCEEDED),
        ]
    )

    failures = check_no_write_was_attempted(record)

    assert failures and "delete_deployments" in failures[0]


def test_a_run_using_only_registered_capabilities_reports_nothing():
    assert check_no_write_was_attempted(_record()) == []


# --- an authored absence must be reported, either way it truthfully happened ----------------------
ABSENCE_EXPECTED = {"absent_evidence": [{"capability": "get_deployments", "why": "authored"}]}


def _without_absences():
    return [o for o in _record().observations if not o.evidence_ref.startswith("absence:")]


def test_an_absence_the_run_recorded_as_evidence_satisfies_the_check():
    """The source answered and held nothing, which is an authoritative absence and is evidence."""
    assert check_declared_absence_is_disclosed(_record(), ABSENCE_EXPECTED) == []


def test_an_absence_reported_as_a_limitation_also_satisfies_it():
    """The source could not answer, which is not evidence and is still honest. Which of the two is
    correct depends on how the source behaved, so the check takes either, and silence is
    neither."""
    record = _mutated(observations=_without_absences())

    assert check_declared_absence_is_disclosed(record, ABSENCE_EXPECTED) == []


def test_an_absence_the_run_never_looked_for_is_reported():
    record = _mutated(observations=_without_absences(), limitations=[])

    failures = check_declared_absence_is_disclosed(record, ABSENCE_EXPECTED)

    assert failures and "get_deployments" in failures[0]


def test_a_scenario_declaring_no_absence_is_not_asked_to_disclose_one():
    assert check_declared_absence_is_disclosed(_record(), {"absent_evidence": []}) == []


# --- the outcome the scenario accepts -------------------------------------------------------------
def test_an_outcome_the_scenario_accepts_reports_nothing():
    assert check_outcome_is_accepted(_record(), {"accepted_outcomes": ["partial"]}) == []


def test_an_outcome_the_scenario_does_not_accept_is_reported():
    failures = check_outcome_is_accepted(_record(), {"accepted_outcomes": ["complete"]})

    assert failures and "partial" in failures[0]


# --- the benign case, answered affirmatively ------------------------------------------------------
def test_a_benign_case_answered_with_an_affirmative_no_action_now_passes():
    record = _mutated(
        assessment=_record().assessment.model_copy(
            update={
                "actions": [Action(action="watch the eviction rate over the next hour", now=False)]
            }
        )
    )

    assert check_no_immediate_action(record) == []


def test_a_benign_case_answered_with_immediate_action_is_reported():
    assert check_no_immediate_action(_record()), "an immediate action on a benign case was accepted"


def test_a_benign_case_answered_with_silence_is_reported_rather_than_passed():
    """The check exists to prove the system said nothing needs doing, which an empty brief does not
    say. Reading no recommendations as agreement would pass a run that simply produced nothing."""
    record = _mutated(assessment=_record().assessment.model_copy(update={"actions": []}))

    failures = check_no_immediate_action(record)

    assert failures and "nothing at all" in failures[0]


# --- where an investigation came from -------------------------------------------------------------
def test_a_scenario_with_a_recording_is_replayed_from_it():
    source = Source.for_scenario("inc-005")

    assert source.provenance is Provenance.REPLAYED
    assert source.detail.endswith("inc-005.json")


def test_a_scenario_with_no_recording_is_not_run_and_says_why():
    source = Source.for_scenario("inc-001")

    assert source.provenance is Provenance.NOT_RUN
    assert "no recording" in source.detail


def test_a_scenario_that_did_not_run_is_neither_passed_nor_failed():
    """Coverage that varies between runs makes two reports look alike when they are not, so a
    scenario with no recording is a stated result rather than an omission."""
    source = Source.for_scenario("inc-001")

    result = evaluate("inc-001", None, {"accepted_outcomes": ["complete"]}, source)

    assert not result.ran
    assert not result.passed
    assert not result.failures
    assert result.notes and "no recording" in result.notes[0]


# --- a comparison may not read one response into both of its conditions ---------------------------
def test_two_conditions_replaying_the_same_recording_are_refused():
    """The arrangement that would look like a clean null result. One cassette answers both arms
    identically whatever the condition changed, which does not show the variable made no
    difference; it shows the variable was never applied."""
    same = Source.for_scenario("inc-007")

    with pytest.raises(ValueError, match="identical whatever the condition"):
        require_distinct(same, same)


def test_two_conditions_recorded_separately_are_allowed():
    require_distinct(Source.for_scenario("inc-005"), Source.for_scenario("inc-007"))


def test_a_live_condition_is_not_refused_against_a_replayed_one():
    """Live responses differ per call, so nothing is shared to erase the variable."""
    require_distinct(Source(Provenance.OBTAINED, "live"), Source.for_scenario("inc-005"))


# --- how the benign fixture reaches the evaluation ------------------------------------------------
def test_the_fixture_is_reported_from_a_row_the_corpus_actually_holds():
    """Its context is derived rather than restated, so a drifting corpus breaks this rather than
    leaving the evaluation running against a symptom nothing generated."""
    incident = _fixture_incident()

    assert incident.incident_id == FIXTURE["id"]
    assert "429" in incident.short_description
    assert incident.opened_at.isoformat().startswith("2026-06-18")


def test_the_fixture_is_obtained_live_and_never_replayed():
    assert Source.for_fixture("gpt-5-mini").provenance is Provenance.OBTAINED


def test_the_fixture_without_a_deployment_is_reported_not_run():
    source = Source.for_fixture("")

    assert source.provenance is Provenance.NOT_RUN
    assert "never replayed" in source.detail


def test_a_live_fixture_run_that_fails_is_reported_rather_than_ending_the_run(monkeypatch):
    """The one step that can fail for reasons outside the repository. Losing every other result to
    an expired credential would throw away a report that was otherwise complete."""

    def _no_credential(*_: object) -> None:
        raise RuntimeError("no credential available")

    monkeypatch.setattr(run_evaluation, "build_chat_model", _no_credential)

    record, source = run_evaluation.obtain_fixture(Source(Provenance.OBTAINED, "live"))

    assert record is None
    assert source.provenance is Provenance.NOT_RUN
    assert "no credential available" in source.detail


# --- the report states coverage rather than implying it -------------------------------------------
def _rendered(*results: ScenarioResult) -> str:
    return render(list(results), {"model_deployment": "gpt-5-mini"}, "2026-08-20T00:00:00Z")


def test_the_report_names_how_each_scenario_ran():
    report = _rendered(
        ScenarioResult("inc-005", Source(Provenance.REPLAYED, "eval/cassettes/inc-005.json")),
        ScenarioResult("benign-01", Source(Provenance.OBTAINED, "run live against gpt-5-mini")),
    )

    assert "inc-005 - replayed" in report
    assert "benign-01 - obtained" in report
    assert "eval/cassettes/inc-005.json" in report


def test_a_scenario_that_did_not_run_is_said_so_rather_than_omitted():
    """Two reports covering different scenarios look alike unless the absent one is on the page."""
    report = _rendered(ScenarioResult("inc-001", Source(Provenance.NOT_RUN, "no recording")))

    assert "inc-001 - not_run" in report
    assert "Not run." in report
    assert "0 of 1 scenario(s) ran." in report


def test_named_failures_reach_the_report_and_no_score_does():
    report = _rendered(
        ScenarioResult(
            "inc-005",
            Source(Provenance.REPLAYED, "eval/cassettes/inc-005.json"),
            ["outcome: reported partial, which this scenario does not accept (complete)"],
        )
    )

    assert "which this scenario does not accept" in report
    assert "No composite score is reported" in report


def test_the_report_records_what_it_ran_under():
    assert "gpt-5-mini" in _rendered()
