"""The offline judge, and the boundaries it must not cross.

Three properties matter more than the categories themselves. The judge cannot reach a deterministic
result, which is structural here rather than a rule: a `ScenarioResult` has nowhere to put a
category. It refuses a response that is not a judgement instead of repairing it into one. And it is
not shown what code has already decided, or the scenario title, which names the cause it is being
asked to look for.

The model is a stand-in throughout. What the real deployment would answer is not a property of this
code, and asserting a category from a live call would be asserting something about the model.
"""

from __future__ import annotations

import json

import pytest
import run_evaluation
from answer_key import SCENARIOS
from evaluation import Provenance, ScenarioResult, Source
from judge import (
    DIAGNOSIS_MATCH,
    MATCH_CATEGORIES,
    QUALITIES,
    QUALITY_CATEGORIES,
    Judged,
    UnusableVerdict,
    context_for,
    judge,
    read_verdicts,
)
from run_evaluation import _judge_deployment, _judge_lines, judged, render
from test_completed_record import _record

from opspilot.llm.base import ChatResult

SCENARIO = next(s for s in SCENARIOS if s["id"] == "inc-005")
REPORTED = "Checkout latency up and some carts/sessions dropping."


def _sound(**overrides) -> str:
    payload = {name: {"category": "meets", "why": "a sentence"} for name in QUALITIES}
    payload[DIAGNOSIS_MATCH] = {"category": "leads", "why": "a sentence"}
    payload.update(overrides)
    return json.dumps(payload)


class _Model:
    """Answers with whatever it was given, and remembers what it was asked."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.messages: list = []

    def complete(self, task, messages, deadline_s=None):
        self.messages = messages
        return ChatResult(text=self.text, task=task, deployment="a-deployment")


# --- the vocabulary is fixed, and nothing outside it is a judgement -------------------------------
def test_a_sound_response_yields_one_verdict_for_each_quality_and_the_match():
    verdicts = read_verdicts(_sound())

    assert set(verdicts) == {*QUALITIES, DIAGNOSIS_MATCH}
    assert all(v.why for v in verdicts.values())


def test_a_category_outside_the_vocabulary_is_refused_rather_than_coerced():
    """The nearest value would be a judgement nobody made, and reported as one."""
    with pytest.raises(UnusableVerdict, match="excellent"):
        read_verdicts(_sound(usefulness_and_coherence={"category": "excellent", "why": "a"}))


def test_a_quality_category_is_not_accepted_for_the_diagnosis_match():
    """Two vocabularies, because the match says where in the candidate list the cause landed."""
    with pytest.raises(UnusableVerdict, match=DIAGNOSIS_MATCH):
        read_verdicts(_sound(diagnosis_match={"category": "meets", "why": "a"}))

    assert set(QUALITY_CATEGORIES).isdisjoint(MATCH_CATEGORIES)


def test_a_missing_verdict_is_refused_rather_than_defaulted():
    payload = json.loads(_sound())
    del payload["recommendation_fit"]

    with pytest.raises(UnusableVerdict, match="recommendation_fit"):
        read_verdicts(json.dumps(payload))


def test_a_category_without_a_reason_is_not_a_judgement():
    with pytest.raises(UnusableVerdict, match="without saying why"):
        read_verdicts(_sound(appropriate_uncertainty={"category": "partial", "why": "   "}))


def test_a_response_that_is_not_json_is_refused():
    with pytest.raises(UnusableVerdict, match="no JSON object"):
        read_verdicts("I think the brief was pretty good, honestly.")


def test_json_the_model_wrapped_in_prose_is_still_read():
    verdicts = read_verdicts(f"Here is my assessment:\n```json\n{_sound()}\n```\nHope that helps.")

    assert verdicts[DIAGNOSIS_MATCH].category == "leads"


# --- what the judge is shown, and what it is not --------------------------------------------------
def test_the_judge_reads_the_brief_the_incident_and_the_expectation():
    context = context_for(_record(), SCENARIO, REPORTED)

    assert REPORTED in context
    assert _record().brief.text in context
    assert SCENARIO["root_cause"] in context
    assert SCENARIO["evaluation"]["behavior_tested"].split(".")[0] in context


def test_the_judge_is_not_shown_what_code_has_already_decided():
    """`accepted_outcomes` and `absent_evidence` are settled mechanically. A judge shown them is
    invited to re-decide them, and its answer would be reported beside the real one."""
    context = context_for(_record(), SCENARIO, REPORTED)

    assert "accepted_outcomes" not in context
    assert "absent_evidence" not in context
    for absence in SCENARIO["evaluation"]["absent_evidence"]:
        assert absence["why"] not in context


def test_the_judge_is_not_shown_the_scenario_title():
    """The title names the cause. Handing it to a judge asked how well a brief explains itself
    would let it read the answer back rather than judge the account."""
    assert SCENARIO["title"] not in context_for(_record(), SCENARIO, REPORTED)


def test_the_judge_is_not_shown_the_evidence_set():
    context = context_for(_record(), SCENARIO, REPORTED)

    for observation in _record().observations:
        assert observation.evidence_ref not in context
    for operation in _record().operations:
        assert operation.operation_ref not in context


def test_a_scenario_with_no_expected_cause_states_none():
    """The benign fixture. The rubric answers `not_applicable` rather than matching against a
    cause that was never authored, which is why none is written into the context."""
    context = context_for(_record(), {"id": "benign-01", "evaluation": {}}, REPORTED)

    assert "Expected cause" not in context
    assert "not_applicable" in MATCH_CATEGORIES


def test_the_deployment_that_answered_is_recorded():
    result = judge(_Model(_sound()), _record(), SCENARIO, REPORTED)

    assert result.ran
    assert result.deployment == "a-deployment"
    assert result.scenario_id == "inc-005"


def test_the_rubric_is_the_system_message_and_the_context_is_the_user_message():
    model = _Model(_sound())

    judge(model, _record(), SCENARIO, REPORTED)

    system, user = model.messages
    assert system.role == "system" and "You are an evaluator" in system.content
    assert user.role == "user" and REPORTED in user.content


# --- the judge is reported beside the deterministic result, never inside it -----------------------
def test_a_scenario_result_has_nowhere_to_put_a_category():
    """Never combined into one number, enforced by the shape rather than by remembering to."""
    assert not {"judge", "judgement", "category", "verdicts"} & set(
        ScenarioResult.__dataclass_fields__
    )


def test_the_report_prints_the_categories_beside_the_result():
    verdicts = read_verdicts(_sound())

    lines = "\n".join(_judge_lines(Judged("inc-005", verdicts, "a-deployment")))

    assert "a-deployment" in lines
    assert all(name in lines for name in (*QUALITIES, DIAGNOSIS_MATCH))
    # Printed, and never counted: a total over these would be the one number the design refuses.
    assert not any(word in lines.lower() for word in ("score", "total", "overall", "passed"))


def test_a_judgement_that_did_not_run_says_why():
    lines = "\n".join(_judge_lines(Judged("inc-001", note="no investigation to judge")))

    assert "not run" in lines and "no investigation to judge" in lines


def test_the_judge_deployment_is_recorded_in_the_configuration_identity():
    """Two reports judged by different models are not comparable, and with only the runtime
    deployment on the page they would look as though they were."""
    verdicts = read_verdicts(_sound())

    assert _judge_deployment([Judged("inc-005", verdicts, "a-deployment")]) == "a-deployment"
    assert "did not run" in _judge_deployment([Judged("inc-005", note="no deployment")])


def test_the_report_carries_the_judge_deployment():
    verdicts = read_verdicts(_sound())
    results = [ScenarioResult("inc-005", Source(Provenance.REPLAYED, "a.json"))]

    report = render(results, {}, "2026-08-20T00:00:00Z", [Judged("inc-005", verdicts, "gpt-x")])

    assert "judge_deployment" in report and "gpt-x" in report


# --- every way there is no judgement is said, and they are told apart -----------------------------
def test_a_scenario_that_did_not_run_is_not_judged():
    result = judged(None, SCENARIO, REPORTED)

    assert not result.ran
    assert "no investigation to judge" in result.note


def test_without_the_judge_deployment_the_judge_is_reported_not_run(monkeypatch):
    """The lane still replays and still checks; only the judgement is missing, and it says so.
    The judge's own settings decide this, not the runtime's: a revision serving investigations
    does not need the judge, and the judge does not run on the runtime's deployment."""
    monkeypatch.setattr(run_evaluation.config, "AZURE_CLAUDE_ENDPOINT", "")
    monkeypatch.setattr(run_evaluation.config, "AZURE_CLAUDE_DEPLOYMENT", "")

    result = judged(_record(), SCENARIO, REPORTED)

    assert not result.ran
    assert "no judge model deployment is configured" in result.note


def test_a_deployment_that_cannot_be_reached_is_not_reported_as_a_bad_verdict(monkeypatch):
    """Distinct from an unusable answer. The judge said nothing, so saying it answered badly would
    be a different and untrue account of the run."""
    monkeypatch.setattr(run_evaluation.config, "AZURE_CLAUDE_ENDPOINT", "https://x.invalid/")
    monkeypatch.setattr(run_evaluation.config, "AZURE_CLAUDE_DEPLOYMENT", "claude-x")
    monkeypatch.setattr(
        run_evaluation,
        "build_judge_model",
        lambda *a, **k: (_ for _ in ()).throw(ImportError("no")),
    )

    result = judged(_record(), SCENARIO, REPORTED)

    assert "could not be reached" in result.note
    assert "usable verdict" not in result.note


def test_an_unusable_answer_is_reported_as_one(monkeypatch):
    monkeypatch.setattr(run_evaluation.config, "AZURE_CLAUDE_ENDPOINT", "https://x.invalid/")
    monkeypatch.setattr(run_evaluation.config, "AZURE_CLAUDE_DEPLOYMENT", "claude-x")
    monkeypatch.setattr(run_evaluation, "build_judge_model", lambda *a, **k: _Model("nonsense"))

    result = judged(_record(), SCENARIO, REPORTED)

    assert not result.ran
    assert "did not return a usable verdict" in result.note
