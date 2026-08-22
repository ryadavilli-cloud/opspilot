"""The judge's model: its own adapter, constructible through the factory, never selectable.

The adapter maps the existing judge messages onto the Messages API and its answer back into the
one `ChatResult` shape, so the verdict parser never learns which model answered. The factory can
build it, which is what makes it traced; configuration cannot select it, which is what keeps the
investigation graph off the judge's model. Both directions of that boundary are asserted here.
"""

from __future__ import annotations

import types

import pytest

from opspilot import config
from opspilot.evaluation.judge_model import build_judge_model
from opspilot.llm.base import ChatMessage
from opspilot.llm.claude import EFFORT, MAX_TOKENS, THINKING, ClaudeFoundryChatModel
from opspilot.llm.client import TracedChatModel, build_chat_model

TASK = "judge"
MESSAGES = [
    ChatMessage(role="system", content="You are an evaluator."),
    ChatMessage(role="user", content="Judge this brief."),
]


def _capturing(monkeypatch, deployment: str = "claude-opus-5"):
    """The adapter with its client replaced by a stub that records the request it was sent."""
    model = ClaudeFoundryChatModel(deployment, endpoint="https://example.invalid/anthropic/")
    captured: dict = {}

    class _Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(
                content=[
                    types.SimpleNamespace(type="thinking", thinking="deliberation"),
                    types.SimpleNamespace(type="text", text='{"category": "meets"}'),
                ],
                stop_reason="end_turn",
                usage=types.SimpleNamespace(input_tokens=11, output_tokens=7),
            )

    monkeypatch.setattr(
        model, "_ensure_client", lambda: types.SimpleNamespace(messages=_Messages())
    )
    return model, captured


# --- provider mapping ----------------------------------------------------------------------------
def test_system_and_user_messages_map_to_the_messages_api(monkeypatch):
    """The system message becomes the API's own system parameter; the turns keep their roles."""
    model, captured = _capturing(monkeypatch)

    model.complete(TASK, MESSAGES)

    assert captured["system"] == "You are an evaluator."
    assert captured["messages"] == [{"role": "user", "content": "Judge this brief."}]


def test_the_configured_deployment_is_the_one_called(monkeypatch):
    model, captured = _capturing(monkeypatch, deployment="claude-opus-5-pinned")

    result = model.complete(TASK, MESSAGES)

    assert captured["model"] == "claude-opus-5-pinned"
    assert result.deployment == "claude-opus-5-pinned"


def test_the_fixed_measurement_configuration_is_sent(monkeypatch):
    """Adaptive thinking, pinned effort, and the code-owned total-output limit, on every call.
    Fixed in code and reported on the adapter, so an edit here is visible in every report."""
    model, captured = _capturing(monkeypatch)

    model.complete(TASK, MESSAGES)

    assert captured["thinking"] == {"type": THINKING}
    assert captured["output_config"] == {"effort": EFFORT}
    assert captured["max_tokens"] == MAX_TOKENS
    assert (model.thinking, model.effort, model.max_tokens) == (THINKING, EFFORT, MAX_TOKENS)


def test_response_text_is_the_text_blocks_and_never_the_thinking(monkeypatch):
    """The existing verdict parser reads `ChatResult.text`; thinking is the model's own working
    and handing it to the parser would judge the deliberation instead of the verdict."""
    model, _ = _capturing(monkeypatch)

    result = model.complete(TASK, MESSAGES)

    assert result.text == '{"category": "meets"}'
    assert "deliberation" not in result.text


def test_usage_and_finish_reason_map_into_the_existing_accounting(monkeypatch):
    model, _ = _capturing(monkeypatch)

    result = model.complete(TASK, MESSAGES)

    assert result.usage == {"prompt_tokens": 11, "completion_tokens": 7}
    assert result.finish_reason == "end_turn"
    assert result.task == TASK


def test_a_deadline_travels_as_the_request_timeout(monkeypatch):
    model, captured = _capturing(monkeypatch)

    model.complete(TASK, MESSAGES, deadline_s=12.5)
    assert captured["timeout"] == 12.5

    captured.clear()
    model.complete(TASK, MESSAGES)
    assert "timeout" not in captured  # absent means unbounded, and none is sent


# --- the factory boundary ------------------------------------------------------------------------
def test_the_factory_builds_a_traced_claude_model_without_the_sdk():
    """Constructing must not import the optional `llm` group, and whatever the factory builds is
    traced: a client built beside the factory would be the only untraced model path."""
    model = build_chat_model("claude", deployment="claude-opus-5")

    assert isinstance(model, TracedChatModel)
    assert isinstance(model._inner, ClaudeFoundryChatModel)
    assert model.deployment == "claude-opus-5"


def test_configuration_may_not_select_the_judge_provider(monkeypatch):
    """The runtime asks the factory for no provider by name, so it can only receive what
    configuration selected, and configuration may not select the judge's model."""
    monkeypatch.setattr(config, "LLM_PROVIDER", "claude")

    with pytest.raises(ValueError, match="OPSPILOT_LLM_PROVIDER"):
        build_chat_model()


# --- the evaluation's entry point ----------------------------------------------------------------
def test_build_judge_model_refuses_missing_configuration_by_name(monkeypatch):
    monkeypatch.setattr(config, "AZURE_CLAUDE_ENDPOINT", "")
    monkeypatch.setattr(config, "AZURE_CLAUDE_DEPLOYMENT", "claude-opus-5")
    with pytest.raises(ValueError, match="AZURE_CLAUDE_ENDPOINT"):
        build_judge_model()

    monkeypatch.setattr(config, "AZURE_CLAUDE_ENDPOINT", "https://example.invalid/anthropic/")
    monkeypatch.setattr(config, "AZURE_CLAUDE_DEPLOYMENT", "")
    with pytest.raises(ValueError, match="AZURE_CLAUDE_DEPLOYMENT"):
        build_judge_model()


def test_build_judge_model_returns_the_traced_configured_deployment(monkeypatch):
    monkeypatch.setattr(config, "AZURE_CLAUDE_ENDPOINT", "https://example.invalid/anthropic/")
    monkeypatch.setattr(config, "AZURE_CLAUDE_DEPLOYMENT", "claude-opus-5-pinned")

    model = build_judge_model()

    assert isinstance(model, TracedChatModel)
    assert model.deployment == "claude-opus-5-pinned"


# --- provenance in the report --------------------------------------------------------------------
def test_the_configuration_identity_carries_the_judge_beside_the_runtime(monkeypatch):
    """Provider, deployment, effort, thinking, and prompt version, kept as their own fields: two
    reports judged under different measurement configurations are not comparable, and the runtime
    fields alone would make them look as though they were."""
    from run_evaluation import configuration_identity

    monkeypatch.setattr(config, "AZURE_CLAUDE_DEPLOYMENT", "claude-opus-5-pinned")

    identity = configuration_identity()

    assert identity["judge_provider"] == "anthropic-foundry"
    assert identity["judge_deployment"] == "claude-opus-5-pinned"
    assert identity["judge_effort"] == EFFORT
    assert identity["judge_thinking"] == THINKING
    assert identity["judge_prompt_version"] == "judge.v1"
    # The runtime identity is unchanged and stays separate.
    assert {"model_deployment", "reasoning_effort", "model_call_cap"} <= set(identity)


# --- one live smoke, excluded from the CI lane ----------------------------------------------------
@pytest.mark.llm
def test_the_live_judge_deployment_returns_one_usable_verdict():
    """One real call against the configured Claude deployment: the investigation replays
    deterministically, only the judge is live, and its answer must parse into the five verdicts."""
    from answer_key import SCENARIOS
    from evaluation import Source
    from judge import DIAGNOSIS_MATCH, QUALITIES
    from judge import judge as run_judge
    from run_evaluation import obtain

    record = obtain("inc-005", Source.for_scenario("inc-005"))
    assert record is not None
    scenario = next(s for s in SCENARIOS if s["id"] == "inc-005")

    result = run_judge(build_judge_model(), record, scenario, scenario["alert"]["summary"])

    assert result.ran
    assert set(result.verdicts) == {*QUALITIES, DIAGNOSIS_MATCH}
