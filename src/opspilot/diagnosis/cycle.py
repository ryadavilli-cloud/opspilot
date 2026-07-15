"""One deterministic diagnostic cycle — the deployment-regression decision path, with a
counter-evidence step so the red herring is at least *investigated* deterministically.

    context -> get_deployments -> query_logs -> get_service_dependencies -> get_metrics
    -> deployment-regression hypothesis (naive: still blames a coincidental deploy)

No LLM and no `if`-tower masquerading as intelligence: the point is to freeze the plan/execute/
observe/update transitions and the contracts, and to *gather* the dependency + metric evidence a
severity-scaled sufficiency gate needs — not to reason over it. The deterministic hypothesis stays
deploy-focused (so inc-004's red herring is scored wrong; that is the honest floor the LLM beats).

Plan advancement: each question carries a stable `key`; a re-entered loop skips already-answered
questions and reports whether any remain (`plan_can_advance`), so re-entry never re-asks or spins.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from opspilot.config import MAX_DIAGNOSE_ITERS
from opspilot.diagnosis.contracts import (
    DiagnosisContext,
    DiagnosticQuestion,
    EvidenceCitation,
    Hypothesis,
    InvestigationPlan,
    StopReason,
    ToolCallRequest,
    ToolObservation,
)
from opspilot.guardrails.policies import is_read_only

if TYPE_CHECKING:
    from opspilot.tools.service import ToolService

DEPLOY_LOOKBACK_HOURS = 24
WINDOW_MINUTES = 30


def _parse(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(iso) if iso else None
    except ValueError:
        return None


def plan_investigation(ctx: DiagnosisContext) -> InvestigationPlan:
    """Build the deploy-regression plan (+ counter-evidence). Needs onset + affected services."""
    onset = _parse(ctx.onset)
    services = ctx.affected_services
    if not (onset and services):
        return InvestigationPlan(max_iters=MAX_DIAGNOSE_ITERS, questions=[])

    trigger = "checkout-api" if "checkout-api" in services else services[-1]
    window_start = (onset - timedelta(minutes=WINDOW_MINUTES)).isoformat()
    window_end = (onset + timedelta(minutes=WINDOW_MINUTES)).isoformat()

    return InvestigationPlan(
        max_iters=MAX_DIAGNOSE_ITERS,
        questions=[
            DiagnosticQuestion(
                key="deployments",
                question="What changed before onset? (recent deployments to the affected services)",
                call=ToolCallRequest(tool="get_deployments", params={
                    "services": services,
                    "start_time": (onset - timedelta(hours=DEPLOY_LOOKBACK_HOURS)).isoformat(),
                    "end_time": (onset + timedelta(minutes=15)).isoformat(),
                }),
            ),
            DiagnosticQuestion(
                key="error_logs",
                question="Are there error logs on the customer-facing service around onset?",
                call=ToolCallRequest(tool="query_logs", params={
                    "service": trigger, "level": "error",
                    "start_time": window_start, "end_time": window_end,
                }),
            ),
            # Counter-evidence: before trusting a deploy, check whether the trigger's downstream
            # dependencies are the real story (the inc-004 red-herring discriminator).
            DiagnosticQuestion(
                key="dependency_health",
                question="What does the customer-facing service depend on? (blast radius)",
                call=ToolCallRequest(tool="get_service_dependencies", params={
                    "service": trigger, "direction": "downstream",
                }),
            ),
            DiagnosticQuestion(
                key="downstream_metrics",
                question="Do the trigger's own metrics show degradation in the window?",
                call=ToolCallRequest(tool="get_metrics", params={
                    "service": trigger, "start_time": window_start, "end_time": window_end,
                }),
            ),
        ],
    )


def run_cycle(
    service: ToolService,
    ctx: DiagnosisContext,
    plan: InvestigationPlan,
    answered: Iterable[str] = (),
) -> tuple[Hypothesis, list[ToolObservation], StopReason, set[str]]:
    """Execute the not-yet-answered questions. Returns the hypothesis, the observations, the stop
    reason, and the set of question keys answered this run (for plan advancement)."""
    already = set(answered)
    to_ask = [q for q in plan.questions if q.key not in already]

    observations: list[ToolObservation] = []
    citations: list[EvidenceCitation] = []
    newly_answered: set[str] = set()
    deploy_note = ""
    stop: StopReason | None = None

    for i, q in enumerate(to_ask):
        if i >= plan.max_iters:  # hard iteration limit
            stop = StopReason(reason="iteration_limit", detail=f"hit max_iters={plan.max_iters}")
            break
        if not is_read_only(q.call.tool):  # read-only tool policy
            observations.append(ToolObservation(
                question=q.question, tool=q.call.tool, status="blocked:not_read_only",
                evidence_refs=[], result_count=0))
            newly_answered.add(q.key)
            continue
        result = service.call(q.call.tool, **q.call.params)
        observations.append(ToolObservation(
            question=q.question, tool=q.call.tool, status=result.status,
            evidence_refs=list(result.evidence_refs), result_count=len(result.results)))
        newly_answered.add(q.key)

        # Citations stay deploy-focused: the deterministic hypothesis names the deploy + a log.
        # Dependency/metric results are gathered (they land in observations and feed the
        # sufficiency gate) but deliberately not cited — the naive baseline ignores them.
        if q.call.tool == "get_deployments" and result.results:
            latest = max(result.results, key=lambda d: d.ts)  # closest deploy before onset
            deploy_note = (f"deployment {latest.deploy_id} on {latest.service} "
                           f"at {latest.ts.isoformat()}")
            citations.append(EvidenceCitation(
                source="deploys", ref=f"deploys:{latest.service}:{latest.deploy_id}",
                note=f"{deploy_note}, preceding onset {ctx.onset}"))
        elif q.call.tool == "query_logs" and result.evidence_refs:
            citations.append(EvidenceCitation(
                source="logs", ref=result.evidence_refs[0],
                note="error log on the affected service within the incident window"))

    if stop is None:
        stop = StopReason(
            reason="hypothesis_supported" if citations else "no_more_questions",
            detail=f"{len(citations)} supporting citations")

    if deploy_note:
        statement = (f"Likely deployment regression: {deploy_note} preceded symptom onset at "
                     f"{ctx.onset}.")
        confidence = 0.8
    elif citations:
        statement = "Partial evidence found but no implicated deployment; recommend manual review."
        confidence = 0.55
    else:
        statement = "Insufficient deployment/log evidence in the window; recommend manual review."
        confidence = 0.2

    hypothesis = Hypothesis(statement=statement, confidence=confidence, citations=citations)
    return hypothesis, observations, stop, newly_answered
