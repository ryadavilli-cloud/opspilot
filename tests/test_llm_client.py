"""The model seam: one live adapter, replay, and the fake.

The factory must construct the live adapter without importing the optional Azure SDK, which is what
lets the lean lane exercise it at all; serve replay from a cassette; and fail loud on anything else
rather than answering with a different model than the caller asked for. One `llm`-marked case
actually calls the deployment and is excluded from the CI gate lane.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from opspilot.llm.base import ChatMessage, ChatResult
from opspilot.llm.cassette import RecordingChatModel
from opspilot.llm.client import AzureChatModel, build_chat_model

TASK = "rca_synthesis"


class FakeModel:
    deployment = "fake-1"

    def complete(self, task, messages, deadline_s=None):
        return ChatResult(text="ok", task=task, deployment=self.deployment)


def test_unknown_provider_raises():
    """Including the ones that used to exist: a stale configuration must fail rather than resolve
    to the one remaining adapter behind the caller's back."""
    for provider in ("anthropic-native", "ollama", "openai"):
        with pytest.raises(ValueError, match="unknown LLM provider"):
            build_chat_model(provider)


def test_the_live_adapter_constructs_without_importing_a_provider_sdk():
    # Constructing must not require the optional `llm` group: the SDK is imported lazily on the
    # first real call, so this runs in the lean CI lane with nothing installed.
    model = build_chat_model("azure", deployment="gpt-5-mini")
    assert isinstance(model, AzureChatModel)
    assert model.deployment == "gpt-5-mini"


def test_replay_requires_cassette():
    with pytest.raises(ValueError, match="requires a cassette"):
        build_chat_model("replay")


def test_replay_provider_serves_recorded(tmp_path: Path):
    cassette = tmp_path / "c.json"
    RecordingChatModel(FakeModel(), cassette).complete(TASK, [ChatMessage("user", "hi")])
    model = build_chat_model("replay", cassette=str(cassette))
    assert model.complete(TASK, [ChatMessage("user", "hi")]).text == "ok"


def test_fake_chat_model_queues_and_maps():
    from opspilot.llm.fake import FakeChatModel

    queued = FakeChatModel(["a", "b"])
    msgs = [ChatMessage("user", "x")]
    assert [queued.complete(TASK, msgs).text for _ in range(3)] == ["a", "b", "b"]  # last repeats
    mapped = FakeChatModel(lambda m: f"echo:{m[-1].content}")
    assert mapped.complete(TASK, [ChatMessage("user", "hi")]).text == "echo:hi"


class _CaptureClient:
    """Stub Azure client that records the kwargs passed to chat.completions.create."""

    def __init__(self) -> None:
        self.captured: dict = {}
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.captured = kwargs
                import types

                return types.SimpleNamespace(
                    choices=[
                        types.SimpleNamespace(
                            message=types.SimpleNamespace(content="ok"),
                            finish_reason="stop",
                        )
                    ],
                    usage=types.SimpleNamespace(prompt_tokens=11, completion_tokens=7),
                )

        import types

        self.chat = types.SimpleNamespace(completions=_Completions())


def _captured(deployment: str, monkeypatch) -> tuple[AzureChatModel, _CaptureClient]:
    model = AzureChatModel(deployment, endpoint="https://example.invalid", api_version="v")
    client = _CaptureClient()
    monkeypatch.setattr(model, "_ensure_client", lambda: client)
    return model, client


def test_is_reasoning_model_classification():
    from opspilot.llm.client import _is_reasoning_model

    assert _is_reasoning_model("gpt-5-mini")
    assert _is_reasoning_model("gpt-5")
    assert _is_reasoning_model("o3")
    assert not _is_reasoning_model("gpt-4o-mini")


def test_a_reasoning_deployment_is_called_with_its_effort_and_no_temperature(monkeypatch):
    """Reasoning deployments reject an explicit temperature, and left unbounded their hidden
    tokens make the call slow and expensive, so the effort is what the request carries."""
    model, client = _captured("gpt-5-mini", monkeypatch)

    result = model.complete(TASK, [ChatMessage("user", "hi")])

    assert "temperature" not in client.captured
    assert client.captured["reasoning_effort"]
    assert client.captured["model"] == "gpt-5-mini"
    assert result.text == "ok"


def test_a_non_reasoning_deployment_carries_no_sampling_controls(monkeypatch):
    """Neither temperature nor a seed: the seam takes a task label and messages, and nothing else
    reaches the provider."""
    model, client = _captured("gpt-4o-mini", monkeypatch)

    model.complete(TASK, [ChatMessage("user", "hi")])

    assert set(client.captured) == {"model", "messages"}


def test_every_call_accounts_for_its_task_deployment_latency_and_usage(monkeypatch):
    """A run that cannot say what its model calls cost cannot be audited, and reconstructing that
    afterwards from a provider bill is not an audit."""
    model, _ = _captured("gpt-5-mini", monkeypatch)

    result = model.complete(TASK, [ChatMessage("user", "hi")])

    assert result.task == TASK
    assert result.deployment == "gpt-5-mini"
    assert result.latency_ms > 0
    assert result.usage == {"prompt_tokens": 11, "completion_tokens": 7}


def test_the_fake_and_the_cassette_account_for_a_call_the_same_way(tmp_path: Path):
    """The stand-ins answer the same contract, so a test never reads a field the live path fills
    and they leave empty."""
    from opspilot.llm.fake import FakeChatModel

    fake = FakeChatModel(["x"]).complete(TASK, [ChatMessage("user", "hi")])
    assert (fake.task, fake.deployment) == (TASK, "fake")

    cassette = tmp_path / "c.json"
    RecordingChatModel(FakeModel(), cassette).complete(TASK, [ChatMessage("user", "hi")])
    replayed = build_chat_model("replay", cassette=str(cassette)).complete(
        TASK, [ChatMessage("user", "hi")]
    )
    assert (replayed.task, replayed.deployment) == (TASK, "fake-1")


@pytest.mark.llm
def test_the_deployment_answers_over_the_shipping_adapter():
    """Keyless, as the environment's identity. Proves the boundary the application uses, which is
    the only reason a live case earns its place here."""
    pytest.importorskip("openai")
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
        pytest.skip("AZURE_OPENAI_ENDPOINT is not set")

    model = build_chat_model("azure", deployment="gpt-5-mini")
    result = model.complete(TASK, [ChatMessage("user", "Reply with the single word: pong")])

    assert result.text.strip() != ""
    assert result.deployment == "gpt-5-mini"
    assert result.usage["prompt_tokens"] > 0
