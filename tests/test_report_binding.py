"""5a — the published report is a typed, frozen IncidentReport bound by a content hash.

Proves the report is immutable, its hash is deterministic, and the bytes an approval is bound to are
exactly the bytes finalize publishes (the property the real HITL interrupt in 5c will enforce). All
ML-free: the report nodes are exercised on a hand-built state, no retrieval or model needed.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from pydantic import ValidationError

from opspilot.contracts import IncidentReport
from opspilot.diagnosis.contracts import EvidenceCitation, Hypothesis
from opspilot.nodes.investigation import (
    apply_edit,
    escalate,
    finalize_report,
    hitl_gate,
    synthesize_report,
)
from opspilot.router import after_approval
from opspilot.state import EvidenceItem, InvestigationState


def _approval_graph():
    """The smallest graph that exercises the real hitl_gate interrupt: hitl_gate -> (approve ->
    finalize_report) | (else -> escalate), on an in-process MemorySaver. `hitl_gate` calls a real
    LangGraph interrupt(), so it can no longer be exercised as a bare function call — this mirrors
    tests/test_checkpointer.py's `_tiny_graph` pattern."""
    g = StateGraph(InvestigationState)
    g.add_node("hitl_gate", hitl_gate)
    g.add_node("finalize_report", finalize_report)
    g.add_node("escalate", escalate)
    g.add_edge(START, "hitl_gate")
    g.add_conditional_edges(
        "hitl_gate", after_approval,
        {"finalize_report": "finalize_report", "apply_edit": "escalate", "escalate": "escalate"},
    )
    g.add_edge("finalize_report", END)
    g.add_edge("escalate", END)
    return g.compile(checkpointer=MemorySaver())


def _state_with_evidence() -> InvestigationState:
    hyp = Hypothesis(
        statement="deployment regression in checkout-api",
        confidence=0.8,
        citations=[EvidenceCitation(source="deploys", ref="deploys:checkout-api:d1", note="")],
    )
    ev = EvidenceItem.make("deploys", "deploys:checkout-api:d1", "deploy d1 at 10:02")
    return InvestigationState(
        incident_id="inc-006", severity="SEV2", category="deployment",
        hypothesis=hyp, evidence_by_id={ev.content_hash: ev},
    )


def test_synthesize_emits_a_typed_report_and_its_hash():
    out = synthesize_report(_state_with_evidence())
    report = out["report"]
    assert isinstance(report, IncidentReport)
    assert report.incident_id == "inc-006" and report.citations
    assert out["report_hash"] == report.content_hash()


def test_content_hash_is_deterministic_across_identical_reports():
    r1 = synthesize_report(_state_with_evidence())["report"]
    r2 = synthesize_report(_state_with_evidence())["report"]
    assert r1 == r2
    assert r1.content_hash() == r2.content_hash()


def test_report_is_frozen():
    report = synthesize_report(_state_with_evidence())["report"]
    with pytest.raises(ValidationError):
        report.hypothesis = "tampered"  # type: ignore[misc]


def test_editing_changes_the_hash():
    state = _state_with_evidence().model_copy(update=synthesize_report(_state_with_evidence()))
    original = state.report_hash
    edit = {"approval": {"decision": "edit", "edits": {"recommended_next_step": "roll back d1"}}}
    state = state.model_copy(update=edit)
    edited = apply_edit(state)
    assert edited["report"].recommended_next_step == "roll back d1"
    assert edited["report_hash"] != original  # a different report, a new hash
    assert edited["report_hash"] == edited["report"].content_hash()


def test_approved_bytes_equal_published_bytes():
    """synthesize -> real interrupt pause -> approve (binds the hash) -> finalize publishes the
    byte-exact object. Exercises the actual hitl_gate interrupt()/Command(resume=...) round trip,
    not a bare function call."""
    state = _state_with_evidence()
    state = state.model_copy(update=synthesize_report(state))
    report_hash = state.report_hash

    graph = _approval_graph()
    config = {"configurable": {"thread_id": "report-binding-test"}}
    paused = graph.invoke(state.model_dump(), config=config)
    pending = paused["__interrupt__"]
    assert pending[0].value["report_hash"] == report_hash  # the interrupt carries the exact hash

    result = graph.invoke(
        Command(resume={"decision": "approve", "approver": "human", "edits": None,
                        "submitted_report_hash": report_hash}),
        config=config,
    )
    approved_hash = result["approval"]["approved_report_hash"]
    assert approved_hash == report_hash  # approval bound to what it saw

    assert result["report"].content_hash() == approved_hash  # published == approved, byte-exact
    assert result["report_hash"] == approved_hash


def test_finalize_report_rejects_an_unbound_approval():
    """Defense-in-depth: `after_approval`'s routing should make this unreachable, but
    finalize_report must never publish a report its approval doesn't actually match — it fails
    loud rather than trusting an invariant it cannot itself verify came from the router."""
    state = _state_with_evidence()
    state = state.model_copy(update=synthesize_report(state))
    state = state.model_copy(update={"approval": {"decision": "approve",
                                                    "approved_report_hash": "not-the-real-hash"}})
    with pytest.raises(RuntimeError, match="finalize_report invariant violated"):
        finalize_report(state)


def test_stale_approval_is_rejected_and_escalates():
    """A decision submitted against a hash that no longer matches the current report is rejected,
    not silently applied — and routes to escalate with a specific, machine-readable reason."""
    state = _state_with_evidence()
    state = state.model_copy(update=synthesize_report(state))

    graph = _approval_graph()
    config = {"configurable": {"thread_id": "stale-approval-test"}}
    graph.invoke(state.model_dump(), config=config)

    result = graph.invoke(
        Command(resume={"decision": "approve", "approver": "human", "edits": None,
                        "submitted_report_hash": "not-the-real-hash"}),
        config=config,
    )
    assert result["approval"]["decision"] == "stale_rejected"
    assert result["approval"]["approved_report_hash"] is None
    assert result["error"].startswith("stale_approval:")


def test_reject_escalates_with_the_rejecting_approver_named():
    state = _state_with_evidence()
    state = state.model_copy(update=synthesize_report(state))
    report_hash = state.report_hash

    graph = _approval_graph()
    config = {"configurable": {"thread_id": "reject-test"}}
    graph.invoke(state.model_dump(), config=config)

    result = graph.invoke(
        Command(resume={"decision": "reject", "approver": "reviewer-1", "edits": None,
                        "submitted_report_hash": report_hash}),
        config=config,
    )
    assert result["error"] == "human_rejected by reviewer-1"
