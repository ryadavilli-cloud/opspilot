"""LLM client factory: no ML stack for the deterministic cases.

The factory must construct live providers without importing the optional `openai` SDK (lazy on
first call), serve the replay provider from a cassette, and fail loud on an unknown provider. A
single `@pytest.mark.llm` smoke actually hits Ollama — excluded from the CI gate lane.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opspilot.llm.base import ChatMessage, ChatResult
from opspilot.llm.cassette import RecordingChatModel
from opspilot.llm.client import OpenAICompatModel, build_chat_model


class FakeModel:
    model_id = "fake-1"

    def complete(self, messages, *, temperature=0.0):
        return ChatResult(text="ok", model_id=self.model_id)


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="unknown LLM provider"):
        build_chat_model("anthropic-native")


def test_live_providers_construct_without_importing_openai():
    # Constructing must not require the optional `openai` package — it is imported lazily on the
    # first real call, so this runs in the lean CI lane with no `llm` group installed.
    ollama = build_chat_model("ollama", model="qwen3:8b")
    assert isinstance(ollama, OpenAICompatModel)
    assert ollama.model_id == "qwen3:8b"
    assert isinstance(build_chat_model("openai", model="gpt-4o-mini"), OpenAICompatModel)


def test_replay_requires_cassette():
    with pytest.raises(ValueError, match="requires a cassette"):
        build_chat_model("replay")


def test_replay_provider_serves_recorded(tmp_path: Path):
    cassette = tmp_path / "c.json"
    RecordingChatModel(FakeModel(), cassette).complete([ChatMessage("user", "hi")])
    model = build_chat_model("replay", cassette=str(cassette))
    assert model.complete([ChatMessage("user", "hi")]).text == "ok"


def test_azure_provider_constructs_without_network():
    from opspilot.llm.client import AzureChatModel

    model = build_chat_model("azure", model="gpt-4o-deploy")  # lazy client, no network
    assert isinstance(model, AzureChatModel)
    assert model.model_id == "gpt-4o-deploy"


def test_fake_chat_model_queues_and_maps():
    from opspilot.llm.fake import FakeChatModel

    queued = FakeChatModel(["a", "b"])
    msgs = [ChatMessage("user", "x")]
    assert [queued.complete(msgs).text for _ in range(3)] == ["a", "b", "b"]  # last repeats
    mapped = FakeChatModel(lambda m: f"echo:{m[-1].content}")
    assert mapped.complete([ChatMessage("user", "hi")]).text == "echo:hi"


class _CaptureClient:
    """Stub OpenAI client that records the kwargs passed to chat.completions.create."""

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
                    usage=None,
                )

        import types

        self.chat = types.SimpleNamespace(completions=_Completions())


def test_is_reasoning_model_classification():
    from opspilot.llm.client import _is_reasoning_model

    assert _is_reasoning_model("gpt-5-mini")
    assert _is_reasoning_model("gpt-5")
    assert _is_reasoning_model("o3")
    assert not _is_reasoning_model("gpt-4o-mini")
    assert not _is_reasoning_model("qwen3:8b")


def test_reasoning_model_omits_temperature(monkeypatch):
    # gpt-5 reasoning models reject an explicit temperature; the client must not send one.
    model = OpenAICompatModel("gpt-5-mini", base_url=None, api_key="x")
    client = _CaptureClient()
    monkeypatch.setattr(model, "_ensure_client", lambda: client)
    result = model.complete([ChatMessage("user", "hi")], temperature=0.0)
    assert "temperature" not in client.captured
    assert client.captured["model"] == "gpt-5-mini"
    assert result.text == "ok"


def test_non_reasoning_model_sends_temperature(monkeypatch):
    model = OpenAICompatModel("gpt-4o-mini", base_url=None, api_key="x")
    client = _CaptureClient()
    monkeypatch.setattr(model, "_ensure_client", lambda: client)
    model.complete([ChatMessage("user", "hi")], temperature=0.0)
    assert client.captured["temperature"] == 0.0


@pytest.mark.llm
def test_ollama_live_smoke():
    pytest.importorskip("openai")
    model = build_chat_model("ollama", model="qwen3:8b")
    result = model.complete([ChatMessage("user", "Reply with the single word: pong")])
    assert result.text.strip() != ""
    assert result.model_id == "qwen3:8b"
