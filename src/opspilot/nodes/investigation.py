"""Stubbed graph nodes (Phase 1 walking skeleton).

Every node is wired so a synthetic alert flows end-to-end; the logic is canned and is
replaced phase by phase — real retrieval (Phase 3), the agentic diagnose loop (Phase 4),
HITL interrupt + report + memory write-back (Phase 5), guardrails/ops (Phase 6).
"""

from __future__ import annotations

from typing import Any

from opspilot.state import Evidence, IncidentState, Intent

_tools = None


def _tool_service():
    """Lazily-built, cached ToolService (its retriever embeds the KB on first search call)."""
    global _tools
    if _tools is None:
        from opspilot.tools.service import ToolService

        _tools = ToolService()
    return _tools


def ingest(state: IncidentState) -> dict[str, Any]:
    alert = state.get("alert", {})
    return {"incident_id": alert.get("incident_id", "INC-STUB"), "diagnose_iters": 0}


_PRIORITY_TO_SEV = {"1": "SEV1", "2": "SEV2", "3": "SEV3", "4": "SEV4"}


def triage_router(state: IncidentState) -> dict[str, Any]:
    """Deterministic triage over real tools: resolve the incident + its alert storm, derive
    severity/category/affected-services/onset, and decide known-issue vs novel from a
    past-incident search. No LLM — this is the baseline the eventual model must beat.
    """
    incident_id = state.get("incident_id", "")
    svc = _tool_service()
    record = (svc.get_incident(incident_id=incident_id).results or [None])[0]

    if record is None:  # unknown incident id — cannot classify from data; treat as novel
        alert = state.get("alert", {})
        return {
            "severity": alert.get("severity", "SEV3"),
            "category": alert.get("category", "unknown"),
            "intent": Intent.NOVEL_INVESTIGATION.value,
            "matched_incident": "",
            "affected_services": [],
            "onset": "",
            "triage": {"reason": "incident id not found; defaulting to novel investigation"},
        }

    alerts = svc.get_correlated_alerts(incident_id=incident_id).results
    affected = sorted({a.service for a in alerts})
    onset = min((a.fired_at for a in alerts), default=record.opened_at)

    # Known vs novel: does a past-incident search surface THIS incident's own postmortem?
    # (Deterministic baseline; the confidence-floored match verification is a later phase.)
    past = svc.search_past_incidents(query=record.short_description, k=3).results
    own = f"postmortem:{incident_id}"
    matched = own if any(h.doc_id == own for h in past) else ""
    intent = Intent.KNOWN_ISSUE.value if matched else Intent.NOVEL_INVESTIGATION.value

    return {
        "severity": _PRIORITY_TO_SEV.get(record.priority[:1], "SEV3"),
        "category": record.category,
        "intent": intent,
        "matched_incident": matched,
        "affected_services": affected,
        "onset": onset.isoformat(),
        "triage": {
            "route": "known-incident" if matched else "novel-investigation",
            "matched_incident": matched,
            "affected_services": affected,
            "onset": onset.isoformat(),
            "top_past_incidents": [h.doc_id for h in past],
            "reason": (f"top past-incident match is this incident's own postmortem ({matched})"
                       if matched else "no prior postmortem matches this incident"),
        },
    }


def known_issue_fast_path(state: IncidentState) -> dict[str, Any]:
    """Deterministic short-circuit for a known issue: reuse the matched incident's stored
    resolution as the hypothesis and skip the full diagnose loop."""
    match = state.get("matched_incident", "")
    inc_id = match.split(":", 1)[1] if ":" in match else state.get("incident_id", "")
    record = _tool_service().get_incident(incident_id=inc_id).results
    resolution = record[0].resolution if (record and record[0].resolution) else ""
    ref = f"past_incident:{inc_id}"
    return {
        "hypothesis": f"Known issue — recurrence of {inc_id}. Prior resolution: {resolution}",
        "confidence": 0.95,
        "evidence": [{"source": "past_incident", "ref": ref, "content": resolution}],
        "retrieved_sources": [ref],
    }


def retrieve(state: IncidentState) -> dict[str, Any]:
    """Real hybrid retrieval via ToolService; degrades to no evidence if retrieval is down."""
    query = state.get("alert", {}).get("summary", "")
    svc = _tool_service()
    evidence: list[Evidence] = []
    for hit in svc.search_runbooks(query=query, k=5).results:
        evidence.append({"source": "runbook", "ref": hit.doc_id, "content": hit.title})
    for hit in svc.search_past_incidents(query=query, k=3).results:
        inc_id = hit.doc_id.split(":", 1)[1] if ":" in hit.doc_id else hit.doc_id
        evidence.append({"source": "past_incident", "ref": f"past_incident:{inc_id}",
                         "content": hit.title})
    return {"evidence": evidence, "retrieved_sources": [e["ref"] for e in evidence]}


def diagnose(state: IncidentState) -> dict[str, Any]:
    """One deterministic diagnostic cycle (deployment-regression path). No LLM yet — the
    reasoning agent will later plug into these same contracts and transitions."""
    from opspilot.diagnosis.contracts import DiagnosisContext
    from opspilot.diagnosis.cycle import plan_investigation, run_cycle

    ctx = DiagnosisContext(
        incident_id=state.get("incident_id", ""),
        affected_services=state.get("affected_services", []),
        onset=state.get("onset", ""),
        category=state.get("category", ""),
    )
    hypothesis, observations, stop = run_cycle(_tool_service(), ctx, plan_investigation(ctx))
    evidence: list[Evidence] = [
        {"source": c.source, "ref": c.ref, "content": c.note} for c in hypothesis.citations
    ]
    return {
        "hypothesis": hypothesis.statement,
        "confidence": hypothesis.confidence,
        "evidence": evidence,
        "retrieved_sources": [c.ref for c in hypothesis.citations],
        # one outer cycle per diagnose invocation, so the loop lands exactly on MAX_DIAGNOSE_ITERS
        "diagnose_iters": state.get("diagnose_iters", 0) + 1,
        "diagnosis": {
            "hypothesis": hypothesis.model_dump(),
            "observations": [o.model_dump() for o in observations],
            "stop_reason": stop.model_dump(),
        },
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
    """Output guardrail: no unsupported hypothesis. Every report citation must be an evidence
    reference produced by a tool during this run (exempt only the info_only reply)."""
    from opspilot.guardrails.policies import hypothesis_supported

    if state.get("intent") == Intent.INFO_ONLY.value:  # ungrounded informational reply — exempt
        return {"safety": {"passed": True, "violations": [], "exempt": "info_only"}}

    citations = state.get("report", {}).get("citations", [])
    produced = {e["ref"] for e in state.get("evidence", [])}
    passed, violations = hypothesis_supported(citations, produced)
    return {"safety": {"passed": passed, "violations": violations}}


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
