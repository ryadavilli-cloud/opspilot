"""End-to-end: the LLM planner drives the real graph on inc-004.

Calls the live chat deployment, so it is excluded from the CI gate lane (`-m "not llm"`). It
asserts that the loop terminates and that every citation it ships is grounded in the tool-produced
trail, not that it reaches any particular quality.
"""

from __future__ import annotations

import pytest


@pytest.mark.llm
def test_llm_planner_investigates_inc004_end_to_end():
    pytest.importorskip("openai")
    from fake_operational_records import corpus_records

    from opspilot.diagnosis.planner import build_planner
    from opspilot.graph import _initial_state, build_graph, invoke_auto_approving
    from opspilot.tools.service import ToolService

    config = {
        "configurable": {
            "tool_service": ToolService(corpus_records()),
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
