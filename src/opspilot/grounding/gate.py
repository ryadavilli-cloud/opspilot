"""Grounding: one deterministic function, zero or more issues.

It reads the admitted assessment, the operational evidence this investigation admitted, the
knowledge it retrieved, and the limitations it recorded, and reports what would make the assessment
unsafe to deliver. It edits nothing, chooses no outcome, and runs no model.

The one distinction it draws is between the two roles a reference can play, and the prefix already
tells them apart. **Current operational support** must resolve to something admitted in this
investigation: it is the claim that the running system was observed doing this. **Knowledge or
context** must resolve to a passage retrieved in this investigation: it may inform history,
interpretation, or an action's provenance, and it may never stand as proof about the incident,
because a document cannot observe the current system. No role field or provenance taxonomy is
needed to enforce that.

An issue carries a kind and a detail, and the kinds below are diagnostics rather than a contract.
Nothing counts them, no type guarantees their number, and adding a property that turns out to
matter means adding a check, not reconfiguring a fixed set.

What it does not do is read prose. Whether a cited observation semantically bears out the sentence
attached to it is a judgment, and judgment belongs to the offline judge, not to a gate that has to
be deterministic to be worth anything.
"""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from opspilot.assessment.contracts import Assessment
from opspilot.evidence.admission import Limitation
from opspilot.evidence.references import ReferenceType, try_parse

UNRESOLVED_REFERENCE = "unresolved_reference"
KNOWLEDGE_AS_SUPPORT = "knowledge_as_support"
UNSUPPORTED_CLAIM = "unsupported_claim"
UNDISCLOSED_LIMITATION = "undisclosed_limitation"


@dataclass(frozen=True)
class Issue:
    """One thing wrong with the assessment, named well enough to correct without re-running."""

    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.detail}"


def _is_knowledge(ref: str) -> bool:
    parsed = try_parse(ref)
    return parsed is not None and parsed.reference_type is ReferenceType.KNOWLEDGE


def _support_issues(refs: Iterable[str], where: str, admitted: AbstractSet[str]) -> list[Issue]:
    """References standing as current operational support: knowledge cannot, and evidence must
    have been admitted here."""
    issues: list[Issue] = []
    for ref in refs:
        if _is_knowledge(ref):
            issues.append(
                Issue(KNOWLEDGE_AS_SUPPORT, f"{ref} stands as operational support in {where}")
            )
        elif ref not in admitted:
            issues.append(
                Issue(UNRESOLVED_REFERENCE, f"{ref} in {where} was not admitted in this run")
            )
    return issues


def _knowledge_issues(refs: Iterable[str], where: str, retrieved: AbstractSet[str]) -> list[Issue]:
    return [
        Issue(UNRESOLVED_REFERENCE, f"{ref} in {where} was not retrieved in this run")
        for ref in refs
        if ref not in retrieved
    ]


def _has_admitted_support(refs: Iterable[str], admitted: AbstractSet[str]) -> bool:
    return any(ref in admitted and not _is_knowledge(ref) for ref in refs)


def ground(
    assessment: Assessment,
    *,
    admitted_refs: AbstractSet[str],
    knowledge_refs: AbstractSet[str] = frozenset(),
    limitations: Iterable[Limitation] = (),
) -> list[Issue]:
    """Every issue this assessment carries, in reading order. Empty means deliverable."""
    issues: list[Issue] = []

    issues.extend(_support_issues(assessment.what_happened_refs, "what_happened", admitted_refs))
    if not _has_admitted_support(assessment.what_happened_refs, admitted_refs):
        issues.append(
            Issue(UNSUPPORTED_CLAIM, "what_happened rests on no admitted operational evidence")
        )

    for candidate in assessment.candidates:
        where = f"candidate {candidate.statement!r}"
        issues.extend(_support_issues(candidate.supporting, f"{where} support", admitted_refs))
        issues.extend(_support_issues(candidate.weakening, f"{where} weakening", admitted_refs))
        if candidate.established and not _has_admitted_support(candidate.supporting, admitted_refs):
            issues.append(
                Issue(UNSUPPORTED_CLAIM, f"{where} is established on no admitted evidence")
            )

    issues.extend(_knowledge_issues(assessment.knowledge_used, "knowledge_used", knowledge_refs))
    issues.extend(_knowledge_issues(assessment.history_refs, "history", knowledge_refs))
    for action in assessment.actions:
        if action.knowledge_ref:
            issues.extend(
                _knowledge_issues(
                    [action.knowledge_ref], f"action {action.action!r}", knowledge_refs
                )
            )

    # A disclosure counts when it carries the recorded question verbatim, whether or not the
    # analyst wrote anything alongside it. It reads the question back to the engineer either way,
    # which is what being represented in the assessment means, and an analyst that appends why the
    # question went unanswered has disclosed more rather than less. Containment of an exact
    # recorded string keeps this a comparison rather than a judgment about prose.
    disclosed = [text.strip() for text in assessment.limitations]
    issues.extend(
        Issue(UNDISCLOSED_LIMITATION, limitation.question)
        for limitation in limitations
        if not any(limitation.question.strip() in text for text in disclosed)
    )

    return issues
