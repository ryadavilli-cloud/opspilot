"""The assessment contracts.

Field-by-field coverage is assumed. What these assert are the places where an assessment could
claim more than its evidence supports and still look well formed: an alternative promoted to fact,
a recommendation whose provenance and reference disagree, a document standing in as current proof,
and any number acting as confidence.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from opspilot.assessment.contracts import (
    BRIEF_SECTIONS,
    Assessment,
    Brief,
    BriefSection,
    CandidateCause,
    Citation,
    ConclusionDisposition,
    GroundedElement,
    HistoricalComparison,
    Horizon,
    Recommendation,
    RecommendationKind,
    RecommendationProvenance,
    Strength,
    SupportLabel,
)
from opspilot.evidence.references import CitationRole

EVIDENCE = "metrics:redis-cache:used_memory_pct@2026-06-22T11:35:00Z"
LOG = "logs:checkout-api:evt-005-01"
KNOWLEDGE = "runbook:redis-cache-degradation"

SUPPORT = Citation(reference=EVIDENCE, role=CitationRole.CURRENT_SUPPORT)


def _happened(strength: Strength = Strength.ESTABLISHED) -> GroundedElement:
    return GroundedElement(
        statement="checkout latency rose while the cache evicted keys",
        strength=strength,
        citations=[SUPPORT] if strength is Strength.ESTABLISHED else [],
    )


def _leading(strength: Strength = Strength.ESTABLISHED) -> CandidateCause:
    return CandidateCause(
        statement="redis-cache reached its memory ceiling and evicted session keys",
        label=SupportLabel.LEADING,
        strength=strength,
        supporting=[EVIDENCE, LOG],
    )


def _assessment(**kw) -> Assessment:
    base = dict(
        investigation_id="inv-1",
        turn_id="turn-1",
        turn_objective="explain the checkout latency rise",
        what_happened=_happened(),
        disposition=ConclusionDisposition.SUPPORTED_CONCLUSION,
        leading_candidate=_leading(),
    )
    base.update(kw)
    return Assessment(**base)


# --- strength rules -----------------------------------------------------------------------------
def test_an_established_element_needs_current_operational_support():
    """Established means the brief presents it as current fact, so something must currently
    support it. Marking it established with only historical citations is the quiet version of
    asserting a fact from a document."""
    with pytest.raises(ValidationError):
        GroundedElement(
            statement="the cache was evicting",
            strength=Strength.ESTABLISHED,
            citations=[Citation(reference=KNOWLEDGE, role=CitationRole.HISTORICAL_CONTEXT)],
        )


def test_a_possible_element_needs_no_support():
    assert (
        GroundedElement(statement="something degraded", strength=Strength.POSSIBLE).citations == []
    )


def test_a_supported_alternative_can_never_be_established():
    """An alternative is by definition one the evidence keeps open. Establishing it would make two
    competing conclusions, which the design refuses."""
    alternative = CandidateCause(
        statement="a downstream dependency degraded independently",
        label=SupportLabel.PLAUSIBLE,
        strength=Strength.ESTABLISHED,
        supporting=[LOG],
    )
    with pytest.raises(ValidationError, match="always possible"):
        _assessment(supported_alternatives=[alternative])


def test_a_historical_comparison_can_never_be_established():
    """History cannot establish a fact about the current incident."""
    with pytest.raises(ValidationError, match="always possible"):
        HistoricalComparison(
            statement="this resembles an earlier incident", strength=Strength.ESTABLISHED
        )


# --- one conclusion, not several ------------------------------------------------------------------
def test_only_one_candidate_may_be_leading():
    other = CandidateCause(statement="another cause", label=SupportLabel.LEADING, supporting=[LOG])
    with pytest.raises(ValidationError, match="only one candidate may be leading"):
        _assessment(supported_alternatives=[other])


def test_the_leading_candidate_must_carry_the_leading_label():
    with pytest.raises(ValidationError, match="leading label"):
        _assessment(
            leading_candidate=CandidateCause(
                statement="c", label=SupportLabel.PLAUSIBLE, supporting=[LOG]
            )
        )


def test_a_supported_conclusion_requires_an_established_leading_candidate():
    """Insufficiency cannot be converted into a conclusion by asserting one. If the candidate is
    only possible, the disposition must say the evidence does not support stating it."""
    with pytest.raises(ValidationError, match="established"):
        _assessment(leading_candidate=_leading(Strength.POSSIBLE))


def test_insufficient_evidence_is_a_legitimate_assessment():
    """Not a failure. It may establish the effect and still decline to name a cause."""
    assessment = _assessment(
        disposition=ConclusionDisposition.INSUFFICIENT_EVIDENCE,
        leading_candidate=None,
        unresolved_discriminator="whether the eviction preceded the latency rise",
    )
    assert assessment.leading_candidate is None
    assert assessment.unresolved_discriminator


# --- reference type rules -------------------------------------------------------------------------
@pytest.mark.parametrize("role", [CitationRole.CURRENT_SUPPORT, CitationRole.CURRENT_CONTRADICTION])
def test_knowledge_cannot_be_cited_as_current_proof(role):
    """A document cannot observe the running system."""
    with pytest.raises(ValidationError, match="cannot occupy"):
        Citation(reference=KNOWLEDGE, role=role)


def test_knowledge_may_be_cited_as_historical_context():
    assert (
        Citation(reference=KNOWLEDGE, role=CitationRole.HISTORICAL_CONTEXT).reference == KNOWLEDGE
    )


def test_candidate_support_must_be_evidence_not_knowledge():
    with pytest.raises(ValidationError, match="must be evidence"):
        CandidateCause(statement="c", label=SupportLabel.LEADING, supporting=[KNOWLEDGE])


def test_relevant_knowledge_must_be_knowledge_references():
    with pytest.raises(ValidationError, match="must be knowledge"):
        _assessment(relevant_knowledge=[EVIDENCE])


def test_a_malformed_reference_is_refused_rather_than_stored():
    with pytest.raises(ValidationError):
        Citation(reference="past_incident:inc-001", role=CitationRole.HISTORICAL_CONTEXT)


# --- recommendation provenance --------------------------------------------------------------------
@pytest.mark.parametrize(
    "provenance",
    [RecommendationProvenance.RUNBOOK_GUIDANCE, RecommendationProvenance.PRIOR_INCIDENT_ACTION],
)
def test_sourced_provenance_must_carry_its_knowledge_reference(provenance):
    with pytest.raises(ValidationError, match="knowledge reference"):
        Recommendation(
            action="raise the cache memory limit",
            horizon=Horizon.SOON,
            kind=RecommendationKind.PREVENTION,
            responds_to="the leading candidate",
            provenance=provenance,
        )


def test_general_practice_must_not_carry_a_reference():
    """Presenting a sensible idea as though a runbook backed it is the dishonest form. Saying it is
    model-generated is the honest one."""
    with pytest.raises(ValidationError, match="carries no reference"):
        Recommendation(
            action="raise the cache memory limit",
            horizon=Horizon.SOON,
            kind=RecommendationKind.PREVENTION,
            responds_to="the leading candidate",
            provenance=RecommendationProvenance.GENERAL_PRACTICE,
            knowledge_reference=KNOWLEDGE,
        )


def test_a_provenance_reference_cannot_be_an_evidence_reference():
    with pytest.raises(ValidationError, match="must be knowledge"):
        Recommendation(
            action="a",
            horizon=Horizon.NOW,
            kind=RecommendationKind.VERIFICATION,
            responds_to="r",
            provenance=RecommendationProvenance.RUNBOOK_GUIDANCE,
            knowledge_reference=EVIDENCE,
        )


def test_a_mitigation_must_state_how_to_confirm_it_worked():
    with pytest.raises(ValidationError, match="confirm"):
        Recommendation(
            action="flush and resize the cache",
            horizon=Horizon.NOW,
            kind=RecommendationKind.MITIGATION,
            responds_to="the leading candidate",
            provenance=RecommendationProvenance.GENERAL_PRACTICE,
        )


def test_a_well_formed_general_practice_mitigation_is_accepted():
    rec = Recommendation(
        action="raise the cache memory ceiling",
        horizon=Horizon.NOW,
        kind=RecommendationKind.MITIGATION,
        responds_to="the leading candidate",
        provenance=RecommendationProvenance.GENERAL_PRACTICE,
        confirm_signal="eviction rate returns to zero and hit rate recovers",
    )
    assert rec.knowledge_reference is None


# --- no numeric confidence, anywhere -------------------------------------------------------------
def _numeric_fields(model: type[BaseModel]) -> list[str]:
    found: list[str] = []
    for name, field in model.model_fields.items():
        annotation = str(field.annotation)
        if "float" in annotation or "Decimal" in annotation:
            found.append(f"{model.__name__}.{name}")
    return found


@pytest.mark.parametrize(
    "model",
    [
        Assessment,
        CandidateCause,
        GroundedElement,
        HistoricalComparison,
        Citation,
        Recommendation,
        Brief,
        BriefSection,
    ],
)
def test_no_contract_carries_a_number_that_could_act_as_confidence(model):
    """Model confidence is not a form of support. A float on any of these would become one the
    moment something sorted or thresholded on it."""
    assert _numeric_fields(model) == []


def test_support_is_expressed_only_by_the_three_labels():
    assert [label.value for label in SupportLabel] == ["leading", "plausible", "weakly_supported"]


# --- brief shape ---------------------------------------------------------------------------------
def test_the_brief_has_exactly_the_eight_accepted_sections():
    assert len(BRIEF_SECTIONS) == 8
    assert BRIEF_SECTIONS[0] == "current_conclusion_and_next_action"


def test_brief_sections_keep_their_order():
    """Reordering is not presentation. A brief that leads with history instead of the conclusion
    asserts a different emphasis than the assessment holds."""
    with pytest.raises(ValidationError, match="order"):
        Brief(
            investigation_id="inv-1",
            turn_id="turn-1",
            sections=[
                BriefSection(name="what_happened"),
                BriefSection(name="current_conclusion_and_next_action"),
            ],
        )


def test_a_brief_holds_each_section_at_most_once():
    with pytest.raises(ValidationError, match="at most once"):
        Brief(
            investigation_id="inv-1",
            turn_id="turn-1",
            sections=[BriefSection(name="what_happened"), BriefSection(name="what_happened")],
        )


def test_an_unknown_brief_section_is_refused():
    with pytest.raises(ValidationError, match="unknown brief section"):
        BriefSection(name="executive_summary")


def test_omitting_an_empty_section_is_allowed():
    """Omitting a section the assessment left empty is presentation; removing content it holds is
    not, and that second rule belongs to the projection rather than to this shape."""
    brief = Brief(
        investigation_id="inv-1",
        turn_id="turn-1",
        sections=[BriefSection(name="what_happened", body="x")],
    )
    assert len(brief.sections) == 1


# --- the first scenario's shape ------------------------------------------------------------------
def test_the_first_scenario_shape_is_representable():
    """inc-005 has one cause, no acceptable alternatives, and no weakening evidence. The contract
    must express that without requiring empty structures to be invented."""
    assessment = _assessment(
        recommendations=[
            Recommendation(
                action="raise the cache memory ceiling",
                horizon=Horizon.NOW,
                kind=RecommendationKind.MITIGATION,
                responds_to="the leading candidate",
                provenance=RecommendationProvenance.GENERAL_PRACTICE,
                confirm_signal="eviction rate returns to zero",
            )
        ],
    )
    assert assessment.supported_alternatives == []
    assert assessment.leading_candidate is not None
    assert assessment.leading_candidate.weakening == []
    assert assessment.disposition is ConclusionDisposition.SUPPORTED_CONCLUSION


def test_an_assessment_is_frozen():
    assessment = _assessment()
    with pytest.raises(ValidationError):
        assessment.turn_objective = "something else"  # type: ignore[misc]
