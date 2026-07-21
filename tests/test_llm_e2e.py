"""End-to-end: the LLM planner drives the real graph on inc-004 (Stage 4b).

Live model (Ollama qwen or OpenAI, per env) — CI-excluded (`-m "not llm"`); the deterministic
scorecard is the CI gate. This asserts the loop *terminates* and that every citation it ships is
grounded in the tool-produced trail — not that it beats the floor (that is the single_agent
scorecard, recorded via a cassette).
"""

from __future__ import annotations

import pytest


@pytest.mark.llm
def test_llm_planner_investigates_inc004_end_to_end():
    pytest.importorskip("openai")
    from opspilot.diagnosis.planner import build_planner
    from opspilot.graph import _initial_state, build_graph, invoke_auto_approving
    from opspilot.tools.service import ToolService

    config = {
        "configurable": {
            "tool_service": ToolService(),
            "planner": build_planner("single_agent"),
            "thread_id": "llm-e2e-inc-004",
        }
    }
    result = invoke_auto_approving(
        build_graph(),
        _initial_state({"incident_id": "inc-004", "summary": "checkout-api 500s after deploy"}),
        config=config,
    )

    hyp = result.get("hypothesis")
    produced = set(result.get("produced_refs") or [])
    print(f"\nhypothesis: {hyp.statement if hyp else None}")
    print(f"citations:  {[c.ref for c in hyp.citations] if hyp else []}")

    assert hyp is not None  # the loop terminated with a hypothesis (grounded report or escalation)
    for citation in hyp.citations:  # every shipped citation must be a real tool-produced ref
        assert citation.ref in produced
