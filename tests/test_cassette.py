"""Cassette record/replay: the deterministic CI-gate mechanism. No ML stack.

Wiring the LLM into the loop must be gate-able without a live model: record once, replay in CI.
The manifest tests cover the other half: replay must FAIL when the recorded run and the
current code disagree on a behaviour-affecting setting, rather than serving a stale response under
a key that no longer describes the request.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opspilot import config
from opspilot.llm.base import ChatMessage, ChatResult
from opspilot.llm.cassette import (
    CassetteDriftError,
    RecordingChatModel,
    ReplayChatModel,
    request_key,
)
from opspilot.llm.manifest import behaviour_manifest, manifest_drift


class FakeModel:
    """A live-model stand-in returning a fresh answer each call (so replay-vs-live is visible)."""

    deployment = "fake-1"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, task, messages):
        self.calls += 1
        return ChatResult(
            text=f"reply-{self.calls}", task=task, deployment=self.deployment, finish_reason="stop"
        )


TASK = "rca_synthesis"
MSGS = [ChatMessage("system", "you are an SRE"), ChatMessage("user", "what changed?")]
_M = {"deployment": "m", "reasoning_effort": "medium"}
_OTHER = {"deployment": "m", "reasoning_effort": "low"}


def test_request_key_is_stable_and_sensitive():
    assert request_key(_M, TASK, MSGS) == request_key(_M, TASK, MSGS)
    assert request_key(_M, TASK, MSGS) != request_key(_M, "triage", MSGS)
    assert request_key(_M, TASK, MSGS) != request_key({**_M, "deployment": "other"}, TASK, MSGS)


def test_a_changed_provider_knob_changes_the_key():
    """The defect in one line: moving reasoning_effort from low to medium once left every key
    identical, so CI kept replaying responses recorded under the old setting."""
    assert request_key(_M, TASK, MSGS) != request_key(_OTHER, TASK, MSGS)


def test_record_then_replay_round_trip(tmp_path: Path):
    cassette = tmp_path / "c.json"
    live = FakeModel()
    recorded = RecordingChatModel(live, cassette).complete(TASK, MSGS)
    assert recorded.text == "reply-1"

    replay = ReplayChatModel(cassette)
    assert replay.deployment == "fake-1"
    played = replay.complete(TASK, MSGS)
    assert played.text == "reply-1"  # served from disk...
    assert played.finish_reason == "stop"
    assert live.calls == 1  # ...the live model was not re-invoked


def test_replay_unknown_request_fails_loud(tmp_path: Path):
    cassette = tmp_path / "c.json"
    RecordingChatModel(FakeModel(), cassette).complete(TASK, MSGS)
    replay = ReplayChatModel(cassette)
    with pytest.raises(KeyError, match="re-record"):
        replay.complete(TASK, [ChatMessage("user", "an unrecorded question")])


# --- replay manifest --------------------------------------------------------------------------
def test_the_recorded_cassette_carries_its_manifest(tmp_path: Path):
    cassette = tmp_path / "c.json"
    RecordingChatModel(FakeModel(), cassette).complete(TASK, MSGS)
    saved = json.loads(cassette.read_text(encoding="utf-8"))
    assert saved["manifest"]["deployment"] == "fake-1"
    assert saved["manifest"]["reasoning_effort"] == config.REASONING_EFFORT
    assert saved["manifest"]["prompt_versions"]  # the append-only registry is pinned


def test_a_drifted_setting_fails_the_load_and_names_the_field(tmp_path: Path, monkeypatch):
    """The whole point: a stale cassette must say WHICH input moved, at load, not miss per
    request or (worse) hit and certify a response the current inputs cannot produce."""
    cassette = tmp_path / "c.json"
    monkeypatch.setattr(config, "REASONING_EFFORT", "low")
    RecordingChatModel(FakeModel(), cassette).complete(TASK, MSGS)

    monkeypatch.setattr(config, "REASONING_EFFORT", "medium")
    with pytest.raises(CassetteDriftError, match="reasoning_effort"):
        ReplayChatModel(cassette)


def test_a_cassette_without_a_manifest_is_rejected(tmp_path: Path):
    """Pre-manifest cassettes cannot be validated, so they are stale by construction."""
    cassette = tmp_path / "old.json"
    cassette.write_text(json.dumps({"deployment": "fake-1", "interactions": []}), encoding="utf-8")
    with pytest.raises(CassetteDriftError, match="re-record"):
        ReplayChatModel(cassette)


def test_manifest_drift_lists_every_changed_field_and_is_empty_when_equal():
    current = behaviour_manifest(deployment="fake-1")
    assert manifest_drift(current, current) == []
    drift = manifest_drift({**current, "reasoning_effort": "low"}, current)
    assert len(drift) == 1 and "reasoning_effort" in drift[0]


def test_the_provider_name_is_not_part_of_the_manifest():
    """Replay runs under the `replay` provider while the recording ran against Azure. Comparing it
    would fail every single load and train everyone to ignore the check, so the knobs that shape
    output are compared instead of the provider identity."""
    assert "provider" not in behaviour_manifest(deployment="fake-1")


def test_no_sampling_seed_is_pinned():
    """The seam sends no seed, and a manifest field pinned to a constant nobody sends is coverage
    theatre that also invalidates every cassette whenever it is touched."""
    assert "sampling_seed" not in behaviour_manifest(deployment="fake-1")
