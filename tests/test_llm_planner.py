"""LLMPlanner: parsing and fail-closed selection, all of it without a model.

The read-only registry is the hard boundary: the planner must never surface a mutating or
hallucinated tool, whatever the model returns.
"""

from __future__ import annotations

import pytest

from opspilot.diagnosis.contracts import DiagnosisContext, Hypothesis
from opspilot.diagnosis.llm_planner import LLMPlanner, extract_json_object
from opspilot.llm.base import ChatResult

CTX = DiagnosisContext(
    incident_id="inc-004",
    affected_services=["checkout-api"],
    onset="2026-06-28T10:15:00+00:00",
    category="payment",
)


class ScriptedModel:
    deployment = "scripted"

    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, task, messages):
        return ChatResult(text=self._text, task=task, deployment=self.deployment)


def test_extract_json_handles_think_and_fences():
    assert extract_json_object('<think>weigh options</think>{"a": 1}') == {"a": 1}
    assert extract_json_object('```json\n{"b": 2}\n```') == {"b": 2}
    assert extract_json_object('prose {"c": 3} trailer') == {"c": 3}
    with pytest.raises(ValueError):
        extract_json_object("no json here")


def test_valid_tool_selection_becomes_a_question():
    model = ScriptedModel(
        '{"next_tool": "get_deployments", "params": {"services": ["checkout-api"]}, '
        '"why": "what changed before onset"}'
    )
    plan = LLMPlanner(model).plan(CTX, answered=set(), observations=[])
    assert len(plan.questions) == 1
    question = plan.questions[0]
    assert question.call.tool == "get_deployments"
    assert question.call.params == {"services": ["checkout-api"]}


def test_mutating_tool_is_dropped_fail_closed():
    model = ScriptedModel('{"next_tool": "restart_service", "params": {"svc": "checkout-api"}}')
    plan = LLMPlanner(model).plan(CTX, answered=set(), observations=[])
    assert plan.questions == []  # a non-allowlisted tool never becomes an executable question


def test_plan_parses_a_batch_and_drops_bad_calls():
    model = ScriptedModel(
        '{"tool_calls": ['
        '{"tool": "get_deployments", "params": {"services": "checkout-api"}},'
        '{"tool": "query_logs", "params": {"service": "checkout-api", "level": "error"}},'
        '{"tool": "restart_service", "params": {}}]}'  # non-allowlisted -> dropped
    )
    plan = LLMPlanner(model).plan(CTX, answered=set(), observations=[])
    assert [q.call.tool for q in plan.questions] == ["get_deployments", "query_logs"]
    assert plan.questions[0].call.params["services"] == ["checkout-api"]  # coerced to a list


def test_plan_drops_already_answered_calls_in_batch():
    model = ScriptedModel('{"tool_calls": [{"tool": "query_logs", "params": {"service": "a"}}]}')
    key = 'llm:query_logs:{"service":"a"}'
    plan = LLMPlanner(model).plan(CTX, answered={key}, observations=[])
    assert plan.questions == []  # an already-answered call is never re-issued


def test_done_signal_yields_no_question():
    model = ScriptedModel(
        '{"done": true, "root_cause": "payment-gateway timeout", "citations": []}'
    )
    planner = LLMPlanner(model)
    plan = planner.plan(CTX, answered=set(), observations=[])
    assert plan.questions == []
    assert planner.last_decision == {
        "done": True,
        "root_cause": "payment-gateway timeout",
        "citations": [],
    }


def test_unparseable_response_fails_closed():
    plan = LLMPlanner(ScriptedModel("I cannot help with that")).plan(
        CTX, answered=set(), observations=[]
    )
    assert plan.questions == []


def test_param_coercion_scalar_to_list():
    # The live run returned services as a bare string; it must reach the tool as a list.
    model = ScriptedModel(
        '{"next_tool": "get_deployments", "params": {"services": "checkout-api"}}'
    )
    plan = LLMPlanner(model).plan(CTX, answered=set(), observations=[])
    assert plan.questions[0].call.params["services"] == ["checkout-api"]


_BASE = Hypothesis(statement="provisional", confidence=0.2, citations=[])


def test_synthesize_keeps_only_grounded_citations():
    model = ScriptedModel(
        '{"root_cause": "payment-gateway latency spike",'
        ' "citations": ["logs:payment-api:evt-004-02", "logs:ghost:hallucinated"]}'
    )
    hyp = LLMPlanner(model).synthesize(CTX, [], {"logs:payment-api:evt-004-02"}, set()).hypothesis
    assert hyp.statement == "payment-gateway latency spike"
    assert [c.ref for c in hyp.citations] == ["logs:payment-api:evt-004-02"]  # hallucination gone
    assert hyp.citations[0].source == "logs"


def test_synthesize_ungrounded_conclusion_is_unsupported():
    model = ScriptedModel('{"root_cause": "guessed cause", "citations": ["logs:ghost:x"]}')
    hyp = LLMPlanner(model).synthesize(CTX, [], {"logs:real:1"}, set()).hypothesis
    assert hyp.citations == []  # no grounded citation -> safety gate will escalate


def test_conclude_passthrough_while_investigating():
    # Not the stopping turn (final=False): the provisional hypothesis stands, no model call.
    model = ScriptedModel('{"next_tool": "get_metrics", "params": {"service": "payment-api"}}')
    planner = LLMPlanner(model)
    assert planner.conclude(_BASE, ctx=CTX, produced_refs=set(), final=False).hypothesis is _BASE


def test_conclude_synthesizes_on_final_turn():
    model = ScriptedModel(
        '{"root_cause": "payment-api timeouts", "citations": ["metrics:payment-api:p95@t"]}'
    )
    planner = LLMPlanner(model)
    conclusion = planner.conclude(
        _BASE, ctx=CTX, produced_refs={"metrics:payment-api:p95@t"}, observations=[], final=True
    )
    assert conclusion.hypothesis is not _BASE
    assert conclusion.hypothesis.statement == "payment-api timeouts"
    # No `causal` block was proposed, so nothing is admitted and the prose stands alone. This is
    # the degrade path, not a failure: a run with no structured claim must not look grounded.
    assert conclusion.causal is None


# --- structured conclusion --------------------------------------------------------------------
_CAUSAL = (
    '{"root_cause": "the model prose, which must NOT be published",'
    ' "citations": ["metrics:payment-api:p95@t"],'
    ' "causal": {"cause_type": "dependency_failure", "cause_entity": "payment-api",'
    ' "cause_event_ref": "", "onset_start": "2026-03-01T10:00:00+00:00", "onset_end": "",'
    ' "affected_entities": ["checkout-api"], "support_refs": ["metrics:payment-api:p95@t"],'
    ' "counter_refs": []},'
    ' "report_claims": [{"kind": "recommendation", "statement": "fail over the gateway",'
    ' "support_refs": ["metrics:payment-api:p95@t"]}]}'
)


def _conclude_with_causal(known=("payment-api", "checkout-api")):
    return LLMPlanner(ScriptedModel(_CAUSAL)).synthesize(
        CTX, [], {"metrics:payment-api:p95@t"}, set(known)
    )


def test_an_admitted_claim_renders_the_statement_and_discards_the_model_prose():
    """The published sentence is rendered from the typed fields, so it cannot name an entity
    the claim does not. The model's own prose is deliberately not what ships."""
    conclusion = _conclude_with_causal()
    assert conclusion.causal is not None
    assert conclusion.causal.cause_entity == "payment-api"
    assert "payment-api" in conclusion.hypothesis.statement
    assert "must NOT be published" not in conclusion.hypothesis.statement


def test_a_claim_naming_an_unresolvable_entity_fails_closed():
    """The entity is not one this run touched, so the claim is about nothing and is refused."""
    conclusion = _conclude_with_causal(known=("some-other-service",))
    assert conclusion.causal is None


def test_report_claims_are_admitted_and_carry_their_support_refs():
    claims = _conclude_with_causal().report_claims
    assert [c.kind for c in claims] == ["recommendation"]
    assert claims[0].support_refs == ["metrics:payment-api:p95@t"]
