"""Admission: the model PROPOSES a structured claim, code ADMITS it (Stage 5e, G-29).

`SynthesisResponse.causal` arrives as loose strings because a model cannot be trusted to satisfy a
`Literal` union or to name an entity that exists. Everything here converts that proposal into the
strict `CausalClaim` the report is rendered from and the 6b detectors interrogate, or refuses it.

The refusal path is the point. A deterministic check over a model-controlled input is
deterministic in form only, so a claim that cannot be grounded in this run's evidence must not
become a `GroundedRcaReport` at all. Failing closed here means the run degrades to a prose
hypothesis rather than publishing a typed structure nothing verified.

Scope note: entity resolution is against the entities THIS RUN actually touched: the services
named in tool-produced evidence refs, plus the triaged affected services. That is a real
grounding check (those refs came from real tool calls) but it is not yet topology-version
validation: `valid_from`/`valid_to` edges and `topology_version` need the typed-evidence work
(G-42) before a claim can be checked against the topology as it stood at onset.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, get_args

from opspilot.diagnosis.contracts import CausalClaim, OnsetWindow, ReportClaim

if TYPE_CHECKING:
    from opspilot.llm.schema import CausalClaimResponse, ReportClaimResponse

# The Literal members, read off the contract so the two can never drift apart.
_CAUSE_TYPES: frozenset[str] = frozenset(
    get_args(CausalClaim.model_fields["cause_type"].annotation)
)
_CLAIM_KINDS: frozenset[str] = frozenset(get_args(ReportClaim.model_fields["kind"].annotation))


def entities_from_refs(refs: set[str]) -> set[str]:
    """Service names carried by the frozen evidence-ref grammar.

    `logs:<svc>:<id>`, `metrics:<svc>:<metric>@<ts>` and `deploys:<svc>:<id>` name one service in
    the second field; `deps:<from>-><to>` names two. Refs with no service (`runbook:<id>`,
    `past_incident:<id>`) contribute nothing, which is correct: a runbook cannot be a cause entity.
    """
    found: set[str] = set()
    for ref in refs:
        head, _, rest = ref.partition(":")
        if not rest:
            continue
        if head == "deps":
            left, arrow, right = rest.partition("->")
            if arrow:
                found.update({left.strip(), right.strip()} - {""})
        elif head in ("logs", "metrics", "deploys"):
            service = rest.split(":", 1)[0].split("@", 1)[0].strip()
            if service:
                found.add(service)
    return found


def admit_causal_claim(
    proposed: CausalClaimResponse | None,
    *,
    produced_refs: set[str],
    known_entities: set[str],
    fallback_onset: str = "",
) -> CausalClaim | None:
    """Admit a proposed claim into the strict contract, or return None.

    Refused when: nothing was proposed; the named entity is empty or resolves against no entity
    this run touched; or no proposed support ref was actually produced. An unrecognized
    `cause_type` degrades to the contract's own `"unknown"` member rather than failing the whole
    claim, because "we could not classify the mechanism" is honest and still carries grounded
    refs, whereas an unresolvable entity means the claim is about nothing.
    """
    if proposed is None:
        return None

    entity = proposed.cause_entity.strip()
    if not entity or entity not in known_entities:
        return None

    support = [ref for ref in proposed.support_refs if ref in produced_refs]
    if not support:
        return None

    cause_type = proposed.cause_type.strip()
    return CausalClaim(
        cause_type=cause_type if cause_type in _CAUSE_TYPES else "unknown",  # type: ignore[arg-type]
        cause_entity=entity,
        # An event ref the tools never produced is dropped rather than carried: the causal-order
        # check at 6b compares this ref's timestamp, and a ref with no evidence behind it has none.
        cause_event_ref=(
            proposed.cause_event_ref if proposed.cause_event_ref in produced_refs else ""
        ),
        onset_window=OnsetWindow(
            start=proposed.onset_start.strip() or fallback_onset,
            end=proposed.onset_end.strip(),
        ),
        affected_entities=[e for e in proposed.affected_entities if e in known_entities],
        support_refs=support,
        counter_refs=[ref for ref in proposed.counter_refs if ref in produced_refs],
    )


def admit_report_claims(
    proposed: list[ReportClaimResponse],
    *,
    produced_refs: set[str],
) -> list[ReportClaim]:
    """Admit the secondary report-level claims (G-51), dropping any that cannot be grounded.

    Every published claim must cite produced evidence, not just the headline root cause, so a
    claim whose refs were never produced is dropped rather than published uncited. `recommendation`
    is the one kind allowed to stand on runbook/past-incident refs, which the ref filter already
    permits because those are produced by the retrieval tools.
    """
    admitted: list[ReportClaim] = []
    for claim in proposed:
        kind = claim.kind.strip()
        if kind not in _CLAIM_KINDS:
            continue
        support = [ref for ref in claim.support_refs if ref in produced_refs]
        if not support:
            continue
        admitted.append(
            ReportClaim(kind=kind, statement=claim.statement.strip(), support_refs=support)  # type: ignore[arg-type]
        )
    return admitted
