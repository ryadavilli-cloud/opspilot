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
from opspilot.contracts import EvidenceItem as ReportEvidence
from opspilot.contracts import IncidentReport
from opspilot.data.operational_records import SourceUnavailable
from opspilot.diagnosis.admission import entities_from_refs
from opspilot.diagnosis.contracts import EvidenceCitation, Hypothesis
from opspilot.diagnosis.render import render_report_claim_statement
from opspilot.state import DiagnosisTrace, EvidenceItem, Intent, InvestigationState
from opspilot.tools.contracts import IncidentRecord

_UNIT_SEP = "\x1f"


def _svc(config: RunnableConfig | None):
    """Resolve the injected ToolService, or construct a default (direct-call tests / CLI)."""
    if config:
        injected = (config.get("configurable") or {}).get("tool_service")
        if injected is not None:
            return injected
    from opspilot.tools.service import ToolService

    return ToolService()


def _planner(config: RunnableConfig | None):
    """Resolve the injected diagnosis planner, or default to the deterministic floor.

    Mirrors `_svc`: the planner is injected via LangGraph `config` at the composition root
    (the eval harness selects it per `implementation`); direct-call tests and the CLI get the
    deterministic planner, so behavior is unchanged unless a caller opts in."""
    if config:
        injected = (config.get("configurable") or {}).get("planner")
        if injected is not None:
            return injected
    from opspilot.diagnosis.planner import DeterministicPlanner

    return DeterministicPlanner()


def _triager(config: RunnableConfig | None):
    """Resolve the injected triager, or default to the deterministic floor (mirrors `_planner`)."""
    if config:
        injected = (config.get("configurable") or {}).get("triager")
        if injected is not None:
            return injected
    from opspilot.triage import DeterministicTriager

    return DeterministicTriager()


def _evidence_map(items: list[EvidenceItem]) -> dict[str, EvidenceItem]:
    """Key evidence by content hash so the merge reducer dedups it."""
    return {item.content_hash: item for item in items}


def _gathering_block_reason(sufficiency, *, iters: int) -> str:
    """Why this gathering turn blocks, named at the moment the block is decided (G-36).

    Mirrors `diagnose_continue`'s escalate branch: the router picks the edge, this names the cause.
    Returns "" when the turn is not blocking, which also clears any earlier turn's stamp: a run
    that recovers must not carry a stale reason into a later, different escalation.
    """
    if sufficiency.ready:
        return ""
    if iters >= MAX_DIAGNOSE_ITERS:
        return f"iteration_budget_exhausted: diagnose_iters={iters}"
    if not sufficiency.plan_can_advance:
        return (
            f"plan_exhausted_insufficient: coverage={sufficiency.evidence_coverage} "
            f"classes={sufficiency.evidence_classes} required={sufficiency.required_classes}"
        )
    return ""


def ingest(state: InvestigationState) -> dict[str, Any]:
    """Normalize the alert; mint a unique investigation_id and derive thread_id from it.

    Honors a caller-supplied `investigation_id` already on state (the async API mints one at
    `POST /investigations` time and threads it through as the checkpointer's `thread_id` too, so
    the polled id, the checkpoint namespace, and this state field are one identifier) rather than
    always minting a fresh one — a bare caller (tests, the eval harness) leaves it unset and gets
    the old unconditional-mint behavior.
    """
    alert = state.alert
    incident_id = alert.get("incident_id", "INC-STUB")
    investigation_id = state.investigation_id or str(uuid4())
    idem = hashlib.sha256(
        _UNIT_SEP.join((incident_id, alert.get("summary", ""))).encode("utf-8")
    ).hexdigest()
    return {
        "incident_id": incident_id,
        "investigation_id": investigation_id,
        "thread_id": f"thread-{investigation_id}",
        "trace_id": investigation_id,  # span correlation id (Stage 5g) == investigation id
        "workflow_version": WORKFLOW_VERSION,
        "idempotency_key": idem,
        "diagnose_iters": 0,
    }


_PRIORITY_TO_SEV = {"1": "SEV1", "2": "SEV2", "3": "SEV3", "4": "SEV4"}


def _stored_incident(svc: Any, incident_id: str) -> IncidentRecord | None:
    """The stored incident row, read directly rather than through the capability.

    This path wants the incident's own description and its stored resolution, and neither is
    something a capability may hand an agent: what `get_incident` admits is the narrower approved
    surface. Reading the row here keeps that boundary intact while this deterministic baseline
    still works. An unreachable source reads as an unknown incident, which is what the envelope
    this replaced already did.
    """
    try:
        raw = svc.records.incident(incident_id, deadline_s=svc.deadline_s)
    except SourceUnavailable:
        return None
    return IncidentRecord(**raw) if raw else None


def triage_router(
    state: InvestigationState, config: RunnableConfig | None = None
) -> dict[str, Any]:
    """Deterministic triage over real tools: resolve the incident + its alert storm, derive
    severity/category/affected-services/onset, and decide known-issue vs novel from a
    past-incident search. No LLM — this is the baseline the eventual model must beat.
    """
    incident_id = state.incident_id
    svc = _svc(config)
    record = _stored_incident(svc, incident_id)

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

    # Data extraction stays deterministic; the intent + known-issue candidate is the triager's call
    # (deterministic self-match baseline, or LLM recurrence detection at 4c).
    from opspilot.triage import PastCandidate, TriageContext

    past = svc.search_past_incidents(query=record.short_description, k=3).results
    ctx = TriageContext(
        incident_id=incident_id,
        short_description=record.short_description,
        category=record.category,
        affected_services=affected,
        alert_signals=sorted({a.signal for a in alerts if a.signal}),
        past_candidates=[PastCandidate(doc_id=p.reference, title=p.title) for p in past],
    )
    decision = _triager(config).classify(ctx)
    matched = decision.matched_incident

    return {
        "severity": _PRIORITY_TO_SEV.get(record.priority[:1], "SEV3"),
        "category": record.category,
        "intent": decision.intent,
        "matched_incident": matched,
        "affected_services": affected,
        "onset": onset.isoformat(),
        "triage": {
            "route": "known-incident" if matched else "novel-investigation",
            "matched_incident": matched,
            "affected_services": affected,
            "onset": onset.isoformat(),
            "top_past_incidents": [p.reference for p in past],
            "reason": (
                f"known-issue candidate: {matched}"
                if matched
                else "no prior postmortem matched as a recurrence"
            ),
        },
    }


def known_issue_fast_path(
    state: InvestigationState, config: RunnableConfig | None = None
) -> dict[str, Any]:
    """Deterministic short-circuit for a known issue: reuse the matched incident's stored
    resolution as the hypothesis and skip the full diagnose loop."""
    match = state.matched_incident
    inc_id = match.split(":", 1)[1] if ":" in match else state.incident_id
    record = _stored_incident(_svc(config), inc_id)
    resolution = (record.resolution or "") if record else ""
    ref = f"past_incident:{inc_id}"
    hypothesis = Hypothesis(
        statement=f"Known issue — recurrence of {inc_id}. Prior resolution: {resolution}",
        confidence=0.95,
        citations=[EvidenceCitation(source="past_incident", ref=ref, note=resolution)],
    )
    return {
        "hypothesis": hypothesis,
        "evidence_by_id": _evidence_map([EvidenceItem.make("past_incident", ref, resolution)]),
        "produced_refs": [ref],  # the matched postmortem is real, retrieved evidence
    }


def retrieve(state: InvestigationState, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Real hybrid retrieval via ToolService; degrades to no evidence if retrieval is down."""
    query = state.alert.get("summary", "")
    svc = _svc(config)
    items: list[EvidenceItem] = []
    for passage in svc.search_runbooks(query=query, k=5).results:
        items.append(EvidenceItem.make("runbook", passage.reference, passage.title))
    for passage in svc.search_past_incidents(query=query, k=3).results:
        reference = passage.reference
        inc_id = reference.split(":", 1)[1] if ":" in reference else reference
        items.append(EvidenceItem.make("past_incident", f"past_incident:{inc_id}", passage.title))
    # Retrieved docs are real, tool-produced evidence — part of the grounding set the safety gate
    # validates citations against (a report may cite a retrieved runbook or past incident).
    return {"evidence_by_id": _evidence_map(items), "produced_refs": [it.ref for it in items]}


def diagnose(state: InvestigationState, config: RunnableConfig | None = None) -> dict[str, Any]:
    """One deterministic diagnostic cycle (deployment-regression path + counter-evidence). No LLM
    yet — the reasoning agent will later plug into these same contracts and transitions. Computes
    the deterministic sufficiency state that decides whether the loop is allowed to stop."""
    from opspilot.diagnosis.contracts import DiagnosisContext
    from opspilot.diagnosis.cycle import run_cycle
    from opspilot.diagnosis.sufficiency import compute_sufficiency

    ctx = DiagnosisContext(
        incident_id=state.incident_id,
        affected_services=state.affected_services,
        onset=state.onset,
        category=state.category or "",
    )
    already = set(state.answered_questions)
    planner = _planner(config)
    # The planner sees the FULL trail (accumulated across turns), not just the last turn, so a model
    # planner knows everything it has already gathered and does not repeat calls.
    plan = planner.plan(ctx, answered=already, observations=state.observation_trail)
    hypothesis, observations, stop, newly = run_cycle(_svc(config), ctx, plan, already)

    # The grounding set: every ref a tool actually produced, accumulated across turns (the LLM
    # loop gathers one question per turn). A hypothesis may cite only refs in this trail — this is
    # what the safety guardrail validates against, so a fabricated citation cannot self-certify.
    this_turn_refs = {r for o in observations for r in o.evidence_refs}
    # Two distinct sets: `produced` is the grounding set the safety gate validates citations against
    # (includes retrieved docs — a report may cite a runbook). `diagnostic_refs` is only the
    # diagnose-tool evidence (logs/metrics/deps/deploys) — the sufficiency gate must not count a
    # retrieved runbook as diagnostic coverage, or an unknown incident would look "solved".
    produced = set(state.produced_refs) | this_turn_refs
    diagnostic_refs = {r for o in state.observation_trail + observations for r in o.evidence_refs}
    answered = already | newly
    plan_can_advance = planner.wants_to_continue(plan, answered=answered)
    sufficiency = compute_sufficiency(state.severity, diagnostic_refs, hypothesis, plan_can_advance)

    # The sufficiency gate ends *gathering*; on the stopping turn the planner synthesizes the final
    # grounded conclusion from the full trail (the model's root cause replaces run_cycle's
    # provisional hypothesis; the deterministic planner no-ops, so its output is unchanged).
    stopping = (
        sufficiency.ready or state.diagnose_iters + 1 >= MAX_DIAGNOSE_ITERS or not plan_can_advance
    )
    # The entities a claim may blame: those named in refs the tools actually produced, plus the
    # triaged affected services. A claim about anything else is about something this run never
    # observed, so admission refuses it (Stage 5e; topology-version validation is G-42 at 6a).
    known_entities = entities_from_refs(produced) | set(state.affected_services)
    conclusion = planner.conclude(
        hypothesis,
        ctx=ctx,
        produced_refs=produced,
        observations=state.observation_trail + observations,
        known_entities=known_entities,
        final=stopping,
    )
    hypothesis = conclusion.hypothesis

    evidence = [EvidenceItem.make(c.source, c.ref, c.note) for c in hypothesis.citations]

    return {
        "hypothesis": hypothesis,
        "causal": conclusion.causal,
        "report_claims": conclusion.report_claims,
        "evidence_by_id": _evidence_map(evidence),
        "produced_refs": sorted(this_turn_refs),
        "diagnose_iters": state.diagnose_iters + 1,
        "diagnosis": DiagnosisTrace(observations=observations, stop_reason=stop),
        "observation_trail": observations,
        "answered_questions": sorted(answered),
        "sufficiency": sufficiency,
        # Stamped here, not inferred later (G-36). Empty on a turn that keeps gathering.
        "error": _gathering_block_reason(sufficiency, iters=state.diagnose_iters + 1),
    }


# Used only when the run produced no `recommendation` claim of its own. Deliberately NOT a
# rollback: hard-coding rollback as the recommendation for every incident is a prohibited pattern
# (code guidelines §21), and it is wrong whenever the cause is a dependency or an external fault.
_NO_RECOMMENDATION = "No specific next step was derived; hand to the on-call engineer for triage."


def synthesize_report(state: InvestigationState) -> dict[str, Any]:
    hyp = state.hypothesis
    claims = state.report_claims
    # A recommendation the run actually derived, rendered from its structured claim, replaces the
    # old fixed rollback string. Falls back to an explicit "nothing derived" rather than inventing
    # an action, so an empty result reads as empty instead of as advice.
    recommendation = next((c for c in claims if c.kind == "recommendation"), None)
    report = IncidentReport(
        incident_id=state.incident_id or "INC-STUB",
        severity=state.severity or "SEV3",
        category=state.category or "unknown",
        hypothesis=hyp.statement if hyp else "",
        confidence=hyp.confidence if hyp else 0.0,
        # published report evidence shape — the internal content_hash stays in state
        evidence=[
            ReportEvidence(source=ev.source, ref=ev.ref, content=ev.content)
            for ev in state.evidence_by_id.values()
        ],
        recommended_next_step=(
            render_report_claim_statement(recommendation) if recommendation else _NO_RECOMMENDATION
        ),
        citations=state.evidence_refs(),
        report_claims=claims,
    )
    return {"report": report, "report_hash": report.content_hash()}


def safety_validate(state: InvestigationState) -> dict[str, Any]:
    """Output guardrail: no unsupported hypothesis. Every report citation must be an evidence
    reference produced by a tool during this run (exempt only the info_only reply). Delegates to
    the four-check grounding gate's reference-resolution primitive rather than a policy of its
    own."""
    from opspilot.grounding.checks import unresolved_references

    if state.intent == Intent.INFO_ONLY.value:  # ungrounded informational reply — exempt
        return {"safety": {"passed": True, "violations": [], "exempt": "info_only"}}

    report = state.report
    # Every published claim is checked, not just the headline citations (G-51). A report-level
    # claim whose support ref was never produced is exactly the ungrounded assertion the "every
    # claim cites tool-produced evidence" guarantee promises does not ship.
    citations = list(report.citations) if report else []
    if report:
        citations += [ref for claim in report.report_claims for ref in claim.support_refs]
    # Validate against the tool-produced ref trail, NOT evidence_refs() (which is derived from the
    # cited refs themselves — that would let a fabricated citation certify itself).
    produced = set(state.produced_refs)
    violations = (
        ["hypothesis has no supporting citations"]
        if not citations
        else unresolved_references(citations, produced)
    )
    passed = not violations
    if passed:
        return {"safety": {"passed": True, "violations": violations}}
    # Stamp the guardrail as the cause at the moment it blocks (G-36). Without this the run
    # escalates with whatever reason `escalate()` happened to probe for first, which reported a
    # citation-gate block as an exhausted iteration budget: specific, confident, and wrong.
    return {
        "safety": {"passed": False, "violations": violations},
        "error": (
            f"guardrail_blocked: unsupported_citations ({len(violations)}): "
            f"{'; '.join(violations[:3])}"
        ),
    }


def hitl_gate(state: InvestigationState) -> dict[str, Any]:
    """A checkpoint-backed pause: `interrupt()` persists state and suspends the graph until a
    human decision resumes it (`Command(resume=...)`, see `api.py`'s async decision endpoint).

    LangGraph re-executes this node from the top on resume, so everything above the `interrupt()`
    call runs again harmlessly (it's pure, no side effects) — only the code *after* it, which only
    ever runs once `interrupt()` has returned the human's decision, may act on that decision.
    """
    from langgraph.types import interrupt

    payload = {
        "kind": "approval_request",
        "incident_id": state.incident_id,
        "investigation_id": state.investigation_id,
        "report": state.report.model_dump() if state.report else None,
        "report_hash": state.report_hash,
        "safety": state.safety,
    }
    resume = interrupt(payload) or {}
    decision = resume.get("decision")
    edits = resume.get("edits")
    submitted_hash = resume.get("submitted_report_hash")

    # Identity is stamped by the API from a validated token (G-01) — this node never invents or
    # defaults it. `auth_method` absent means no identity was proven, which is exactly the
    # deterministic sync path; `_build_response` degrades that to the auto-approval label rather
    # than to "human", so an unproven decision can never be reported as human review.
    identity = {
        "approver": resume.get("approver", "unknown"),
        "approver_display_name": resume.get("approver_display_name"),
        "approver_tenant_id": resume.get("approver_tenant_id"),
        "auth_method": resume.get("auth_method"),
    }

    if submitted_hash != state.report_hash:
        # The decision was made against a report that no longer matches current state (e.g. a
        # concurrent edit/decision advanced the thread first). "stale_rejected" is neither
        # "approve" nor "edit", so it already falls into after_approval's fail-closed else-branch.
        #
        # As of G-32 this branch is unreachable from the decision endpoint: the stale check moved
        # into the repository's atomic commit, which rejects a stale hash with a 409 and leaves the
        # run `awaiting_approval` - it never resumes the graph, so this node never sees it. It is
        # kept anyway, for the same reason `finalize_report` asserts its invariant rather than
        # trusting the routing: the alternative to failing closed here is applying a human decision
        # to a report they did not review. The sync path always submits the current hash.
        return {
            "approval": {
                **identity,
                "decision": "stale_rejected",
                "edits": edits,
                "submitted_report_hash": submitted_hash,
                "current_report_hash": state.report_hash,
                "approved_report_hash": None,
            },
            "error": (
                f"stale_approval: submitted for {submitted_hash}, current is {state.report_hash}"
            ),
        }

    # A human decision that ends the run carries its own reason, stamped here rather than
    # re-derived by `escalate()` (G-36). `approve` and `edit` continue, so they stamp nothing.
    who = identity["approver"]
    blocked = {
        "reject": f"human_rejected by {who}",
        "request_more_evidence": f"human_requested_more_evidence by {who}",
    }
    return {
        "approval": {
            **identity,
            "decision": decision,
            "edits": edits,
            "approved_report_hash": state.report_hash if decision == "approve" else None,
        },
        "error": blocked.get(str(decision), ""),
    }


def apply_edit(state: InvestigationState) -> dict[str, Any]:
    """Apply the reviewer's edits to the report, re-validating into a NEW frozen IncidentReport and
    recomputing its hash. The graph routes the result back through safety_validate — an edit never
    reaches finalize without passing the guardrail (and being re-bound to its new hash) again."""
    edits = (state.approval or {}).get("edits") or {}
    base = state.report.model_dump() if state.report else {}
    report = IncidentReport.model_validate({**base, **edits})
    return {"report": report, "report_hash": report.content_hash()}


def finalize_report(state: InvestigationState) -> dict[str, Any]:
    """Publish the byte-exact object the approval was bound to, under a stable `publication_id`.

    `after_approval` only routes here on `decision == "approve"`, which `hitl_gate` only ever sets
    once `submitted_report_hash == state.report_hash` — so this invariant should be unreachable in
    practice. It is asserted explicitly anyway rather than left as a comment: a future change to
    the routing that broke it would otherwise publish a report the approval never saw, silently.

    The `publication_id` is **derived from (investigation_id, report_hash), never minted** (G-58).
    That is the whole mechanism: LangGraph re-executes an interrupted node from the top, so a
    checkpoint-recovered run runs this node a second time, and a `uuid4()` here would hand the
    sink a fresh key each time and publish the same report twice. Deriving it means the second
    execution presents the key the first one already committed, and the sink refuses it. Binding
    it to `report_hash` rather than the run alone is deliberate: an `edit` produces different
    approved bytes, which is a genuinely different publication and must not be suppressed as a
    replay of the first.
    """
    approval = state.approval or {}
    if approval.get("approved_report_hash") != state.report_hash:
        raise RuntimeError(
            "finalize_report invariant violated: approved_report_hash="
            f"{approval.get('approved_report_hash')!r} does not match report_hash="
            f"{state.report_hash!r}"
        )
    raw = _UNIT_SEP.join((state.investigation_id or "", state.report_hash))
    return {
        "report": state.report,
        "report_hash": state.report_hash,
        "publication_id": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }


def postmortem(state: InvestigationState) -> dict[str, Any]:
    # The HITL/memory stage writes this back to the cross-thread incident Store.
    return {
        "postmortem": {
            "incident_id": state.incident_id or "INC-STUB",
            "resolution": state.hypothesis.statement if state.hypothesis else "",
        }
    }


def escalate(state: InvestigationState) -> dict[str, Any]:
    """Terminal hand-off to a human, always with a machine-readable reason, never silent.

    This node REPORTS the reason the blocking node stamped; it no longer derives one (G-36). The
    old version probed state in a fixed order (`error` -> approval decision -> iteration budget ->
    plan advancement -> a generic fallback), so any cause it did not test for was reported as
    whichever probe matched first. A guardrail block, which set nothing at all, surfaced as
    `plan_exhausted_insufficient` or `iteration_budget_exhausted`: a confident, specific, wrong
    reason. And since `InvestigationResponse.reason` is public API, a published falsehood.

    Inference cannot be repaired by adding probes, because the next unprobed cause repeats the
    failure. The fix is that every path into this node names its own cause first. An empty stamp is
    therefore a defect in the caller, and is reported as one rather than papered over with a
    plausible guess.
    """
    return {
        "degraded": True,
        "error": state.error or "unattributed_escalation: no blocking node stamped a reason",
    }
