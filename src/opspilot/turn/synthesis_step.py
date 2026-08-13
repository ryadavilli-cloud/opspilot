"""Gathering, admitting, and synthesizing for one predefined-incident turn.

The evidence path here is deterministic and fixed. Adaptive source selection belongs to the
Evidence Investigator, which does not exist yet, so this gathers a small standing set rather than
pretending to choose. It starts from correlated alerts because predefined intake normalizes to an
incident identity with no affected service, so the alerts are what identify the entities the
remaining calls are scoped to.

One model call happens, and only one: the synthesis. Everything around it is deterministic. What
the model is given is the admitted evidence and the questions that went unanswered, never a raw
provider payload and never anything from the answer key.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from opspilot.assessment.contracts import Assessment
from opspilot.assessment.synthesis import SYNTHESIS_TASK, admit_assessment, parse_proposal
from opspilot.evidence.operations import TurnEvidence
from opspilot.llm.base import ChatMessage
from opspilot.llm.prompts import get_prompt
from opspilot.obs import tracing
from opspilot.stream.contracts import ActivityEvent
from opspilot.stream.projection import ActivityProjector, emit
from opspilot.tools.contracts import ToolResult
from opspilot.turn.identity import TurnIdentity

# The window either side of the incident's time anchor that telemetry queries are scoped to.
EVIDENCE_WINDOW = timedelta(minutes=45)

# At most this many services are followed out of the correlated alerts. A bound, not a ranking:
# choosing which sources matter is the Evidence Investigator's job.
MAX_SERVICES = 3


def evidence_plan(context: Any, alerts: list[Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """(capability, the question it is meant to answer, validated parameters).

    The question travels with the call because a limitation that cannot name its question
    discloses nothing useful, and it is admission that turns a non-answer into that limitation.
    """
    services = sorted({a.service for a in alerts if getattr(a, "service", "")})
    start = (context.time_anchor - EVIDENCE_WINDOW).isoformat()
    end = (context.time_anchor + EVIDENCE_WINDOW).isoformat()

    plan: list[tuple[str, str, dict[str, Any]]] = []
    for service in services[:MAX_SERVICES]:
        plan.append(
            (
                "query_logs",
                f"were there error logs for {service} around the incident",
                {"service": service, "level": "error", "start_time": start, "end_time": end},
            )
        )
        plan.append(
            (
                "get_metrics",
                f"what did {service} metrics do around the incident",
                {"service": service, "start_time": start, "end_time": end},
            )
        )
    if services:
        # Kept deliberately, because an empty change history is a finding rather than a gap: it is
        # admitted as an authoritative absence and must not be read as a missing answer.
        plan.append(
            (
                "get_deployments",
                "did anything change before the incident",
                {"services": services, "start_time": start, "end_time": end},
            )
        )
    return plan


def evidence_digest(evidence: TurnEvidence) -> str:
    """What the model reasons over: admitted observations by reference, and what went unanswered."""
    lines = ["Admitted evidence:"]
    if evidence.observations:
        lines.extend(
            f"- {obs.evidence_ref} [{obs.evidence_type.value}] {obs.observation}"
            for obs in evidence.observations
        )
    else:
        lines.append("- (none)")
    if evidence.limitations:
        lines.append("Could not be established:")
        lines.extend(f"- {limitation}" for limitation in evidence.limitations)
    return "\n".join(lines)


def synthesize(model: Any, context: Any, evidence: TurnEvidence, objective: str) -> Assessment:
    """One bounded model call, then deterministic admission of what it proposed.

    The model's answer is a proposal. What survives into the assessment is decided against the
    admitted evidence set, not by the model.
    """
    prompt = get_prompt("rca_synthesis")
    user = "\n".join(
        [
            f"Turn objective: {objective}",
            f"Reported symptom: {context.symptom}",
            f"Time anchor: {context.time_anchor.isoformat()}",
            "",
            evidence_digest(evidence),
        ]
    )
    with tracing.span(
        f"model.{SYNTHESIS_TASK}",
        attributes={"task": SYNTHESIS_TASK, "prompt_version": prompt.version},
    ):
        result = model.complete(
            [
                ChatMessage(role="system", content=prompt.text),
                ChatMessage(role="user", content=user),
            ]
        )
    return admit_assessment(
        parse_proposal(result.text),
        investigation_id=evidence.investigation_id,
        turn_id=evidence.turn_id,
        objective=objective,
        observations=evidence.observations,
        limitations=evidence.limitations,
    )


def capability_event(
    turn: TurnIdentity,
    projector: ActivityProjector,
    capability: str,
    result: ToolResult[Any],
    *,
    admitted: int,
    references: list[str] | None = None,
) -> ActivityEvent:
    """One activity entry per capability call, carrying both result axes rather than a verdict.

    `succeeded` with `empty` reads here as an authoritative absence, visibly distinct from a source
    that did not answer, which is the whole reason the two axes are separate.
    """
    return emit(
        "turn.capability",
        turn,
        projector,
        phase="investigating",
        action=capability,
        detail=(
            f"{capability}: {result.outcome.value}, {result.completeness.value} "
            f"({admitted} admitted)"
        ),
        capability=capability,
        transport="direct",
        outcome=result.outcome.value,
        references=references or [],
    )
