"""The grounding gate: its result contracts, the four checks, and the correction routing.

Three of the four checks (unsupported-element rejection, recommendation-provenance presence, and
half of reference resolution) can never fail against a normally-constructed `Assessment`, because
the contract's own validators already make the violation unconstructable. That is intentional
defense in depth, not dead code: the gate re-verifies independently rather than trusting the object
that produced it (`code-guidelines.md` §3). Reaching those checks' failure branches in a test
therefore requires `model_construct()` at both the nested field and the `Assessment` itself:
embedding an already-built, deliberately invalid nested model into a normally-constructed
`Assessment` still re-runs that nested model's own validators, so `_unvalidated_assessment` below
bypasses both levels. The tests below say so at each use so a reader does not mistake it for an
accident. Reference resolution's admission-membership half, and required limitation disclosure,
need no such trick: both compare the assessment against turn-scoped state the assessment's own
validators have no view of, so a normally-constructed assessment can genuinely fail either one.
"""

from __future__ import annotations

import pytest

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
from opspilot.evidence.admission import Limitation
from opspilot.evidence.references import CitationRole
from opspilot.grounding.checks import (
    CorrectionAllowance,
    GateRouting,
    check_recommendation_provenance_presence,
    check_reference_resolution,
    check_required_limitation_disclosure,
    check_unsupported_element_rejection,
    route_grounding_result,
    run_gate,
    unresolved_references,
)
from opspilot.grounding.contracts import CheckName, CheckResult, GroundingResult
from opspilot.tools.contracts import ExecutionOutcome

LOG = "logs:checkout-api:evt-1"
DEPLOY = "deploys:checkout-api:d-1"


_ASSESSMENT_DEFAULTS: dict[str, object] = dict(
    investigation_id="inv-1",
    turn_id="turn-1",
    turn_objective="explain the checkout latency rise",
    what_happened=GroundedElement(statement="under investigation", strength=Strength.POSSIBLE),
    disposition=ConclusionDisposition.INSUFFICIENT_EVIDENCE,
)


def _assessment(**overrides: object) -> Assessment:
    """A minimal valid turn: nothing established, nothing cited. Every test overrides only the
    field its check inspects, so a failure is traceable to that one field."""
    return Assessment(**{**_ASSESSMENT_DEFAULTS, **overrides})  # type: ignore[arg-type]


def _unvalidated_assessment(**overrides: object) -> Assessment:
    """Like `_assessment`, but via `model_construct()`: no validator on `Assessment` or any nested
    field runs, even for a field carrying an already-built, deliberately invalid nested model.
    Embedding a nested model instance in a normal `Assessment(...)` call still re-runs that nested
    model's own validators (proven empirically: `model_construct()` on the nested model alone is
    not enough), so reaching a check's failure branch for a violation the contract itself forbids
    requires bypassing validation at this, the outermost, level too."""
    return Assessment.model_construct(**{**_ASSESSMENT_DEFAULTS, **overrides})


def _limitation(question: str = "what did the change history show") -> Limitation:
    return Limitation(
        question=question,
        reason="the source could not be reached",
        operation_ref="op-1",
        capability="get_deployments",
        outcome=ExecutionOutcome.UNAVAILABLE,
    )


_ALL_PASSING = tuple(CheckResult(check=name, passed=True) for name in CheckName)


def _failing(
    passing: tuple[CheckResult, ...], check: CheckName, reason: str
) -> tuple[CheckResult, ...]:
    """`passing` with one check's verdict replaced by a named failure."""
    return tuple(
        CheckResult(check=check, passed=False, reason=reason) if result.check is check else result
        for result in passing
    )


# --- CheckResult -----------------------------------------------------------------------------
def test_a_passing_check_carries_no_reason():
    with pytest.raises(ValueError, match="no failure reason"):
        CheckResult(check=CheckName.REFERENCE_RESOLUTION, passed=True, reason="unused")


def test_a_failed_check_must_name_why():
    with pytest.raises(ValueError, match="must name why"):
        CheckResult(check=CheckName.REFERENCE_RESOLUTION, passed=False)


def test_a_failed_check_carries_its_reason():
    result = CheckResult(
        check=CheckName.UNSUPPORTED_ELEMENT_REJECTION, passed=False, reason="no current support"
    )
    assert result.reason == "no current support"


# --- GroundingResult: the fixed set of four ---------------------------------------------------
def test_exactly_four_checks_are_required():
    with pytest.raises(ValueError, match="exactly the four fixed checks"):
        GroundingResult(checks=_ALL_PASSING[:3])


def test_a_duplicate_check_is_rejected():
    duplicated = (_ALL_PASSING[0],) + _ALL_PASSING
    with pytest.raises(ValueError, match="each check once"):
        GroundingResult(checks=duplicated)


def test_an_unknown_check_cannot_stand_in_for_a_fixed_one():
    # Four results, but one repeated in place of a required check: still not the fixed set.
    substituted = _ALL_PASSING[:3] + (_ALL_PASSING[0],)
    with pytest.raises(ValueError, match="exactly the four fixed checks"):
        GroundingResult(checks=substituted)


def test_all_four_passing_is_a_passing_result():
    result = GroundingResult(checks=_ALL_PASSING)
    assert result.passed is True
    assert result.failures == ()


def test_one_failure_fails_the_whole_result():
    checks = _failing(
        _ALL_PASSING, CheckName.RECOMMENDATION_PROVENANCE_PRESENCE, "no provenance category"
    )
    result = GroundingResult(checks=checks)

    assert result.passed is False
    assert [f.check for f in result.failures] == [CheckName.RECOMMENDATION_PROVENANCE_PRESENCE]


def test_failures_names_every_check_that_failed_not_just_the_first():
    checks = _failing(_ALL_PASSING, CheckName.REFERENCE_RESOLUTION, "unresolved")
    checks = _failing(checks, CheckName.REQUIRED_LIMITATION_DISCLOSURE, "limitation omitted")
    result = GroundingResult(checks=checks)

    assert {f.check for f in result.failures} == {
        CheckName.REFERENCE_RESOLUTION,
        CheckName.REQUIRED_LIMITATION_DISCLOSURE,
    }


# --- unresolved_references ---------------------------------------------------------------------
def test_unresolved_references_keeps_only_what_was_not_admitted():
    assert unresolved_references([LOG, DEPLOY], admitted={LOG}) == [DEPLOY]


def test_unresolved_references_is_empty_when_everything_was_admitted():
    assert unresolved_references([LOG, DEPLOY], admitted={LOG, DEPLOY}) == []


# --- check_reference_resolution: a real failure, no model_construct needed ----------------------
def test_reference_resolution_passes_when_every_citation_was_admitted():
    element = GroundedElement(
        statement="checkout latency rose",
        strength=Strength.ESTABLISHED,
        citations=[Citation(reference=LOG, role=CitationRole.CURRENT_SUPPORT)],
    )
    assessment = _assessment(what_happened=element)

    result = check_reference_resolution(assessment, admitted_refs={LOG})

    assert result.passed is True


def test_reference_resolution_fails_on_a_citation_this_turn_never_admitted():
    """A well-formed, role-compatible citation can still fail: admission is turn-scoped state the
    citation's own shape carries no view of."""
    element = GroundedElement(
        statement="checkout latency rose",
        strength=Strength.ESTABLISHED,
        citations=[Citation(reference=LOG, role=CitationRole.CURRENT_SUPPORT)],
    )
    assessment = _assessment(what_happened=element)

    result = check_reference_resolution(assessment, admitted_refs=set())

    assert result.passed is False
    assert LOG in result.reason


def test_reference_resolution_covers_candidate_support_and_relevant_knowledge():
    candidate = CandidateCause(
        statement="a bad deploy caused it",
        label=SupportLabel.LEADING,
        strength=Strength.ESTABLISHED,
        supporting=[DEPLOY],
    )
    assessment = _assessment(
        leading_candidate=candidate,
        disposition=ConclusionDisposition.SUPPORTED_CONCLUSION,
        relevant_knowledge=["runbook:checkout-timeout"],
    )

    result = check_reference_resolution(assessment, admitted_refs={DEPLOY})

    assert result.passed is False
    assert "runbook:checkout-timeout" in result.reason
    assert DEPLOY not in result.reason  # the admitted one is not reported as a violation


# --- check_unsupported_element_rejection: needs model_construct to reach the failure branch -----
def test_unsupported_element_rejection_passes_a_normally_constructed_assessment():
    element = GroundedElement(
        statement="checkout latency rose",
        strength=Strength.ESTABLISHED,
        citations=[Citation(reference=LOG, role=CitationRole.CURRENT_SUPPORT)],
    )
    assert check_unsupported_element_rejection(_assessment(what_happened=element)).passed is True


def test_unsupported_element_rejection_catches_an_established_what_happened_with_no_support():
    # GroundedElement's own validator refuses this on normal construction, and embedding an
    # already-built instance still re-runs it, so both levels must be constructed unvalidated for
    # the gate's independent check, not the contract, to be what the assertion below exercises.
    bad_element = GroundedElement.model_construct(
        statement="checkout latency rose", strength=Strength.ESTABLISHED, citations=[]
    )
    result = check_unsupported_element_rejection(_unvalidated_assessment(what_happened=bad_element))

    assert result.passed is False
    assert "what_happened" in result.reason


def test_unsupported_element_rejection_catches_an_established_candidate_with_no_support():
    # Same reasoning as above, for CandidateCause's own validator.
    bad_candidate = CandidateCause.model_construct(
        statement="a bad deploy caused it",
        label=SupportLabel.LEADING,
        strength=Strength.ESTABLISHED,
        supporting=[],
        weakening=[],
        contextual=[],
    )
    assessment = _unvalidated_assessment(leading_candidate=bad_candidate)

    result = check_unsupported_element_rejection(assessment)

    assert result.passed is False
    assert "a bad deploy caused it" in result.reason


# --- check_recommendation_provenance_presence: needs model_construct ----------------------------
def test_recommendation_provenance_presence_passes_a_normally_constructed_recommendation():
    recommendation = Recommendation(
        action="raise the cache memory ceiling",
        horizon=Horizon.NOW,
        kind=RecommendationKind.VERIFICATION,
        responds_to="the leading candidate",
        provenance=RecommendationProvenance.GENERAL_PRACTICE,
    )
    assessment = _assessment(recommendations=[recommendation])

    assert check_recommendation_provenance_presence(assessment).passed is True


def test_recommendation_provenance_presence_catches_a_claimed_provenance_with_no_reference():
    # Recommendation's own validator refuses this on normal construction, and embedding an
    # already-built instance still re-runs it, so the gate's independent check, not the contract,
    # is what the assertion below exercises.
    bad_recommendation = Recommendation.model_construct(
        action="raise the cache memory ceiling",
        horizon=Horizon.NOW,
        kind=RecommendationKind.VERIFICATION,
        responds_to="the leading candidate",
        provenance=RecommendationProvenance.RUNBOOK_GUIDANCE,
        knowledge_reference=None,
        confirm_signal=None,
    )
    assessment = _unvalidated_assessment(recommendations=[bad_recommendation])

    result = check_recommendation_provenance_presence(assessment)

    assert result.passed is False
    assert "raise the cache memory ceiling" in result.reason


# --- check_required_limitation_disclosure: a real failure, no model_construct needed -------------
def test_required_limitation_disclosure_passes_when_every_recorded_limitation_is_disclosed():
    limitation = _limitation()
    assessment = _assessment(limitations=[limitation])

    result = check_required_limitation_disclosure(assessment, turn_limitations=[limitation])

    assert result.passed is True


def test_required_limitation_disclosure_fails_on_a_recorded_limitation_the_assessment_dropped():
    recorded = _limitation("what did the change history show")
    assessment = _assessment(limitations=[])  # the assessment discloses nothing

    result = check_required_limitation_disclosure(assessment, turn_limitations=[recorded])

    assert result.passed is False
    assert "what did the change history show" in result.reason


def test_required_limitation_disclosure_allows_extra_disclosures_beyond_what_was_recorded():
    """Disclosing more than the turn recorded is not a violation; only an omission is."""
    extra = _limitation("an incompleteness disclosure the turn itself never recorded")
    assessment = _assessment(limitations=[extra])

    result = check_required_limitation_disclosure(assessment, turn_limitations=[])

    assert result.passed is True


# --- run_gate: all four together -----------------------------------------------------------------
def test_run_gate_passes_a_fully_grounded_assessment():
    element = GroundedElement(
        statement="checkout latency rose",
        strength=Strength.ESTABLISHED,
        citations=[Citation(reference=LOG, role=CitationRole.CURRENT_SUPPORT)],
    )
    limitation = _limitation()
    assessment = _assessment(what_happened=element, limitations=[limitation])

    result = run_gate(assessment, admitted_refs={LOG}, turn_limitations=[limitation])

    assert result.passed is True


def test_run_gate_fails_on_an_unadmitted_reference_alone():
    element = GroundedElement(
        statement="checkout latency rose",
        strength=Strength.ESTABLISHED,
        citations=[Citation(reference=LOG, role=CitationRole.CURRENT_SUPPORT)],
    )
    assessment = _assessment(what_happened=element)

    result = run_gate(assessment, admitted_refs=set())

    assert result.passed is False
    assert [f.check for f in result.failures] == [CheckName.REFERENCE_RESOLUTION]


# --- CorrectionAllowance and routing --------------------------------------------------------------
def test_the_allowance_starts_unspent():
    assert CorrectionAllowance().spent is False


def test_the_allowance_can_be_spent_once():
    allowance = CorrectionAllowance()
    assert allowance.spend() is True
    assert allowance.spent is True


def test_the_allowance_refuses_a_second_spend():
    """One shared allowance across both spend points: a structural spend leaves nothing for a
    later grounding failure, and the reverse."""
    allowance = CorrectionAllowance()
    allowance.spend()
    assert allowance.spend() is False
    assert allowance.spent is True


def test_a_passing_result_always_routes_to_passed_even_with_a_spent_allowance():
    allowance = CorrectionAllowance()
    allowance.spend()
    assert route_grounding_result(GroundingResult(checks=_ALL_PASSING), allowance) is (
        GateRouting.PASSED
    )


def test_a_failure_with_an_unspent_allowance_routes_to_correct_and_spends_it():
    allowance = CorrectionAllowance()
    failing = _failing(_ALL_PASSING, CheckName.REFERENCE_RESOLUTION, "unresolved")

    routing = route_grounding_result(GroundingResult(checks=failing), allowance)

    assert routing is GateRouting.CORRECT
    assert allowance.spent is True


def test_a_failure_with_an_already_spent_allowance_is_a_failed_execution():
    allowance = CorrectionAllowance()
    allowance.spend()  # spent on an earlier structural failure, in the real turn ordering
    failing = _failing(_ALL_PASSING, CheckName.REFERENCE_RESOLUTION, "unresolved")

    assert route_grounding_result(GroundingResult(checks=failing), allowance) is (
        GateRouting.FAILED_EXECUTION
    )
