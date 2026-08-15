"""The four grounding checks, the gate that runs them, and the shared correction allowance they
route through.

`data-and-evidence.md` §13 defines what each check inspects; `workflow-design.md` §7 defines when
the gate runs and how a failure routes. Each check is independently re-verified here rather than
trusted from the `Assessment` that carries it (`code-guidelines.md` §3: authority boundaries),
even where the contract already makes a violation unconstructable, such as an established element
with no current-support citation. Reference resolution is the one check most able to fail against
an otherwise-valid assessment: admission is turn-scoped state a reference's own shape carries no
view of, so membership has to be checked against the turn, not inferred from the reference.

Contract validity is settled before any of this runs, through structured model-output admission
(`assessment/synthesis.py`). A parse or contract failure never reaches these checks and is never
reported as one (`code-guidelines.md` §14).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from collections.abc import Set as AbstractSet
from enum import StrEnum

from opspilot.assessment.contracts import Assessment, Citation, RecommendationProvenance, Strength
from opspilot.evidence.admission import Limitation
from opspilot.evidence.references import CitationRole, role_is_admissible, try_parse
from opspilot.grounding.contracts import CheckName, CheckResult, GroundingResult

_PROVENANCE_NEEDS_REFERENCE = frozenset(
    {RecommendationProvenance.RUNBOOK_GUIDANCE, RecommendationProvenance.PRIOR_INCIDENT_ACTION}
)


def _typed_citations(assessment: Assessment) -> Iterator[Citation]:
    """Every reference carried as a role-bearing `Citation`, wherever one appears."""
    yield from assessment.what_happened.citations
    if assessment.historical_comparison is not None:
        yield from assessment.historical_comparison.citations


def _plain_references(assessment: Assessment) -> Iterator[str]:
    """Every reference cited without a formal role: candidate support, relevant knowledge, and a
    recommendation's provenance reference."""
    for candidate in assessment.candidates():
        yield from candidate.supporting
        yield from candidate.weakening
        yield from candidate.contextual
    yield from assessment.relevant_knowledge
    for recommendation in assessment.recommendations:
        if recommendation.knowledge_reference:
            yield recommendation.knowledge_reference


def unresolved_references(refs: Iterable[str], admitted: AbstractSet[str]) -> list[str]:
    """References that do not resolve to something this turn admitted, order preserved."""
    return [ref for ref in refs if ref not in admitted]


def check_reference_resolution(
    assessment: Assessment, admitted_refs: AbstractSet[str]
) -> CheckResult:
    """Every cited reference resolves to something the turn admitted, and carries a reference type
    compatible with the role it occupies."""
    violations: list[str] = []

    for citation in _typed_citations(assessment):
        parsed = try_parse(citation.reference)
        if parsed is not None and not role_is_admissible(parsed.reference_type, citation.role):
            violations.append(f"{citation.reference} cannot occupy the {citation.role} role")

    all_refs = [c.reference for c in _typed_citations(assessment)]
    all_refs.extend(_plain_references(assessment))
    violations.extend(
        f"{ref} was not admitted this turn"
        for ref in unresolved_references(all_refs, admitted_refs)
    )

    if violations:
        return CheckResult(
            check=CheckName.REFERENCE_RESOLUTION, passed=False, reason="; ".join(violations)
        )
    return CheckResult(check=CheckName.REFERENCE_RESOLUTION, passed=True)


def check_unsupported_element_rejection(assessment: Assessment) -> CheckResult:
    """Every grounded element marked established carries at least one current-operational-support
    reference. An alternative and a historical comparison are always possible, never established,
    so neither can violate this."""
    violations: list[str] = []

    element = assessment.what_happened
    if element.strength is Strength.ESTABLISHED and not any(
        citation.role is CitationRole.CURRENT_SUPPORT for citation in element.citations
    ):
        violations.append("what_happened is established with no current-support citation")

    for candidate in assessment.candidates():
        if candidate.strength is Strength.ESTABLISHED and not candidate.supporting:
            violations.append(f"{candidate.statement!r} is established with no supporting evidence")

    if violations:
        return CheckResult(
            check=CheckName.UNSUPPORTED_ELEMENT_REJECTION,
            passed=False,
            reason="; ".join(violations),
        )
    return CheckResult(check=CheckName.UNSUPPORTED_ELEMENT_REJECTION, passed=True)


def check_recommendation_provenance_presence(assessment: Assessment) -> CheckResult:
    """Every recommendation carries exactly one provenance category, and a knowledge reference
    where that category is runbook guidance or a prior-incident action."""
    violations: list[str] = []
    for recommendation in assessment.recommendations:
        needs_reference = recommendation.provenance in _PROVENANCE_NEEDS_REFERENCE
        if needs_reference and not recommendation.knowledge_reference:
            violations.append(
                f"{recommendation.action!r} claims {recommendation.provenance} with no reference"
            )
        if not needs_reference and recommendation.knowledge_reference:
            violations.append(
                f"{recommendation.action!r} carries a reference under {recommendation.provenance}"
            )

    if violations:
        return CheckResult(
            check=CheckName.RECOMMENDATION_PROVENANCE_PRESENCE,
            passed=False,
            reason="; ".join(violations),
        )
    return CheckResult(check=CheckName.RECOMMENDATION_PROVENANCE_PRESENCE, passed=True)


def check_required_limitation_disclosure(
    assessment: Assessment, turn_limitations: Iterable[Limitation]
) -> CheckResult:
    """Every limitation recorded in turn state appears in the assessment's limitations. Extra
    disclosures the assessment adds beyond what the turn recorded are not a violation; only an
    omission is."""
    missing = set(turn_limitations) - set(assessment.limitations)
    if missing:
        reason = "; ".join(sorted(str(limitation) for limitation in missing))
        return CheckResult(
            check=CheckName.REQUIRED_LIMITATION_DISCLOSURE,
            passed=False,
            reason=f"undisclosed: {reason}",
        )
    return CheckResult(check=CheckName.REQUIRED_LIMITATION_DISCLOSURE, passed=True)


def run_gate(
    assessment: Assessment,
    *,
    admitted_refs: AbstractSet[str],
    turn_limitations: Iterable[Limitation] = (),
) -> GroundingResult:
    """Run all four checks and return their combined verdict."""
    return GroundingResult(
        checks=(
            check_reference_resolution(assessment, admitted_refs),
            check_unsupported_element_rejection(assessment),
            check_recommendation_provenance_presence(assessment),
            check_required_limitation_disclosure(assessment, tuple(turn_limitations)),
        )
    )


class CorrectionAllowance:
    """The turn's one shared correction allowance (`workflow-design.md` §5): a single corrective
    model call, spent by whichever failure reaches it first, structural or grounding. A turn that
    spends it on one kind has none left for the other."""

    def __init__(self) -> None:
        self._spent = False

    @property
    def spent(self) -> bool:
        return self._spent

    def spend(self) -> bool:
        """Spend the allowance if it is still unspent.

        Returns whether this call spent it, so a caller holding a failure to correct knows whether
        it may retry once or must let the turn degrade.
        """
        if self._spent:
            return False
        self._spent = True
        return True


class GateRouting(StrEnum):
    """Where a grounding result sends the turn, given the correction allowance."""

    PASSED = "passed"
    CORRECT = "correct"
    FAILED_EXECUTION = "failed_execution"


def route_grounding_result(result: GroundingResult, allowance: CorrectionAllowance) -> GateRouting:
    """A pass always proceeds; the gate validates the outcome shape, it does not choose one. A
    failure spends the allowance if it is still unspent and asks for one correction; a failure
    arriving with the allowance already spent makes the attempt a failed execution, which delivers
    no brief, creates no completed turn, and persists nothing (`workflow-design.md` §7)."""
    if result.passed:
        return GateRouting.PASSED
    return GateRouting.CORRECT if allowance.spend() else GateRouting.FAILED_EXECUTION
