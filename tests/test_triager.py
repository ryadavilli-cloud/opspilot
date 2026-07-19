"""Triager seam (Stage 4c) — no ML stack.

The deterministic triager reproduces the exact self-match baseline; the LLM triager classifies
intent + a recurrence candidate and fails closed — a hallucinated, over-confident, or unparseable
response falls back to `novel_investigation` rather than a fabricated known-issue shortcut.
"""

from __future__ import annotations

import pytest

from opspilot.llm.base import ChatResult
from opspilot.state import Intent
from opspilot.triage import (
    DeterministicTriager,
    LLMTriager,
    PastCandidate,
    TriageContext,
    build_triager,
)


class ScriptedModel:
    model_id = "scripted"

    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, messages, *, temperature=0.0):
        return ChatResult(text=self._text, model_id=self.model_id)


def _ctx(incident_id: str = "inc-007", candidates=("postmortem:inc-003",)) -> TriageContext:
    return TriageContext(
        incident_id=incident_id,
        short_description="notification-worker crash loop",
        past_candidates=[PastCandidate(doc_id=c, title="prior incident") for c in candidates],
    )


def test_deterministic_matches_only_its_own_postmortem():
    own = DeterministicTriager().classify(_ctx("inc-003", ("postmortem:inc-003",)))
    assert own.intent == Intent.KNOWN_ISSUE.value
    assert own.matched_incident == "postmortem:inc-003"
    # inc-007 recurs inc-003 but its OWN postmortem is absent -> novel (the baseline routing miss)
    recur = DeterministicTriager().classify(_ctx("inc-007", ("postmortem:inc-003",)))
    assert recur.intent == Intent.NOVEL_INVESTIGATION.value
    assert recur.matched_incident == ""


def test_llm_detects_a_recurrence_against_a_surfaced_candidate():
    model = ScriptedModel('{"intent": "known_issue", "matched_incident": "postmortem:inc-003"}')
    decision = LLMTriager(model).classify(_ctx())
    assert decision.intent == Intent.KNOWN_ISSUE.value
    assert decision.matched_incident == "postmortem:inc-003"


def test_llm_hallucinated_match_fails_closed_to_novel():
    model = ScriptedModel('{"intent": "known_issue", "matched_incident": "postmortem:inc-999"}')
    decision = LLMTriager(model).classify(_ctx())  # inc-999 was never a candidate
    assert decision.intent == Intent.NOVEL_INVESTIGATION.value
    assert decision.matched_incident == ""


def test_llm_invalid_or_unparseable_fails_closed():
    bad_intent = LLMTriager(ScriptedModel('{"intent": "banana"}')).classify(_ctx())
    assert bad_intent.intent == Intent.NOVEL_INVESTIGATION.value
    no_json = LLMTriager(ScriptedModel("I can't help")).classify(_ctx())
    assert no_json.intent == Intent.NOVEL_INVESTIGATION.value


def test_llm_novel_carries_no_match():
    model = ScriptedModel(
        '{"intent": "novel_investigation", "matched_incident": "postmortem:inc-003"}'
    )
    decision = LLMTriager(model).classify(_ctx())
    assert decision.intent == Intent.NOVEL_INVESTIGATION.value
    assert decision.matched_incident == ""


def test_build_triager_known_and_unknown():
    assert isinstance(build_triager("deterministic"), DeterministicTriager)
    assert build_triager("single_agent").name == "single_agent"  # lazy client, no network
    with pytest.raises(ValueError, match="unknown triage implementation"):
        build_triager("nope")
