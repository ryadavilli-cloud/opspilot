"""Deterministic rendering from an assessment to its brief.

A rendering, not a second analysis. No model call happens here: the brief presents what the
assessment holds and cannot introduce a candidate, an action, or a conclusion it does not, nor drop
one it does. A brief that quietly omits a weakening observation asserts more than the assessment
supports, exactly as one that invents a candidate does.

Ordering is the presentation choice that does most of the work. What happened comes first, then the
explanations with the best-supported one leading, then what to do with immediate actions first, so
an engineer reading only the top of the brief reads the three things that matter soonest. Where the
evidence establishes more than one cause, they are presented as contributing causes rather than as
one leading candidate and a set of alternatives, because ranking co-causes would assert a structure
the evidence did not produce.

No probability appears, and none can: nothing in the assessment carries a number, and support is
expressed by the label a candidate carries and the references attached to it.
"""

from __future__ import annotations

from opspilot.assessment.contracts import Assessment, Brief, Candidate, Outcome


def outcome_of(assessment: Assessment) -> Outcome:
    """The outcome the investigation reached, from two facts the assessment already holds.

    This over-reports partial, since one small limitation makes an otherwise clean investigation
    partial. That is the honest direction to err: the limitation is disclosed either way.
    """
    if not assessment.established:
        return Outcome.INCONCLUSIVE
    return Outcome.PARTIAL if assessment.limitations else Outcome.COMPLETE


def _refs(label: str, refs: list[str]) -> list[str]:
    # Space-separated, never punctuated: each reference stays a token the one parser can read.
    return [f"{label}: {' '.join(refs)}"] if refs else []


def _candidate_lines(candidate: Candidate) -> list[str]:
    marker = "established" if candidate.established else "not established"
    lines = [f"- {candidate.statement} [{candidate.label.value}, {marker}]"]
    lines.extend(f"  {line}" for line in _refs("Supports", candidate.supporting))
    lines.extend(f"  {line}" for line in _refs("Weakens", candidate.weakening))
    return lines


def _section(heading: str, lines: list[str]) -> list[str]:
    """One heading and its body, or nothing at all when the assessment left it empty. Omitting an
    empty section is presentation; omitting a populated one would not be."""
    return [heading, *lines, ""] if lines else []


def render(assessment: Assessment) -> Brief:
    """Render the brief and the outcome it reached."""
    outcome = outcome_of(assessment)
    blocks: list[str] = [f"Outcome: {outcome.value}", ""]

    happened = [assessment.what_happened] if assessment.what_happened else []
    happened.extend(_refs("Evidence", assessment.what_happened_refs))
    blocks.extend(_section("What happened", happened))

    causes = [line for candidate in assessment.candidates for line in _candidate_lines(candidate)]
    contributing = len(assessment.established) > 1
    blocks.extend(
        _section("Contributing causes" if contributing else "What may be causing it", causes)
    )

    # Immediate actions first, then the rest, each stated with where it came from. An action that
    # says no immediate action is required is an entry like any other and is rendered as one.
    actions: list[str] = []
    for immediate in (True, False):
        for action in assessment.actions:
            if action.now is not immediate:
                continue
            reference = action.knowledge_ref
            source = f"guidance: {reference}" if reference else "own judgement"
            actions.append(f"{'Now' if immediate else 'Later'}: {action.action} ({source})")
    blocks.extend(_section("What to do", actions))

    blocks.extend(_section("What remains unknown", [f"- {text}" for text in assessment.unknowns]))
    blocks.extend(
        _section("What could not be established", [f"- {text}" for text in assessment.limitations])
    )
    if assessment.next_check:
        blocks.extend(_section("Most useful next check", [assessment.next_check]))

    if assessment.history:
        history = [assessment.history, *_refs("Sources", assessment.history_refs)]
        blocks.extend(_section("What history says", history))
    blocks.extend(_section("Knowledge used", _refs("References", assessment.knowledge_used)))

    return Brief(outcome=outcome, text="\n".join(blocks).strip())
