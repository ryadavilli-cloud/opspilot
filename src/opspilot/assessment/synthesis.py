"""Synthesis: the model proposes an assessment, code admits it.

The model interprets what the evidence means. It does not decide what counts as evidence, what may
be presented as established, or whether a conclusion may be stated. Those are decided here, against
the admitted evidence set, because a check performed over a model-controlled input is deterministic
in form only.

The proposal arrives as loose strings, because a model cannot be trusted to satisfy a closed
vocabulary or to name a reference that exists. Admission converts it into the strict assessment
contract or refuses the parts it cannot ground:

- a reference the turn never admitted is dropped, never cited;
- a candidate left with no admitted support is dropped entirely, because a candidate about nothing
  is not an explanation;
- the leading candidate is established only when admitted evidence supports it, and the conclusion
  disposition follows from that rather than from anything the model asserted about its own
  certainty.

Refusal is the point. Degrading to "the evidence does not support a conclusion" is honest;
publishing a typed structure nothing verified is not.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from opspilot.assessment.contracts import (
    Assessment,
    CandidateCause,
    Citation,
    ConclusionDisposition,
    GroundedElement,
    Horizon,
    Recommendation,
    RecommendationKind,
    RecommendationProvenance,
    Strength,
    SupportLabel,
)
from opspilot.evidence.admission import AdmittedObservation, Limitation
from opspilot.evidence.references import CitationRole, try_parse

SYNTHESIS_TASK = "rca_synthesis"

_HORIZONS = {h.value: h for h in Horizon}
_KINDS = {k.value: k for k in RecommendationKind}


class CandidateProposal(BaseModel):
    """A candidate as the model offers it: prose plus reference strings that may or may not name
    anything this turn admitted."""

    statement: str = ""
    supporting_refs: list[str] = Field(default_factory=list)
    weakening_refs: list[str] = Field(default_factory=list)


class RecommendationProposal(BaseModel):
    action: str = ""
    horizon: str = ""
    kind: str = ""
    responds_to: str = ""
    confirm_signal: str = ""


class AssessmentProposal(BaseModel):
    """The structured shape the model is asked for. Every field is optional and defaulted, so a
    model that omits one produces a thinner assessment rather than a parse failure that would lose
    the whole turn."""

    what_happened: str = ""
    what_happened_refs: list[str] = Field(default_factory=list)
    leading: CandidateProposal | None = None
    alternatives: list[CandidateProposal] = Field(default_factory=list)
    unresolved_discriminator: str = ""
    recommendations: list[RecommendationProposal] = Field(default_factory=list)


def parse_proposal(text: str) -> AssessmentProposal:
    """Read the model's JSON, tolerating the fencing and prose models wrap it in.

    A response that cannot be read at all yields an empty proposal rather than an exception: the
    turn then degrades to an assessment that states it established nothing, which is a truthful
    result, where a raised exception would lose the evidence the turn did gather.
    """
    cleaned = text.strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        return AssessmentProposal()
    try:
        return AssessmentProposal.model_validate(json.loads(cleaned[start : end + 1]))
    except Exception:  # noqa: BLE001 - an unreadable proposal is a thin assessment, not a crash
        return AssessmentProposal()


def _admitted_refs(observations: list[AdmittedObservation]) -> set[str]:
    return {obs.evidence_ref for obs in observations}


def _grounded(refs: list[str], admitted: set[str]) -> list[str]:
    """Keep only references this turn actually admitted, preserving the model's order."""
    seen: set[str] = set()
    kept: list[str] = []
    for ref in refs:
        if ref in admitted and ref not in seen:
            seen.add(ref)
            kept.append(ref)
    return kept


def _candidate(
    proposal: CandidateProposal, admitted: set[str], label: SupportLabel
) -> CandidateCause | None:
    statement = proposal.statement.strip()
    if not statement:
        return None
    supporting = _grounded(proposal.supporting_refs, admitted)
    if not supporting:
        # A candidate resting on nothing this turn observed is not an explanation of it.
        return None
    strength = (
        Strength.ESTABLISHED if label is SupportLabel.LEADING and supporting else Strength.POSSIBLE
    )
    return CandidateCause(
        statement=statement,
        label=label,
        strength=strength,
        supporting=supporting,
        weakening=_grounded(proposal.weakening_refs, admitted),
    )


def _recommendation(proposal: RecommendationProposal) -> Recommendation | None:
    action = proposal.action.strip()
    if not action:
        return None
    kind = _KINDS.get(proposal.kind.strip().lower(), RecommendationKind.VERIFICATION)
    confirm = proposal.confirm_signal.strip()
    if kind is RecommendationKind.MITIGATION and not confirm:
        # A mitigation must say what would show it worked. Without one it is a verification step.
        kind = RecommendationKind.VERIFICATION
    return Recommendation(
        action=action,
        horizon=_HORIZONS.get(proposal.horizon.strip().lower(), Horizon.SOON),
        kind=kind,
        responds_to=proposal.responds_to.strip() or "the leading candidate",
        # No retrieval runs in this path, so nothing the model says can be attributed to a runbook
        # or a prior incident. Labelling it model-generated is the honest form, and the contract
        # refuses a reference alongside it.
        provenance=RecommendationProvenance.GENERAL_PRACTICE,
        confirm_signal=confirm or None,
    )


def admit_assessment(
    proposal: AssessmentProposal,
    *,
    investigation_id: str,
    turn_id: str,
    objective: str,
    observations: list[AdmittedObservation],
    limitations: list[Limitation],
) -> Assessment:
    """Convert a proposal into the assessment contract, grounded in what this turn admitted."""
    admitted = _admitted_refs(observations)

    happened_refs = _grounded(proposal.what_happened_refs, admitted)
    happened_text = proposal.what_happened.strip() or "The reported condition was investigated."
    what_happened = GroundedElement(
        statement=happened_text,
        # Established only where current operational support exists for it.
        strength=Strength.ESTABLISHED if happened_refs else Strength.POSSIBLE,
        citations=[
            Citation(reference=ref, role=CitationRole.CURRENT_SUPPORT)
            for ref in happened_refs
            if try_parse(ref) is not None
        ],
    )

    leading = (
        _candidate(proposal.leading, admitted, SupportLabel.LEADING) if proposal.leading else None
    )
    alternatives = [
        candidate
        for candidate in (
            _candidate(alternative, admitted, SupportLabel.PLAUSIBLE)
            for alternative in proposal.alternatives
        )
        if candidate is not None
    ]

    disposition = (
        ConclusionDisposition.SUPPORTED_CONCLUSION
        if leading is not None and leading.strength is Strength.ESTABLISHED
        else ConclusionDisposition.INSUFFICIENT_EVIDENCE
    )

    recommendations = [
        rec
        for rec in (_recommendation(proposal) for proposal in proposal.recommendations)
        if rec is not None
    ]

    return Assessment(
        investigation_id=investigation_id,
        turn_id=turn_id,
        turn_objective=objective,
        what_happened=what_happened,
        disposition=disposition,
        leading_candidate=leading,
        supported_alternatives=alternatives,
        unresolved_discriminator=proposal.unresolved_discriminator.strip() or None,
        limitations=list(limitations),
        recommendations=recommendations,
    )
