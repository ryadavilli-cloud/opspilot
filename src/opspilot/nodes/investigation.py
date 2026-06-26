"""Stubbed graph nodes (Phase 1 walking skeleton).

Every node is wired so a synthetic alert flows end-to-end; the logic is canned and is
replaced phase by phase — real retrieval (Phase 3), the agentic diagnose loop (Phase 4),
HITL interrupt + report + memory write-back (Phase 5), guardrails/ops (Phase 6).
"""

from __future__ import annotations

from typing import Any

from opspilot.state import Evidence, IncidentState, Intent
from opspilot.tools.stubs import search_past_incidents, search_runbooks


def ingest(state: IncidentState) -> dict[str, Any]:
    alert = state.get("alert", {})
    return {"incident_id": alert.get("incident_id", "INC-STUB"), "diagnose_iters": 0}


def triage_router(state: IncidentState) -> dict[str, Any]:
    alert = state.get("alert", {})
    return {
        "severity": alert.get("severity", "SEV3"),
        "category": alert.get("category", "unknown"),
        "intent": Intent.NOVEL_INVESTIGATION.value,
        "matched_incident": "",
    }


def retrieve(state: IncidentState) -> dict[str, Any]:
    query = state.get("alert", {}).get("summary", "")
    evidence: list[Evidence] = [*search_runbooks(query), *search_past_incidents(query)]
    return {"evidence": evidence, "retrieved_sources": [e["ref"] for e in evidence]}


def diagnose(state: IncidentState) -> dict[str, Any]:
    # Phase 1 stub: one pass, high confidence so the loop exits immediately.
    # The real ReAct loop + MAX_DIAGNOSE_ITERS breaker land in Phase 4.
    return {
        "hypothesis": "(stub) root cause: a recent deploy introduced a regression.",
        "confidence": 0.9,
        "diagnose_iters": state.get("diagnose_iters", 0) + 1,
    }


def synthesize_report(state: IncidentState) -> dict[str, Any]:
    report = {
        "incident_id": state.get("incident_id", "INC-STUB"),
        "severity": state.get("severity", "SEV3"),
        "category": state.get("category", "unknown"),
        "hypothesis": state.get("hypothesis", ""),
        "confidence": state.get("confidence", 0.0),
        "evidence": state.get("evidence", []),
        "recommended_next_step": "(stub) roll back the most recent deploy and re-observe.",
        "citations": state.get("retrieved_sources", []),
    }
    return {"report": report}


def safety_validate(state: IncidentState) -> dict[str, Any]:
    # Phase 6 adds real guardrails (citation requirement, unsupported-claim, schema).
    return {}


def hitl_gate(state: IncidentState) -> dict[str, Any]:
    # Phase 5 replaces this with a checkpoint-backed interrupt(). For the walking
    # skeleton we auto-approve so the flow completes without a human in the loop.
    return {"approval": {"decision": "approve", "approver": "stub", "edits": None}}


def finalize_report(state: IncidentState) -> dict[str, Any]:
    return {"report": state.get("report", {})}


def postmortem(state: IncidentState) -> dict[str, Any]:
    # Phase 5 writes this back to the cross-thread incident Store (Cosmos).
    return {
        "postmortem": {
            "incident_id": state.get("incident_id", "INC-STUB"),
            "resolution": state.get("hypothesis", ""),
        }
    }


def escalate(state: IncidentState) -> dict[str, Any]:
    return {"degraded": True, "error": state.get("error", "escalated to human")}
