"""LLMPlanner (Stage 4b) — parsing + fail-closed selection are ML-free; one live qwen check.

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
    model_id = "scripted"

    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, messages, *, temperature=0.0):
        return ChatResult(text=self._text, model_id=self.model_id)


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
    hyp = LLMPlanner(model).synthesize(CTX, [], {"logs:payment-api:evt-004-02"})
    assert hyp.statement == "payment-gateway latency spike"
    assert [c.ref for c in hyp.citations] == ["logs:payment-api:evt-004-02"]  # hallucination gone
    assert hyp.citations[0].source == "logs"


def test_synthesize_ungrounded_conclusion_is_unsupported():
    model = ScriptedModel('{"root_cause": "guessed cause", "citations": ["logs:ghost:x"]}')
    hyp = LLMPlanner(model).synthesize(CTX, [], {"logs:real:1"})
    assert hyp.citations == []  # no grounded citation -> safety gate will escalate


def test_revise_hypothesis_passthrough_while_investigating():
    # Not the stopping turn (final=False): the provisional hypothesis stands, no model call.
    model = ScriptedModel('{"next_tool": "get_metrics", "params": {"service": "payment-api"}}')
    planner = LLMPlanner(model)
    assert planner.revise_hypothesis(_BASE, ctx=CTX, produced_refs=set(), final=False) is _BASE


def test_revise_hypothesis_synthesizes_on_final_turn():
    model = ScriptedModel(
        '{"root_cause": "payment-api timeouts", "citations": ["metrics:payment-api:p95@t"]}'
    )
    planner = LLMPlanner(model)
    hyp = planner.revise_hypothesis(
        _BASE, ctx=CTX, produced_refs={"metrics:payment-api:p95@t"}, observations=[], final=True)
    assert hyp is not _BASE
    assert hyp.statement == "payment-api timeouts"


@pytest.mark.llm
def test_qwen_selects_a_read_only_tool_on_inc004():
    from opspilot.guardrails.policies import is_read_only
    from opspilot.llm.client import build_chat_model

    pytest.importorskip("openai")
    planner = LLMPlanner(build_chat_model("ollama", model="qwen3:8b"))
    plan = planner.plan(CTX, answered=set(), observations=[])
    print("\nqwen decision:", planner.last_decision)
    assert planner.last_decision is not None
    if plan.questions:  # a first step, not a premature 'done'
        assert is_read_only(plan.questions[0].call.tool)
