"""Deterministic projection from an assessment to its brief.

A rendering, not a second analysis. No model call happens here: the brief presents what the
assessment holds and cannot introduce a candidate, relationship, recommendation, or conclusion it
does not, nor drop one it does. A brief that quietly omits a weakening observation asserts more
than the assessment supports, exactly as one that invents a candidate does.

What may vary is presentation: which sections are visible, how detail is disclosed, how citations
are formatted. Omitting a section the assessment left empty is presentation. Removing, reordering,
or rewriting content the assessment holds is not, and the brief contract refuses both.
"""

from __future__ import annotations

from opspilot.assessment.contracts import (
    Assessment,
    Brief,
    BriefSection,
    Citation,
    ConclusionDisposition,
    Horizon,
    Strength,
)
from opspilot.evidence.references import CitationRole

_HORIZON_LABELS = {Horizon.NOW: "Now", Horizon.SOON: "Soon", Horizon.LATER: "Later"}


def _conclusion_line(assessment: Assessment) -> str:
    if assessment.disposition is ConclusionDisposition.SUPPORTED_CONCLUSION:
        assert assessment.leading_candidate is not None  # the contract guarantees this pairing
        return assessment.leading_candidate.statement
    # Insufficiency is stated plainly rather than dressed as a weak conclusion.
    return "Current evidence does not support stating a cause. " + (
        f"The most useful next check: {assessment.unresolved_discriminator}"
        if assessment.unresolved_discriminator
        else "No single check would clearly separate the remaining possibilities."
    )


def _next_action(assessment: Assessment) -> str:
    for horizon in (Horizon.NOW, Horizon.SOON, Horizon.LATER):
        for rec in assessment.recommendations:
            if rec.horizon is horizon:
                return rec.action
    return ""


def _candidate_lines(assessment: Assessment) -> list[str]:
    lines: list[str] = []
    for candidate in assessment.candidates():
        marker = "established" if candidate.strength is Strength.ESTABLISHED else "possible"
        lines.append(f"[{candidate.label.value}, {marker}] {candidate.statement}")
    return lines


def _evidence_lines(assessment: Assessment) -> tuple[list[str], list[Citation]]:
    """Supporting and weakening references, per candidate, with weakening never dropped."""
    lines: list[str] = []
    citations: list[Citation] = []
    for candidate in assessment.candidates():
        for ref in candidate.supporting:
            lines.append(f"supports [{candidate.label.value}]: {ref}")
            citations.append(Citation(reference=ref, role=CitationRole.CURRENT_SUPPORT))
        for ref in candidate.weakening:
            lines.append(f"weakens [{candidate.label.value}]: {ref}")
            citations.append(Citation(reference=ref, role=CitationRole.CURRENT_CONTRADICTION))
    return lines, citations


def _section(name: str, lines: list[str], citations: list[Citation] | None = None) -> BriefSection:
    return BriefSection(name=name, body="\n".join(lines), citations=citations or [])


def project(assessment: Assessment) -> Brief:
    """Render the brief. Empty sections are omitted; populated ones carry everything they hold."""
    sections: list[BriefSection] = []

    lead = [_conclusion_line(assessment)]
    action = _next_action(assessment)
    if action:
        lead.append(f"Next action: {action}")
    sections.append(_section("current_conclusion_and_next_action", lead))

    happened = assessment.what_happened
    sections.append(_section("what_happened", [happened.statement], list(happened.citations)))

    candidate_lines = _candidate_lines(assessment)
    if candidate_lines:
        sections.append(_section("what_may_be_causing_it", candidate_lines))

    evidence_lines, evidence_citations = _evidence_lines(assessment)
    if evidence_lines:
        sections.append(
            _section("supporting_and_weakening_evidence", evidence_lines, evidence_citations)
        )

    unknown = [str(limitation) for limitation in assessment.limitations]
    if assessment.unresolved_discriminator:
        unknown.append(f"Most useful next check: {assessment.unresolved_discriminator}")
    if unknown:
        sections.append(_section("what_remains_unknown", unknown))

    if assessment.historical_comparison is not None:
        history = assessment.historical_comparison
        sections.append(_section("what_history_says", [history.statement], list(history.citations)))

    if assessment.recommendations:
        lines = []
        for horizon in (Horizon.NOW, Horizon.SOON, Horizon.LATER):
            for rec in assessment.recommendations:
                if rec.horizon is not horizon:
                    continue
                provenance = rec.provenance.value.replace("_", " ")
                confirm = f" Confirm by: {rec.confirm_signal}" if rec.confirm_signal else ""
                lines.append(
                    f"{_HORIZON_LABELS[horizon]}: {rec.action} ({rec.kind.value}, {provenance})"
                    f"{confirm}"
                )
        sections.append(_section("what_to_do", lines))

    sources = sorted({ref for c in assessment.candidates() for ref in c.supporting + c.weakening})
    sources += sorted(assessment.relevant_knowledge)
    if sources:
        sections.append(_section("sources_limitations_and_diagnostics", sources))

    return Brief(
        investigation_id=assessment.investigation_id,
        turn_id=assessment.turn_id,
        sections=sections,
    )
