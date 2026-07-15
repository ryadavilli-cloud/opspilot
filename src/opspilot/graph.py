"""Investigation graph — Phase 1 walking skeleton (nodes stubbed).

Deterministic skeleton wrapping the (currently stubbed) agentic core:

    ingest -> triage_router -> [route] -> retrieve -> diagnose -> [loop?]
    -> synthesize_report -> safety_validate -> hitl_gate -> [approve?]
    -> finalize_report -> postmortem -> END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from opspilot.nodes.investigation import (
    apply_edit,
    diagnose,
    escalate,
    finalize_report,
    hitl_gate,
    ingest,
    known_issue_fast_path,
    postmortem,
    retrieve,
    safety_validate,
    synthesize_report,
    triage_router,
)
from opspilot.router import (
    after_approval,
    after_safety_validate,
    diagnose_continue,
    route_by_intent,
)
from opspilot.state import InvestigationState


def build_graph():
    """Build and compile the investigation graph."""
    g = StateGraph(InvestigationState)

    g.add_node("ingest", ingest)
    g.add_node("triage_router", triage_router)
    g.add_node("known_issue_fast_path", known_issue_fast_path)
    g.add_node("retrieve", retrieve)
    g.add_node("diagnose", diagnose)
    g.add_node("synthesize_report", synthesize_report)
    g.add_node("safety_validate", safety_validate)
    g.add_node("hitl_gate", hitl_gate)
    g.add_node("apply_edit", apply_edit)
    g.add_node("finalize_report", finalize_report)
    g.add_node("postmortem", postmortem)
    g.add_node("escalate", escalate)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "triage_router")
    g.add_conditional_edges(
        "triage_router",
        route_by_intent,
        {
            "retrieve": "retrieve",
            "known_issue_fast_path": "known_issue_fast_path",
            "synthesize_report": "synthesize_report",
        },
    )
    g.add_edge("known_issue_fast_path", "synthesize_report")
    g.add_edge("retrieve", "diagnose")
    g.add_conditional_edges(
        "diagnose",
        diagnose_continue,
        {"diagnose": "diagnose", "synthesize_report": "synthesize_report", "escalate": "escalate"},
    )
    g.add_edge("synthesize_report", "safety_validate")
    g.add_conditional_edges(
        "safety_validate",
        after_safety_validate,
        {"hitl_gate": "hitl_gate", "escalate": "escalate"},
    )
    g.add_conditional_edges(
        "hitl_gate",
        after_approval,
        {"finalize_report": "finalize_report", "apply_edit": "apply_edit", "escalate": "escalate"},
    )
    # An edit re-enters the guardrail, then returns to the gate for re-approval.
    g.add_edge("apply_edit", "safety_validate")
    g.add_edge("finalize_report", "postmortem")
    g.add_edge("postmortem", END)
    g.add_edge("escalate", END)

    return g.compile()


def _initial_state(alert: dict) -> dict:
    """Initial graph input — just the alert; the typed state supplies every other default."""
    return {"alert": alert}


if __name__ == "__main__":  # pragma: no cover
    from opspilot.tools.service import ToolService

    app = build_graph()
    result = app.invoke(
        _initial_state(
            {"incident_id": "INC-DEMO", "severity": "SEV2", "summary": "API 5xx spike after deploy"}
        ),
        config={"configurable": {"tool_service": ToolService()}},
    )
    print("graph compiled OK; final report:")
    print(result.get("report"))
