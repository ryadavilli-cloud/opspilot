"""Investigation graph — Phase 1 walking skeleton (nodes stubbed).

Deterministic skeleton wrapping the (currently stubbed) agentic core:

    ingest -> triage_router -> [route] -> retrieve -> diagnose -> [loop?]
    -> synthesize_report -> safety_validate -> hitl_gate -> [approve?]
    -> finalize_report -> postmortem -> END
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph

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

# Every custom Pydantic type that can end up inside a checkpointed InvestigationState (via
# hitl_gate's real interrupt(), 5c). LangGraph's default JsonPlusSerializer pickle-falls-back for
# unregistered types today (with a "will be blocked in a future version" warning) and blocks them
# outright under LANGGRAPH_STRICT_MSGPACK=true — explicitly allowlisting these keeps checkpointing
# working under both. `opspilot.state.EvidenceItem` and `opspilot.contracts.EvidenceItem` are two
# distinct classes (internal vs. published-report shape) and both need their own entry.
_CHECKPOINT_MSGPACK_ALLOWLIST: tuple[tuple[str, str], ...] = (
    ("opspilot.state", "EvidenceItem"),
    ("opspilot.state", "DiagnosisTrace"),
    ("opspilot.contracts", "EvidenceItem"),
    ("opspilot.contracts", "IncidentReport"),
    ("opspilot.diagnosis.contracts", "Hypothesis"),
    ("opspilot.diagnosis.contracts", "EvidenceCitation"),
    ("opspilot.diagnosis.contracts", "ToolObservation"),
    ("opspilot.diagnosis.contracts", "StopReason"),
    ("opspilot.diagnosis.contracts", "SufficiencyState"),
)


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Build and compile the investigation graph.

    `checkpointer` (from the composition root's `build_checkpointer()`) makes the graph durable: it
    persists a checkpoint per `thread_id`, so an interrupted run can resume from the exact step
    after a process restart. `hitl_gate`'s real `interrupt()` (5c) requires a checkpointer to
    pause and later resume at all — `Command(resume=...)` hard-fails without one — so `None` (the
    `none` checkpointer backend, still the config default) is upgraded here to an in-process
    `MemorySaver()` rather than left as no checkpointer at all. This is a deliberate, non-durable
    fallback: a caller that needs the pause to survive a process restart must pass a durable
    backend (`sqlite`/`cosmos`) explicitly; one that doesn't (tests, the eval harness, the sync
    `/investigate` endpoint via `invoke_auto_approving`) still gets a graph that can pause/resume
    within the same process. The resolved checkpointer is also given the msgpack allowlist for
    this codebase's Pydantic state types (`_CHECKPOINT_MSGPACK_ALLOWLIST`) — required so a
    checkpoint holding a real `report`/`hypothesis` deserializes cleanly under a strict
    (`LANGGRAPH_STRICT_MSGPACK=true`) LangGraph deployment, not just the default permissive mode.
    """
    checkpointer = checkpointer or MemorySaver()
    checkpointer = checkpointer.with_allowlist(_CHECKPOINT_MSGPACK_ALLOWLIST)
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

    return g.compile(checkpointer=checkpointer)


def _initial_state(alert: dict, *, investigation_id: str | None = None) -> dict:
    """Initial graph input — just the alert; the typed state supplies every other default.

    `investigation_id`, when supplied, is threaded into state so `ingest()` honors it instead of
    minting its own — this is what lets the async API's job id, the checkpointer's `thread_id`,
    and `state.investigation_id` all be the same string (see `api.py`).
    """
    state: dict[str, Any] = {"alert": alert}
    if investigation_id is not None:
        state["investigation_id"] = investigation_id
    return state


def invoke_auto_approving(
    graph: CompiledStateGraph,
    initial_state: dict,
    config: RunnableConfig,
    *,
    approver: str = "system:auto-approve",
) -> dict:
    """Run `graph` to a genuinely terminal state, transparently auto-approving any `hitl_gate`
    interrupt along the way.

    For callers that want pre-HITL, run-to-completion semantics — tests, the eval harness, and the
    synchronous `/investigate` compatibility endpoint. The async job API (`POST /investigations`)
    must NOT use this: it exposes the pause to a real reviewer instead of auto-resolving it.
    """
    from langgraph.types import Command

    state = graph.invoke(initial_state, config=config)
    for _ in range(3):  # a plain approve never loops back through hitl_gate; bounded defensively
        pending = state.get("__interrupt__")
        if not pending:
            return state
        resume = {
            "decision": "approve",
            "approver": approver,
            "edits": None,
            "submitted_report_hash": pending[0].value.get("report_hash"),
        }
        state = graph.invoke(Command(resume=resume), config=config)
    raise RuntimeError("graph did not reach a terminal state after auto-approving the interrupt")


if __name__ == "__main__":  # pragma: no cover
    from opspilot.tools.service import ToolService

    app = build_graph()
    result = invoke_auto_approving(
        app,
        _initial_state(
            {"incident_id": "INC-DEMO", "severity": "SEV2", "summary": "API 5xx spike after deploy"}
        ),
        config={"configurable": {"tool_service": ToolService(), "thread_id": "demo"}},
    )
    print("graph compiled OK; final report:")
    print(result.get("report"))
