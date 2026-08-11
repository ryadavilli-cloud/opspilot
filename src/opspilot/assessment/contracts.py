"""The assessment: one authoritative structured synthesis per turn, and the brief's shape.

Grounding attaches to elements, not to sentences. A grounded element carries its own citations and,
where it can be asserted at more than one strength, a marker separating what the brief may present
as current fact from what it must present as open. The rules that decide which is which are
enforced here rather than left to the renderer, because a rendering defect and a grounding failure
are different things and only one of them is the brief's fault.

Three constraints are structural and are worth naming, since each is a way an assessment could
quietly claim more than its evidence supports:

- Only an element marked established requires current operational support. An alternative and a
  historical comparison are always possible and cannot be constructed as established at all.
- A recommendation's provenance and its reference are checkable together: runbook guidance and a
  prior-incident action each carry a knowledge reference, and general operational practice carries
  none and says so.
- No numeric confidence exists anywhere. Model confidence is not a form of support and carries no
  weight in whether a conclusion may be stated.

What this module does not define: the completed-outcome vocabulary. Whether a turn ends complete,
partial, or inconclusive follows from the grounding gate, which does not exist yet. The conclusion
disposition below is a different question, about whether the evidence supports stating a cause at
all, and it belongs to the assessment.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from opspilot.evidence.admission import Limitation
from opspilot.evidence.references import (
    CitationRole,
    ReferenceType,
    parse,
    role_is_admissible,
)


class SupportLabel(StrEnum):
    """Exactly three. A candidate carries one, and no number stands beside it."""

    LEADING = "leading"
    PLAUSIBLE = "plausible"
    WEAKLY_SUPPORTED = "weakly_supported"


class SupportRelationship(StrEnum):
    """How a reference relates to a candidate. Carries no weight and forms no scored graph."""

    SUPPORTS = "supports"
    WEAKENS = "weakens_or_contradicts"
    CONTEXTUAL = "contextual_only"


class Strength(StrEnum):
    """Established is presented as current fact; possible is presented as open."""

    ESTABLISHED = "established"
    POSSIBLE = "possible"


class Horizon(StrEnum):
    NOW = "now"
    SOON = "soon"
    LATER = "later"


class RecommendationKind(StrEnum):
    MITIGATION = "mitigation"
    VERIFICATION = "verification"
    PREVENTION = "prevention"


class RecommendationProvenance(StrEnum):
    """A field of the recommendation, not a citation role."""

    RUNBOOK_GUIDANCE = "retrieved_runbook_guidance"
    PRIOR_INCIDENT_ACTION = "prior_incident_action"
    GENERAL_PRACTICE = "general_operational_practice"


class ConclusionDisposition(StrEnum):
    """Whether the evidence supports stating a cause. Not the terminal outcome shape, which is a
    consequence of the grounding gate and is not this contract's to name."""

    SUPPORTED_CONCLUSION = "supported_causal_conclusion"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


_PROVENANCE_NEEDS_REFERENCE = frozenset(
    {RecommendationProvenance.RUNBOOK_GUIDANCE, RecommendationProvenance.PRIOR_INCIDENT_ACTION}
)


class Citation(BaseModel):
    """One reference, the role it plays, and nothing else. The role a source cannot support is
    inadmissible, and the reference type alone decides that."""

    model_config = ConfigDict(frozen=True)

    reference: str
    role: CitationRole

    @model_validator(mode="after")
    def _role_matches_reference_type(self) -> Citation:
        parsed = parse(self.reference)
        if not role_is_admissible(parsed.reference_type, self.role):
            raise ValueError(
                f"a {parsed.reference_type} reference cannot occupy the {self.role} role"
            )
        return self


class GroundedElement(BaseModel):
    """A statement carrying its own citations and, where it can be asserted at more than one
    strength, its marker. An established element must rest on current operational support."""

    model_config = ConfigDict(frozen=True)

    statement: str = Field(min_length=1)
    strength: Strength
    citations: list[Citation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _established_needs_current_support(self) -> GroundedElement:
        if self.strength is Strength.ESTABLISHED and not any(
            c.role is CitationRole.CURRENT_SUPPORT for c in self.citations
        ):
            raise ValueError(
                "an established element requires at least one current-operational-support citation"
            )
        return self


class HistoricalComparison(BaseModel):
    """How this incident relates to prior occurrences. Always possible: history cannot establish a
    fact about the current incident, so this element has no strength to choose."""

    model_config = ConfigDict(frozen=True)

    statement: str = Field(min_length=1)
    citations: list[Citation] = Field(default_factory=list)
    strength: Strength = Strength.POSSIBLE

    @model_validator(mode="after")
    def _never_established(self) -> HistoricalComparison:
        if self.strength is not Strength.POSSIBLE:
            raise ValueError("a historical comparison is always possible, never established")
        return self


class CandidateCause(BaseModel):
    """One explanation, its label, and the references that bear on it in each direction.

    Contradicting evidence is attached to the candidate it bears on rather than dropped to make the
    assessment read cleanly. A candidate that survives only on thin support says so through its
    label, never through a lowered number.
    """

    model_config = ConfigDict(frozen=True)

    statement: str = Field(min_length=1)
    label: SupportLabel
    strength: Strength = Strength.POSSIBLE
    supporting: list[str] = Field(default_factory=list)
    weakening: list[str] = Field(default_factory=list)
    contextual: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _established_needs_support(self) -> CandidateCause:
        if self.strength is Strength.ESTABLISHED and not self.supporting:
            raise ValueError("an established candidate requires supporting evidence")
        for ref in self.supporting + self.weakening:
            if parse(ref).reference_type is not ReferenceType.EVIDENCE:
                raise ValueError(
                    "supporting and weakening references must be evidence, not knowledge"
                )
        return self

    def references(self, relationship: SupportRelationship) -> list[str]:
        if relationship is SupportRelationship.SUPPORTS:
            return list(self.supporting)
        if relationship is SupportRelationship.WEAKENS:
            return list(self.weakening)
        return list(self.contextual)


class Recommendation(BaseModel):
    """An advisory action. Nothing executes one, and none implies an operational write."""

    model_config = ConfigDict(frozen=True)

    action: str = Field(min_length=1)
    horizon: Horizon
    kind: RecommendationKind
    responds_to: str = Field(min_length=1)
    provenance: RecommendationProvenance
    knowledge_reference: str | None = None
    confirm_signal: str | None = None

    @model_validator(mode="after")
    def _provenance_and_reference_agree(self) -> Recommendation:
        needs = self.provenance in _PROVENANCE_NEEDS_REFERENCE
        if needs and not self.knowledge_reference:
            raise ValueError(f"{self.provenance} must carry a knowledge reference")
        if not needs and self.knowledge_reference:
            raise ValueError(
                "general operational practice carries no reference; labelling it as model-generated"
                " is the honest form"
            )
        if self.knowledge_reference:
            parsed = parse(self.knowledge_reference)
            if parsed.reference_type is not ReferenceType.KNOWLEDGE:
                raise ValueError("a recommendation's provenance reference must be knowledge")
        if self.kind is RecommendationKind.MITIGATION and not self.confirm_signal:
            raise ValueError("a mitigation must state what should be observed to confirm it worked")
        return self


class Assessment(BaseModel):
    """Exactly one per turn. No other component produces a competing one.

    Ranking candidates does not create several conclusions: where the evidence supports one, it is
    the leading candidate presented as such.
    """

    model_config = ConfigDict(frozen=True)

    investigation_id: str
    turn_id: str
    turn_objective: str = Field(min_length=1)
    what_happened: GroundedElement
    disposition: ConclusionDisposition
    leading_candidate: CandidateCause | None = None
    supported_alternatives: list[CandidateCause] = Field(default_factory=list)
    unresolved_discriminator: str | None = None
    relevant_knowledge: list[str] = Field(default_factory=list)
    historical_comparison: HistoricalComparison | None = None
    limitations: list[Limitation] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_leading_and_disposition_agrees(self) -> Assessment:
        if self.leading_candidate is not None:
            if self.leading_candidate.label is not SupportLabel.LEADING:
                raise ValueError("the leading candidate must carry the leading label")
        for alternative in self.supported_alternatives:
            if alternative.label is SupportLabel.LEADING:
                raise ValueError("only one candidate may be leading")
            if alternative.strength is not Strength.POSSIBLE:
                raise ValueError("a supported alternative is always possible, never established")

        supported = self.disposition is ConclusionDisposition.SUPPORTED_CONCLUSION
        if supported and self.leading_candidate is None:
            raise ValueError("a supported conclusion requires a leading candidate")
        if supported and self.leading_candidate is not None:
            if self.leading_candidate.strength is not Strength.ESTABLISHED:
                raise ValueError(
                    "a supported conclusion requires the leading candidate to be established"
                )
        for ref in self.relevant_knowledge:
            if parse(ref).reference_type is not ReferenceType.KNOWLEDGE:
                raise ValueError("relevant retrieved knowledge must be knowledge references")
        return self


# The brief's logical sections, in the order a reader needs them. Sections of one brief, not eight
# separately persisted objects. The projection that fills them is deterministic and renders only
# what the assessment holds.
BRIEF_SECTIONS: tuple[str, ...] = (
    "current_conclusion_and_next_action",
    "what_happened",
    "what_may_be_causing_it",
    "supporting_and_weakening_evidence",
    "what_remains_unknown",
    "what_history_says",
    "what_to_do",
    "sources_limitations_and_diagnostics",
)


class BriefSection(BaseModel):
    """One rendered section. Omitting a section the assessment left empty is presentation; removing
    content the assessment holds is not."""

    model_config = ConfigDict(frozen=True)

    name: str
    body: str = ""
    citations: list[Citation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _name_is_a_known_section(self) -> BriefSection:
        if self.name not in BRIEF_SECTIONS:
            raise ValueError(f"unknown brief section {self.name!r}")
        return self


class Brief(BaseModel):
    """The user-facing rendering of one assessment. A rendering, not a second analysis: it cannot
    introduce a candidate, relationship, recommendation, or conclusion the assessment does not
    hold, and it may not drop one either."""

    model_config = ConfigDict(frozen=True)

    investigation_id: str
    turn_id: str
    sections: list[BriefSection] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sections_keep_their_order(self) -> Brief:
        order = [BRIEF_SECTIONS.index(s.name) for s in self.sections]
        if order != sorted(order):
            raise ValueError("brief sections must keep their defined order")
        if len(order) != len(set(order)):
            raise ValueError("a brief holds each section at most once")
        return self
