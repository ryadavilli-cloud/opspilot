"""LLM client factory (Stage 4a) — no ML stack for the deterministic cases.

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


@pytest.mark.llm
def test_ollama_live_smoke():
    pytest.importorskip("openai")
    model = build_chat_model("ollama", model="qwen3:8b")
    result = model.complete([ChatMessage("user", "Reply with the single word: pong")])
    assert result.text.strip() != ""
    assert result.model_id == "qwen3:8b"
