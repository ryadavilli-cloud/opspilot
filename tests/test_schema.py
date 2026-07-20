"""Typed model-response schemas (Row 4) — malformed output raises ValidationError so the planner /
triager fall back closed. These pin the strictness the imperative parsing lacked."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opspilot.llm.schema import PlannerResponse, SynthesisResponse, TriageResponse


def test_planner_response_accepts_batch_single_and_done():
    batch = PlannerResponse.model_validate(
        {"tool_calls": [{"tool": "get_metrics", "params": {"service": "a"}}]}
    )
    assert batch.tool_calls[0].tool == "get_metrics"
    single = PlannerResponse.model_validate({"next_tool": "query_logs", "params": {"service": "a"}})
    assert single.next_tool == "query_logs"
    done = PlannerResponse.model_validate({"done": True, "citations": ["logs:a:b"]})
    assert done.done and done.citations == ["logs:a:b"]


def test_planner_response_rejects_bad_types():
    with pytest.raises(ValidationError):
        PlannerResponse.model_validate({"citations": "not-a-list"})
    with pytest.raises(ValidationError):
        PlannerResponse.model_validate({"tool_calls": [{"params": "not-a-dict"}]})


def test_triage_response_rejects_unknown_or_missing_intent():
    assert TriageResponse.model_validate({"intent": "known_issue"}).intent == "known_issue"
    with pytest.raises(ValidationError):
        TriageResponse.model_validate({"intent": "banana"})
    with pytest.raises(ValidationError):
        TriageResponse.model_validate({})  # intent is required


def test_synthesis_response():
    r = SynthesisResponse.model_validate({"root_cause": "x", "citations": ["metrics:a:b@t"]})
    assert r.root_cause == "x" and r.citations == ["metrics:a:b@t"]
