"""Cassette record/replay (Stage 4a) — the deterministic CI-gate mechanism. No ML stack.

Wiring the LLM into the loop must be gate-able without a live model: record once, replay in CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opspilot.llm.base import ChatMessage, ChatResult
from opspilot.llm.cassette import RecordingChatModel, ReplayChatModel, request_key


class FakeModel:
    """A live-model stand-in returning a fresh answer each call (so replay-vs-live is visible)."""

    model_id = "fake-1"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages, *, temperature=0.0):
        self.calls += 1
        return ChatResult(text=f"reply-{self.calls}", model_id=self.model_id, finish_reason="stop")


MSGS = [ChatMessage("system", "you are an SRE"), ChatMessage("user", "what changed?")]


def test_request_key_is_stable_and_sensitive():
    assert request_key("m", MSGS, 0.0) == request_key("m", MSGS, 0.0)
    assert request_key("m", MSGS, 0.0) != request_key("m", MSGS, 0.5)
    assert request_key("m", MSGS, 0.0) != request_key("other", MSGS, 0.0)


def test_record_then_replay_round_trip(tmp_path: Path):
    cassette = tmp_path / "c.json"
    live = FakeModel()
    recorded = RecordingChatModel(live, cassette).complete(MSGS)
    assert recorded.text == "reply-1"

    replay = ReplayChatModel(cassette)
    assert replay.model_id == "fake-1"
    played = replay.complete(MSGS)
    assert played.text == "reply-1"          # served from disk...
    assert played.finish_reason == "stop"
    assert live.calls == 1                    # ...the live model was not re-invoked


def test_replay_unknown_request_fails_loud(tmp_path: Path):
    cassette = tmp_path / "c.json"
    RecordingChatModel(FakeModel(), cassette).complete(MSGS)
    replay = ReplayChatModel(cassette)
    with pytest.raises(KeyError, match="re-record"):
        replay.complete([ChatMessage("user", "an unrecorded question")])
