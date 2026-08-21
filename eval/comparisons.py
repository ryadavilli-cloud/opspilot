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

from dataclasses import dataclass, field
from typing import Any

from evaluation import Source, require_distinct
from judge import DIAGNOSIS_MATCH

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
    """What one comparison found, or the reason it could not be run."""

    name: str
    scenario_id: str
    differences: list[Difference] = field(default_factory=list)
    note: str = ""
    ran: bool = True

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
