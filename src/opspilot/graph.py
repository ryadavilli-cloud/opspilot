"""Investigation graph — Phase 1 walking skeleton (nodes stubbed).

Deterministic skeleton wrapping the (currently stubbed) agentic core:

    ingest -> triage_router -> [route] -> retrieve -> diagnose -> [loop?]
    -> synthesize_report -> safety_validate -> hitl_gate -> [approve?]
    -> finalize_report -> postmortem -> END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from opspilot.nodes.investigation import (
    diagnose,
    escalate,
    finalize_report,
    hitl_gate,
    ingest,
    postmortem,
    retrieve,
    safety_validate,
    synthesize_report,
    triage_router,
)
from opspilot.router import after_approval, diagnose_continue, route_by_intent
from opspilot.state import IncidentState


def build_graph():
    """Build and compile the investigation graph."""
    g = StateGraph(IncidentState)

    g.add_node("ingest", ingest)
    g.add_node("triage_router", triage_router)
    g.add_node("retrieve", retrieve)
    g.add_node("diagnose", diagnose)
    g.add_node("synthesize_report", synthesize_report)
    g.add_node("safety_validate", safety_validate)
    g.add_node("hitl_gate", hitl_gate)
    g.add_node("finalize_report", finalize_report)
    g.add_node("postmortem", postmortem)
    g.add_node("escalate", escalate)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "triage_router")
    g.add_conditional_edges(
        "triage_router",
        route_by_intent,
        {"retrieve": "retrieve", "synthesize_report": "synthesize_report"},
    )
    g.add_edge("retrieve", "diagnose")
    g.add_conditional_edges(
        "diagnose",
        diagnose_continue,
        {"diagnose": "diagnose", "synthesize_report": "synthesize_report", "escalate": "escalate"},
    )
    g.add_edge("synthesize_report", "safety_validate")
    g.add_edge("safety_validate", "hitl_gate")
    g.add_conditional_edges(
        "hitl_gate",
        after_approval,
        {"finalize_report": "finalize_report", "escalate": "escalate"},
    )
    g.add_edge("finalize_report", "postmortem")
    g.add_edge("postmortem", END)
    g.add_edge("escalate", END)

    return g.compile()


def _initial_state(alert: dict) -> dict:
    """Seed the reducer channels so append-only writes have a base."""
    return {"alert": alert, "evidence": [], "retrieved_sources": [], "messages": []}


if __name__ == "__main__":  # pragma: no cover
    app = build_graph()
    result = app.invoke(
        _initial_state(
            {"incident_id": "INC-DEMO", "severity": "SEV2", "summary": "API 5xx spike after deploy"}
        )
    )
    print("graph compiled OK; final report:")
    print(result.get("report"))
