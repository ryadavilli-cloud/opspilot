"""Admission: the deterministic boundary between a source result and the turn's evidence.

This is code, not agent judgment, and it is the only way into the evidence set. An agent cannot
create evidence; a model summary is not evidence however well formed. Every capability goes
through here, so a result reached one way is admitted exactly as a result reached another.

Only a `succeeded` result may be admitted. Everything else produces an operation record and a
limitation, and no observation. The workflow never fabricates an observation to stand in for a
call that did not answer.

`succeeded` with `empty` is admitted, because an authoritative absence is a real observation about
the scope that was queried. "No error logs for this service in this window" can rule a hypothesis
out. It is admitted with a canonical representation naming the scope and the absence, so it is as
inspectable as any other observation rather than an empty record a reader must interpret.

Admission does not re-decide what the boundary already settled. Dispatch decided whether the call
was permitted; the adapter decided that the outcome and completeness form a legal pairing. This
reads both as given and decides only whether the result may become evidence, then assigns the
evidence reference. It does not score, rank, weight, or judge.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from opspilot.evidence.operations import OperationRecord, TurnEvidence
from opspilot.evidence.references import Reference, try_parse
from opspilot.obs.tracing import span
from opspilot.tools.contracts import Completeness, ExecutionOutcome, ToolResult


class EvidenceType(StrEnum):
    """What was observed. A compact vocabulary, not a taxonomy extended per source or scenario."""

    INCIDENT_OR_ALERT = "incident_or_alert_observation"
    LOG_EVENT = "log_event"
    METRIC = "metric_observation"
    DEPLOYMENT_OR_CHANGE = "deployment_or_change_observation"
    DEPENDENCY_OR_TOPOLOGY = "dependency_or_topology_observation"
    STRUCTURED_OPERATIONAL_RECORD = "structured_operational_record"
    SERVICE_HEALTH = "service_health_observation"


# Capability to evidence type. Type describes meaning, never access path, so this maps by what the
# capability observes rather than by how it reached it. The two retrieval capabilities map to None
# deliberately rather than being absent: they produce knowledge, which is not operational evidence
# and is not admitted here. Keeping them present makes the coverage check total.
CAPABILITY_EVIDENCE_TYPES: Mapping[str, EvidenceType | None] = MappingProxyType(
    {
        "get_incident": EvidenceType.INCIDENT_OR_ALERT,
        "get_correlated_alerts": EvidenceType.INCIDENT_OR_ALERT,
        "get_deployments": EvidenceType.DEPLOYMENT_OR_CHANGE,
        "query_logs": EvidenceType.LOG_EVENT,
        "get_metrics": EvidenceType.METRIC,
        "get_service_dependencies": EvidenceType.DEPENDENCY_OR_TOPOLOGY,
        # The structured path observes operational records, which is what its type names. It does
        # not name the path, because the same record read by a dedicated capability would be the
        # same observation.
        "structured_query": EvidenceType.STRUCTURED_OPERATIONAL_RECORD,
        "search_runbooks": None,
        "search_past_incidents": None,
    }
)

# Why an operation did not answer, in the caller's terms. Derived from the execution outcome
# rather than classified again: a second vocabulary beside the outcome would be an invented one.
_LIMITATION_REASONS: Mapping[ExecutionOutcome, str] = MappingProxyType(
    {
        ExecutionOutcome.TIMED_OUT: "the source did not answer within the time allowed",
        ExecutionOutcome.UNAVAILABLE: "the source could not be reached",
        ExecutionOutcome.REJECTED: "the request was refused at the boundary",
        ExecutionOutcome.FAILED: "the source errored and returned no trustworthy answer",
    }
)


@dataclass(frozen=True)
class Limitation:
    """What could not be established, and why, in terms of the question it was meant to answer.

    No limitation category exists. The execution outcome already classifies the failure, and a
    second classification beside it would be a taxonomy nothing asked for.
    """

    question: str
    reason: str
    operation_ref: str
    capability: str
    outcome: ExecutionOutcome

    def __str__(self) -> str:
        return f"{self.question}: {self.reason}"


@dataclass(frozen=True)
class AdmittedObservation:
    """One admitted operational observation. Raw source output is not retained; this is what
    survives, carrying its normalized content, provenance, and a stable evidence reference."""

    evidence_ref: str
    investigation_id: str
    turn_id: str
    operation_ref: str
    evidence_type: EvidenceType
    source: str
    completeness: Completeness
    observation: Any
    entities: tuple[str, ...] = ()
    provenance: str = ""
    limitations: tuple[str, ...] = ()

    @property
    def is_authoritative_absence(self) -> bool:
        """An observation that the queried scope contains nothing. A positive finding: it can rule
        a hypothesis out, and it is never the same as a source that did not answer."""
        return self.completeness is Completeness.EMPTY


@dataclass(frozen=True)
class AuthoritativeAbsence:
    """The canonical representation of `succeeded + empty`.

    Deterministic and inspectable: it names the scope that was queried and states that nothing
    matched. No model writes this, because a generated sentence would make an absence look like an
    interpretation rather than a fact about the query.
    """

    capability: str
    scope: str
    nothing_matched: bool = True

    def __str__(self) -> str:
        return f"no matching observations for {self.capability}({self.scope})"


@dataclass
class AdmissionResult:
    """What one capability call produced: observations, or a limitation, never both."""

    operation: OperationRecord
    observations: list[AdmittedObservation] = field(default_factory=list)
    limitation: Limitation | None = None

    @property
    def admitted(self) -> bool:
        return bool(self.observations)


def _scope_text(request_scope: Mapping[str, Any] | None) -> str:
    if not request_scope:
        return ""
    return ", ".join(f"{k}={v}" for k, v in sorted(request_scope.items()) if v is not None)


def _entities_of(parsed: Reference | None) -> tuple[str, ...]:
    return parsed.entities if parsed else ()


def admit(
    result: ToolResult[Any],
    *,
    turn: TurnEvidence,
    question: str,
    request_scope: Mapping[str, Any] | None = None,
) -> AdmissionResult:
    """Admit a capability result into the turn, or record why it could not be admitted.

    `question` is what this call was meant to answer. It is required rather than optional because
    a limitation that cannot name its question discloses nothing useful.

    One span is emitted per call, whatever the outcome. An unresolvable citation is diagnosable
    from what was admitted and which reference it was assigned, without re-running the turn; a
    result that produced no evidence is as visible here as one that did.
    """
    capability = result.tool_name
    operation_ref = turn.ledger.mint()
    scope = _scope_text(request_scope)

    with span(
        "evidence.admit",
        attributes={
            "capability": capability,
            "operation_ref": operation_ref,
            "execution_outcome": result.outcome.value,
            "completeness": result.completeness.value,
        },
    ) as sp:
        return _admit(result, turn, question, capability, operation_ref, scope, sp)


def _admit(
    result: ToolResult[Any],
    turn: TurnEvidence,
    question: str,
    capability: str,
    operation_ref: str,
    scope: str,
    sp: Any,
) -> AdmissionResult:
    """The admission decision itself. Split from `admit` only so the span wraps every exit."""
    if result.outcome is not ExecutionOutcome.SUCCEEDED:
        operation = turn.ledger.record(
            OperationRecord(
                operation_ref=operation_ref,
                capability=capability,
                outcome=result.outcome,
                completeness=result.completeness,
                duration_ms=result.metadata.duration_ms,
                admitted=False,
                scope=scope,
            )
        )
        limitation = Limitation(
            question=question,
            reason=_LIMITATION_REASONS.get(result.outcome, "the operation did not answer"),
            operation_ref=operation_ref,
            capability=capability,
            outcome=result.outcome,
        )
        turn.limitations.append(limitation)
        sp.attributes["admitted"] = False
        sp.attributes["limitation"] = limitation.question
        return AdmissionResult(operation=operation, limitation=limitation)

    evidence_type = CAPABILITY_EVIDENCE_TYPES.get(capability)
    if evidence_type is None:
        # Retrieval produces knowledge, not operational evidence. It is not admitted here, and
        # silently admitting it would put a document into the current-proof set.
        operation = turn.ledger.record(
            OperationRecord(
                operation_ref=operation_ref,
                capability=capability,
                outcome=result.outcome,
                completeness=result.completeness,
                duration_ms=result.metadata.duration_ms,
                admitted=False,
                scope=scope,
            )
        )
        sp.attributes["admitted"] = False
        sp.attributes["not_operational_evidence"] = True
        return AdmissionResult(operation=operation)

    observations: list[AdmittedObservation] = []
    partial_note = ("the source returned part of the requested scope",)

    if result.completeness is Completeness.EMPTY:
        observations.append(
            AdmittedObservation(
                evidence_ref=f"absence:{capability}:{operation_ref}",
                investigation_id=turn.investigation_id,
                turn_id=turn.turn_id,
                operation_ref=operation_ref,
                evidence_type=evidence_type,
                source=capability,
                completeness=Completeness.EMPTY,
                observation=AuthoritativeAbsence(capability=capability, scope=scope),
                provenance=f"{capability}({scope})",
            )
        )
    else:
        already: set[str] = {obs.evidence_ref for obs in turn.observations}
        for index, ref in enumerate(result.evidence_refs):
            if ref in already:
                continue  # one operation does not admit the same item twice
            already.add(ref)
            record = result.results[index] if index < len(result.results) else None
            observations.append(
                AdmittedObservation(
                    evidence_ref=ref,
                    investigation_id=turn.investigation_id,
                    turn_id=turn.turn_id,
                    operation_ref=operation_ref,
                    evidence_type=evidence_type,
                    source=capability,
                    completeness=result.completeness,
                    observation=record,
                    entities=_entities_of(try_parse(ref)),
                    provenance=f"{capability}({scope})",
                    limitations=partial_note if result.completeness is Completeness.PARTIAL else (),
                )
            )

    operation = turn.ledger.record(
        OperationRecord(
            operation_ref=operation_ref,
            capability=capability,
            outcome=result.outcome,
            completeness=result.completeness,
            duration_ms=result.metadata.duration_ms,
            admitted=bool(observations),
            scope=scope,
        )
    )
    turn.observations.extend(observations)
    sp.attributes["admitted"] = bool(observations)
    sp.attributes["observation_count"] = len(observations)
    sp.attributes["evidence_refs"] = ",".join(obs.evidence_ref for obs in observations)
    # An absence carries a real evidence reference of its own, so it goes through the one parser
    # like any other. The marker stays because it is diagnostically useful, not because it stands
    # in for the reference.
    sp.attributes["references_parsed"] = sum(
        1 for obs in observations if try_parse(obs.evidence_ref) is not None
    )
    if result.completeness is Completeness.EMPTY:
        sp.attributes["authoritative_absence"] = True
    return AdmissionResult(operation=operation, observations=observations)
