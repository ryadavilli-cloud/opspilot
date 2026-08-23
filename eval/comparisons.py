"""The two controlled comparisons: change one thing about a run, and say what followed.

Each runs the same scenario under two conditions that differ in exactly one respect, and reports
what differed. Neither gates anything, and neither reports a score. A comparison that finds no
difference is a result, not a failure: the point is falsification, so a null result says the
variable did not matter here rather than that something went wrong.

The two conditions may never read one recorded model response. Replaying the same cassette into
both arms returns the same output whatever the condition changed, which does not show the variable
made no difference; it shows the variable was never applied. `require_distinct` refuses that
arrangement rather than leaving it as an instruction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evaluation import Source, require_distinct
from judge import DIAGNOSIS_MATCH

from opspilot.config import SOURCE_DEADLINE_SECONDS as DEADLINE_S
from opspilot.retrieval.retriever import PASSAGE_BUDGET
from opspilot.tools.search import search_past_incidents

# Where the expected cause landed in a condition's candidate list, ordered so two conditions can be
# compared. Only the judge decides these; this is the ranking of what it returned.
_REACH = {"absent": 0, "among_candidates": 1, "leads": 2, "not_applicable": -1}


@dataclass(frozen=True)
class Difference:
    """One thing that differed between the two conditions, and what it was."""

    dimension: str
    detail: str


@dataclass
class ComparisonResult:
    """What one comparison found, or the reason it could not be run.

    `conclusion` is what a mechanism reached where reaching something is the point rather than
    differing from another arm. The nearest-history shortcut has one condition and nothing to
    differ from: what it produces is an answer, and the report puts that answer beside the
    investigation's own so a reader can see which they would rather have acted on.
    """

    name: str
    scenario_id: str
    differences: list[Difference] = field(default_factory=list)
    note: str = ""
    ran: bool = True
    conclusion: str = ""

    @property
    def differed(self) -> bool:
        return self.ran and bool(self.differences)


def not_evaluable(name: str, scenario_id: str, why: str) -> ComparisonResult:
    """A comparison that could not be set up. Stated rather than reported as no difference, which
    is what it would otherwise look like."""
    return ComparisonResult(name=name, scenario_id=scenario_id, note=why, ran=False)


def _capabilities(record: Any) -> list[str]:
    return [operation.capability for operation in record.operations]


def _leading(record: Any) -> Any:
    candidates = record.assessment.candidates
    return candidates[0] if candidates else None


def _refs(record: Any) -> set[str]:
    return {observation.evidence_ref for observation in record.observations}


def _actions(record: Any) -> set[str]:
    return {action.action for action in record.assessment.actions}


def _statements(record: Any) -> set[str]:
    return {candidate.statement for candidate in record.assessment.candidates}


# --- adaptive value ------------------------------------------------------------------------------
def adaptive_value(
    scenario: dict[str, Any],
    adaptive: Any,
    fixed: Any,
    adaptive_source: Source,
    fixed_source: Source,
    adaptive_judgement: Any = None,
    fixed_judgement: Any = None,
) -> ComparisonResult:
    """Whether the adaptive path reached a meaningfully better result than a fixed order.

    Three signals, and any one of them is enough. Two are settled here: evidence the expectation
    requires that only the adaptive path reached, and a red herring the fixed path took as support
    while the adaptive path did not. The third, whether the fixed path missed a correct cause, is
    semantic, and the judge already answers exactly that question of one record at a time. It is
    asked of each condition separately with the one rubric, and the two categories are compared
    here. Nothing new judges anything.
    """
    scenario_id = scenario["id"]
    result = ComparisonResult(name="adaptive value", scenario_id=scenario_id)
    require_distinct(adaptive_source, fixed_source)

    only_adaptive = sorted((set(scenario["expected_evidence"]) & _refs(adaptive)) - _refs(fixed))
    if only_adaptive:
        result.differences.append(
            Difference(
                "required evidence",
                f"only the adaptive path reached {', '.join(only_adaptive)}",
            )
        )

    red_herring = scenario.get("red_herring")
    if red_herring:
        leading_fixed, leading_adaptive = _leading(fixed), _leading(adaptive)
        took_it = leading_fixed is not None and red_herring in leading_fixed.supporting
        avoided = leading_adaptive is None or red_herring not in leading_adaptive.supporting
        if took_it and avoided:
            result.differences.append(
                Difference(
                    "red herring",
                    f"the fixed path's leading candidate rests on {red_herring}, "
                    "which the adaptive path did not take as support",
                )
            )

    if adaptive_judgement is not None and fixed_judgement is not None:
        reached = _reach(adaptive_judgement), _reach(fixed_judgement)
        if reached[0] > reached[1]:
            result.differences.append(
                Difference(
                    "the cause",
                    f"the expected cause was {_category(adaptive_judgement)} on the adaptive path "
                    f"and {_category(fixed_judgement)} on the fixed one",
                )
            )
    return result


def _category(judgement: Any) -> str:
    verdicts = getattr(judgement, "verdicts", None) or {}
    verdict = verdicts.get(DIAGNOSIS_MATCH)
    return verdict.category if verdict else "not judged"


def _reach(judgement: Any) -> int:
    return _REACH.get(_category(judgement), -1)


# --- retrieval influence -------------------------------------------------------------------------
def retrieval_influence(
    scenario: dict[str, Any],
    with_knowledge: Any,
    without_knowledge: Any,
    with_source: Source,
    without_source: Source,
) -> ComparisonResult:
    """Whether retrieved knowledge reaching reasoning changed the investigation.

    Retrieval runs in both conditions and is recorded in both, so the tool counts and the activity
    stay comparable and the one variable is whether the passages reached the prompts. A precondition
    rather than an assumption: if the condition that was given its passages retrieved nothing, there
    was no influence to withhold and the comparison has not been set up, which is reported instead
    of being read as no difference.
    """
    scenario_id = scenario["id"]
    result = ComparisonResult(name="retrieval influence", scenario_id=scenario_id)
    require_distinct(with_source, without_source)

    if not with_knowledge.passages:
        return not_evaluable(
            "retrieval influence",
            scenario_id,
            "the condition that was shown its passages retrieved none, so there was no influence "
            "to withhold",
        )
    if len(without_knowledge.passages) != len(with_knowledge.passages):
        result.note = (
            f"retrieval differed between the conditions "
            f"({len(with_knowledge.passages)} passages against "
            f"{len(without_knowledge.passages)}), so more than the one variable moved"
        )

    shown_only = sorted(set(_capabilities(with_knowledge)) - set(_capabilities(without_knowledge)))
    withheld_only = sorted(
        set(_capabilities(without_knowledge)) - set(_capabilities(with_knowledge))
    )
    for capabilities, side in ((shown_only, "shown"), (withheld_only, "withheld")):
        if capabilities:
            result.differences.append(
                Difference(
                    "a capability proposed",
                    f"only the condition {side} its passages asked for {', '.join(capabilities)}",
                )
            )

    lead_with, lead_without = _leading(with_knowledge), _leading(without_knowledge)
    if _lead_of(lead_with) != _lead_of(lead_without):
        result.differences.append(
            Difference(
                "the leading candidate",
                f"shown its passages: {_lead_of(lead_with)} // withheld: {_lead_of(lead_without)}",
            )
        )

    shown_says = _statements(with_knowledge) - _statements(without_knowledge)
    withheld_says = _statements(without_knowledge) - _statements(with_knowledge)
    if shown_says or withheld_says:
        result.differences.append(
            Difference(
                "an interpretation stated",
                f"{len(shown_says)} statement(s) only where passages were shown, "
                f"{len(withheld_says)} only where they were withheld",
            )
        )

    shown_urges = _actions(with_knowledge) - _actions(without_knowledge)
    withheld_urges = _actions(without_knowledge) - _actions(with_knowledge)
    if shown_urges or withheld_urges:
        result.differences.append(
            Difference(
                "an action recommended",
                f"{len(shown_urges)} recommendation(s) only where passages were shown, "
                f"{len(withheld_urges)} only where they were withheld",
            )
        )
    return result


def _lead_of(candidate: Any) -> str:
    if candidate is None:
        return "no leading candidate"
    return f"{candidate.statement} [{candidate.label.value}]"


# --- the nearest-history shortcut ---------------------------------------------------------------
# The objection the other two comparisons cannot answer, because both of them hold OpsPilot against
# a variant of itself: why investigate at all, when the most similar past incident already carries
# a cause and a resolution somebody wrote down? This answers it by doing exactly that and reporting
# what it concluded, so the claim is settled by a result rather than by assertion.
#
# It reasons about nothing. One search of past incidents, the incident it actually returned first,
# and that write-up's recorded cause and resolution taken as the answer. No model call, no prompt,
# no current evidence, no verification. Making it cleverer would defeat it: a baseline that weighed
# a precedent against today's evidence is a second investigation, and beating that would say
# nothing about whether retrieval alone suffices.
NEAREST_HISTORY = "nearest history"

_KB_POSTMORTEMS = Path(__file__).resolve().parents[1] / "data" / "kb" / "postmortems"
_SECTION = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def nearest_history_query(incident: Any) -> str:
    """The query the shortcut searches on: the incident as it was reported, and nothing else.

    Deliberately the whole of what a shortcut has to work with. Reaching for the answer key's cause
    would be searching with the answer already in hand, and asking a model to rewrite the text into
    a better query would make this an investigation with one step.
    """
    return str(incident.short_description)


def _sections(text: str) -> dict[str, str]:
    """A write-up's second-level sections, by heading. Small and deterministic on purpose: the
    corpus is authored markdown with stable headings, and reading two of them needs no more than
    this."""
    found: dict[str, str] = {}
    matches = list(_SECTION.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        found[match.group(1).strip().lower()] = text[match.end() : end].strip()
    return found


def historical_answer(reference: str) -> tuple[str, str]:
    """What a past incident was recorded as having been caused by, and what settled it.

    Read from the authored write-up rather than from the passage retrieval returned, because the
    two sections that ranked highest for a question are not necessarily the two that hold the
    answer, and the shortcut is supposed to reuse the recorded answer rather than whatever text
    came back. No model summarizes it.
    """
    incident_id = reference.split(":", 1)[1]
    found = sorted(_KB_POSTMORTEMS.glob(f"{incident_id}-*.md"))
    if not found:
        return "", ""
    sections = _sections(found[0].read_text(encoding="utf-8"))
    return sections.get("root cause", ""), sections.get("resolution", "")


def nearest_history(scenario: dict[str, Any], incident: Any, retriever: Any) -> ComparisonResult:
    """Reach for the closest past incident and reuse its answer, then say what that would have been.

    The premise is checked before the answer is produced. The scenario names the precedent this
    corpus is authored to put first, and if retrieval returned a different one the experiment did
    not happen: the shortcut is only interesting where it lands where a shortcut would land. What
    is reported then is that the premise was not satisfied, and which incident actually came first,
    so the corpus or the query can be looked at. Substituting the expected precedent would be
    reporting an experiment nobody ran.
    """
    expected = scenario["evaluation"].get("nearest_history_should_select", "")
    # The capability the investigation itself would call, so the shortcut searches the same corpus
    # the same way and its result cannot be an artifact of a second retrieval path.
    precedents, _ = search_past_incidents(
        retriever, DEADLINE_S, query=nearest_history_query(incident), k=PASSAGE_BUDGET
    )
    if not precedents:
        return not_evaluable(
            NEAREST_HISTORY, scenario["id"], "the search of past incidents returned nothing"
        )

    top = precedents[0].reference
    if expected and top != expected:
        return not_evaluable(
            NEAREST_HISTORY,
            scenario["id"],
            f"premise not satisfied: this corpus is authored to return {expected} first and "
            f"returned {top}, so the shortcut was not tested on the precedent it exists to test",
        )

    cause, resolution = historical_answer(top)
    if not cause:
        return not_evaluable(
            NEAREST_HISTORY, scenario["id"], f"{top} records no cause the shortcut could reuse"
        )

    return ComparisonResult(
        name=NEAREST_HISTORY,
        scenario_id=scenario["id"],
        conclusion=(
            f"precedent: {top}\n"
            f"historical cause: {_condensed(cause)}\n"
            f"historical resolution: {_condensed(resolution)}"
        ),
    )


def _condensed(text: str) -> str:
    """One paragraph of a write-up's section, on one line. The report reads it beside the
    investigation's own conclusion, so it has to be comparable at a glance."""
    paragraph = text.split("\n\n", 1)[0]
    return " ".join(paragraph.split())
