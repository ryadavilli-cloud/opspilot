"""Investigation graph nodes — deterministic connected slice (no LLM yet).

A synthetic alert flows end to end over real tools; each node returns a partial update to the
typed `InvestigationState`. The `ToolService` is injected via LangGraph `config` (one instance
per investigation, built at the composition root) rather than a module global, so tests can
supply edge-case repositories and the diagnosis loop always talks to the same service.

(No `from __future__ import annotations` here: LangGraph inspects node signatures at
`add_node`, and stringized annotations make it mis-read the injected `config` parameter.)
"""

import hashlib
from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableConfig

from opspilot.config import MAX_DIAGNOSE_ITERS, WORKFLOW_VERSION
from opspilot.diagnosis.contracts import EvidenceCitation, Hypothesis
from opspilot.state import DiagnosisTrace, EvidenceItem, Intent, InvestigationState

_UNIT_SEP = "\x1f"


def _svc(config: RunnableConfig | None):
    """Resolve the injected ToolService, or construct a default (direct-call tests / CLI)."""
    if config:
        injected = (config.get("configurable") or {}).get("tool_service")
        if injected is not None:
            return injected
    from opspilot.tools.service import ToolService

    return ToolService()


def _evidence_map(items: list[EvidenceItem]) -> dict[str, EvidenceItem]:
    """Key evidence by content hash so the merge reducer dedups it."""
    return {item.content_hash: item for item in items}


def ingest(state: InvestigationState) -> dict[str, Any]:
    """Normalize the alert; mint a unique investigation_id and derive thread_id from it."""
    alert = state.alert
    incident_id = alert.get("incident_id", "INC-STUB")
    investigation_id = str(uuid4())
    idem = hashlib.sha256(
        _UNIT_SEP.join((incident_id, alert.get("summary", ""))).encode("utf-8")
    ).hexdigest()
    return {
        "incident_id": incident_id,
        "investigation_id": investigation_id,
        "thread_id": f"thread-{investigation_id}",
        "workflow_version": WORKFLOW_VERSION,
        "idempotency_key": idem,
        "diagnose_iters": 0,
    }


_PRIORITY_TO_SEV = {"1": "SEV1", "2": "SEV2", "3": "SEV3", "4": "SEV4"}


def triage_router(
    state: InvestigationState, config: RunnableConfig | None = None
) -> dict[str, Any]:
    """Deterministic triage over real tools: resolve the incident + its alert storm, derive
    severity/category/affected-services/onset, and decide known-issue vs novel from a
    past-incident search. No LLM — this is the baseline the eventual model must beat.
    """
    incident_id = state.incident_id
    svc = _svc(config)
    record = (svc.get_incident(incident_id=incident_id).results or [None])[0]

    if record is None:  # unknown incident id — cannot classify from data; treat as novel
        alert = state.alert
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
    # (Deterministic baseline; the confidence-floored match verification is a later stage.)
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


def known_issue_fast_path(
    state: InvestigationState, config: RunnableConfig | None = None
) -> dict[str, Any]:
    """Deterministic short-circuit for a known issue: reuse the matched incident's stored
    resolution as the hypothesis and skip the full diagnose loop."""
    match = state.matched_incident
    inc_id = match.split(":", 1)[1] if ":" in match else state.incident_id
    record = _svc(config).get_incident(incident_id=inc_id).results
    resolution = record[0].resolution if (record and record[0].resolution) else ""
    ref = f"past_incident:{inc_id}"
    hypothesis = Hypothesis(
        statement=f"Known issue — recurrence of {inc_id}. Prior resolution: {resolution}",
        confidence=0.95,
        citations=[EvidenceCitation(source="past_incident", ref=ref, note=resolution)],
    )
    return {
        "hypothesis": hypothesis,
        "evidence_by_id": _evidence_map([EvidenceItem.make("past_incident", ref, resolution)]),
    }


def retrieve(state: InvestigationState, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Real hybrid retrieval via ToolService; degrades to no evidence if retrieval is down."""
    query = state.alert.get("summary", "")
    svc = _svc(config)
    items: list[EvidenceItem] = []
    for hit in svc.search_runbooks(query=query, k=5).results:
        items.append(EvidenceItem.make("runbook", hit.doc_id, hit.title))
    for hit in svc.search_past_incidents(query=query, k=3).results:
        inc_id = hit.doc_id.split(":", 1)[1] if ":" in hit.doc_id else hit.doc_id
        items.append(EvidenceItem.make("past_incident", f"past_incident:{inc_id}", hit.title))
    return {"evidence_by_id": _evidence_map(items)}


def diagnose(state: InvestigationState, config: RunnableConfig | None = None) -> dict[str, Any]:
    """One deterministic diagnostic cycle (deployment-regression path + counter-evidence). No LLM
    yet — the reasoning agent will later plug into these same contracts and transitions. Computes
    the deterministic sufficiency state that decides whether the loop is allowed to stop."""
    from opspilot.diagnosis.contracts import DiagnosisContext
    from opspilot.diagnosis.cycle import plan_investigation, run_cycle
    from opspilot.diagnosis.sufficiency import compute_sufficiency

    ctx = DiagnosisContext(
        incident_id=state.incident_id,
        affected_services=state.affected_services,
        onset=state.onset,
        category=state.category or "",
    )
    plan = plan_investigation(ctx)
    already = set(state.answered_questions)
    hypothesis, observations, stop, newly = run_cycle(_svc(config), ctx, plan, already)

    evidence = [EvidenceItem.make(c.source, c.ref, c.note) for c in hypothesis.citations]
    answered = already | newly
    plan_can_advance = bool({q.key for q in plan.questions} - answered)
    # Coverage is over everything gathered (the observation trail), not just what is cited.
    produced_refs = {r for o in observations for r in o.evidence_refs} | {c.ref for c in
                                                                          hypothesis.citations}
    sufficiency = compute_sufficiency(state.severity, produced_refs, hypothesis, plan_can_advance)

    return {
        "hypothesis": hypothesis,
        "evidence_by_id": _evidence_map(evidence),
        "diagnose_iters": state.diagnose_iters + 1,
        "diagnosis": DiagnosisTrace(observations=observations, stop_reason=stop),
        "answered_questions": sorted(answered),
        "sufficiency": sufficiency,
    }


def synthesize_report(state: InvestigationState) -> dict[str, Any]:
    hyp = state.hypothesis
    report = {
        "incident_id": state.incident_id or "INC-STUB",
        "severity": state.severity or "SEV3",
        "category": state.category or "unknown",
        "hypothesis": hyp.statement if hyp else "",
        "confidence": hyp.confidence if hyp else 0.0,
        # published report evidence shape — the internal content_hash stays in state
        "evidence": [{"source": ev.source, "ref": ev.ref, "content": ev.content}
                     for ev in state.evidence_by_id.values()],
        "recommended_next_step": "(stub) roll back the most recent deploy and re-observe.",
        "citations": state.evidence_refs(),
    }
    return {"report": report}


def safety_validate(state: InvestigationState) -> dict[str, Any]:
    """Output guardrail: no unsupported hypothesis. Every report citation must be an evidence
    reference produced by a tool during this run (exempt only the info_only reply)."""
    from opspilot.guardrails.policies import hypothesis_supported

    if state.intent == Intent.INFO_ONLY.value:  # ungrounded informational reply — exempt
        return {"safety": {"passed": True, "violations": [], "exempt": "info_only"}}

    citations = (state.report or {}).get("citations", [])
    produced = set(state.evidence_refs())
    passed, violations = hypothesis_supported(citations, produced)
    return {"safety": {"passed": passed, "violations": violations}}


def hitl_gate(state: InvestigationState) -> dict[str, Any]:
    # The HITL stage replaces this with a checkpoint-backed interrupt(). For the walking
    # skeleton we auto-approve so the flow completes without a human in the loop.
    return {"approval": {"decision": "approve", "approver": "stub", "edits": None}}


def finalize_report(state: InvestigationState) -> dict[str, Any]:
    return {"report": state.report or {}}


def postmortem(state: InvestigationState) -> dict[str, Any]:
    # The HITL/memory stage writes this back to the cross-thread incident Store.
    return {
        "postmortem": {
            "incident_id": state.incident_id or "INC-STUB",
            "resolution": state.hypothesis.statement if state.hypothesis else "",
        }
    }


def escalate(state: InvestigationState) -> dict[str, Any]:
    """Terminal hand-off to a human — always with a machine-readable reason, never silent."""
    if state.error:
        reason = state.error
    elif state.diagnose_iters >= MAX_DIAGNOSE_ITERS:
        reason = f"iteration_budget_exhausted: diagnose_iters={state.diagnose_iters}"
    elif state.sufficiency is not None and not state.sufficiency.plan_can_advance:
        s = state.sufficiency
        reason = (f"plan_exhausted_insufficient: coverage={s.evidence_coverage} "
                  f"classes={s.evidence_classes} required={s.required_classes}")
    else:
        reason = "escalated to human"
    return {"degraded": True, "error": reason}
