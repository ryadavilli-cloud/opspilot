"""One deterministic diagnostic cycle — the deployment-regression decision path.

    incident context -> get_deployments -> query_logs -> compare deploy time with onset
    -> deployment-regression hypothesis

No LLM and no `if`-tower masquerading as intelligence: the point is to freeze the plan/execute/
observe/update transitions and the contracts, and prove one path end to end from real tool
observations. The hard iteration cap lives on the plan (`max_iters`).
"""

from __future__ import annotations

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


def _parse(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(iso) if iso else None
    except ValueError:
        return None


def plan_investigation(ctx: DiagnosisContext) -> InvestigationPlan:
    """Build the deployment-regression plan. Needs onset + affected services."""
    onset = _parse(ctx.onset)
    services = ctx.affected_services
    if not (onset and services):
        return InvestigationPlan(max_iters=MAX_DIAGNOSE_ITERS, questions=[])

    trigger = "checkout-api" if "checkout-api" in services else services[-1]
    return InvestigationPlan(
        max_iters=MAX_DIAGNOSE_ITERS,
        questions=[
            DiagnosticQuestion(
                question="What changed before onset? (recent deployments to the affected services)",
                call=ToolCallRequest(tool="get_deployments", params={
                    "services": services,
                    "start_time": (onset - timedelta(hours=DEPLOY_LOOKBACK_HOURS)).isoformat(),
                    "end_time": (onset + timedelta(minutes=15)).isoformat(),
                }),
            ),
            DiagnosticQuestion(
                question="Are there error logs on the customer-facing service around onset?",
                call=ToolCallRequest(tool="query_logs", params={
                    "service": trigger,
                    "start_time": (onset - timedelta(minutes=30)).isoformat(),
                    "end_time": (onset + timedelta(minutes=30)).isoformat(),
                    "level": "error",
                }),
            ),
        ],
    )


def run_cycle(
    service: ToolService, ctx: DiagnosisContext, plan: InvestigationPlan
) -> tuple[Hypothesis, list[ToolObservation], StopReason]:
    observations: list[ToolObservation] = []
    citations: list[EvidenceCitation] = []
    deploy_note = ""
    stop: StopReason | None = None

    for i, q in enumerate(plan.questions):
        if i >= plan.max_iters:  # hard iteration limit
            stop = StopReason(reason="iteration_limit", detail=f"hit max_iters={plan.max_iters}")
            break
        if not is_read_only(q.call.tool):  # read-only tool policy
            observations.append(ToolObservation(
                question=q.question, tool=q.call.tool, status="blocked:not_read_only",
                evidence_refs=[], result_count=0))
            continue
        result = service.call(q.call.tool, **q.call.params)
        observations.append(ToolObservation(
            question=q.question, tool=q.call.tool, status=result.status,
            evidence_refs=list(result.evidence_refs), result_count=len(result.results)))

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
    return hypothesis, observations, stop
