"""Stage 4b gate: the single_agent (LLM) diagnosis loop beats the deterministic floor.

Replays a committed cassette (no live model, no API) so CI can score the LLM loop deterministically.
Asserts the replay reproduces the committed single_agent baseline AND clears the deterministic floor
on the headline axes. Runs on the bm25 backend, so it is ML-free (the LLM's tool choices come from
repository-backed diagnostic tools, not retrieval — replay is backend-independent).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("rank_bm25")

REPO_ROOT = Path(__file__).resolve().parents[1]
CASSETTE = REPO_ROOT / "eval" / "cassettes" / "single_agent.json"
FLOOR = json.loads((REPO_ROOT / "eval" / "baselines" / "slice_baseline.json").read_text())
SINGLE = json.loads((REPO_ROOT / "eval" / "baselines" / "single_agent_baseline.json").read_text())

_spec = importlib.util.spec_from_file_location("scenario_eval", REPO_ROOT / "eval/scenario_eval.py")
assert _spec and _spec.loader
scenario_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scenario_eval)


def _replay_scorecard(monkeypatch) -> dict:
    from opspilot import config
    from opspilot.llm.cassette import ReplayChatModel

    monkeypatch.setattr(config, "RETRIEVAL_BACKEND", "bm25")
    return scenario_eval.evaluate("single_agent", model=ReplayChatModel(str(CASSETTE)))


def test_single_agent_replay_reproduces_committed_baseline(monkeypatch):
    sc = _replay_scorecard(monkeypatch)
    for metric in ("evidence_recall", "rca_correctness", "tool_selection_accuracy",
                   "routing_accuracy", "unsupported_evidence_rate", "red_herring_avoidance"):
        assert sc[metric] == SINGLE[metric], f"{metric} drifted from the recorded cassette"


def test_single_agent_beats_the_deterministic_floor(monkeypatch):
    sc = _replay_scorecard(monkeypatch)
    # headline: the LLM agent beats the hand-tuned floor on routing (catches the inc-007
    # recurrence), evidence recall on novel investigations, and tool selection.
    assert sc["routing_accuracy"] > FLOOR["routing_accuracy"]
    assert sc["evidence_recall"] > FLOOR["evidence_recall"]
    assert sc["tool_selection_accuracy"] > FLOOR["tool_selection_accuracy"]
    # reasoning quality: it avoids the coincidental cause where the floor blames it (inc-004),
    # the honest win that rca_correctness ties on (the true root is sometimes external).
    assert sc["red_herring_avoidance"] > FLOOR["red_herring_avoidance"]
    # and regresses nothing else that matters
    assert sc["rca_correctness"] >= FLOOR["rca_correctness"]
    assert sc["category_accuracy"] >= FLOOR["category_accuracy"]
    assert sc["unsupported_evidence_rate"] <= FLOOR["unsupported_evidence_rate"]
    assert sc["tool_call_validity"] >= FLOOR["tool_call_validity"]
