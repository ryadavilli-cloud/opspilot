"""The offline judge: one model call per scenario, returning categories and nothing else.

Advisory, and deliberately weaker in standing than the deterministic half. It runs after those
checks, its result is reported beside them, and it is never a runtime authority. It cannot fail a
scenario: a `ScenarioResult` has no field a category could be written into, so "never combined into
one number" is a property of the shapes here rather than a rule someone has to remember.

What it is asked is fixed by the design and is not this module's to extend: four qualities of the
delivered brief, plus the semantic diagnosis match the mechanical layer deliberately does not
attempt. It reads the brief, the incident as it was reported, and the expectation. It is not shown
the observations, the operations, or the passages, and it is not shown the parts of the expectation
code has already decided, because a judge invited to re-decide a settled question sometimes will.

The incident is given as the symptom that was reported, never as the scenario's title. A title
written by the corpus author names the cause, and handing that to a judge asked how well a brief
explains itself would let it read the answer back to us.

An unusable response is refused rather than repaired. A category outside the vocabulary is not
coerced to the nearest value, and a missing one is not filled in with a default, because either
would report a judgement nobody made.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opspilot.llm.base import ChatMessage, ChatResult
from opspilot.llm.prompts import get_prompt

PROMPTS = Path(__file__).resolve().parent / "prompts"
JUDGE_TASK = "judge"

# The four qualities are fixed by the accepted decision; the diagnosis match is the semantic half
# of scenario behavior. Two vocabularies rather than one, because the match asks where in the
# candidate list the expected cause landed, which `partial` could not express.
QUALITIES = (
    "usefulness_and_coherence",
    "appropriate_uncertainty",
    "explanation_in_context",
    "recommendation_fit",
)
DIAGNOSIS_MATCH = "diagnosis_match"
QUALITY_CATEGORIES = ("meets", "partial", "does_not_meet")
MATCH_CATEGORIES = ("leads", "among_candidates", "absent", "not_applicable")


class UnusableVerdict(ValueError):
    """The judge answered with something that is not a judgement."""


@dataclass(frozen=True)
class Verdict:
    """One category and the sentence that decided it."""

    category: str
    why: str


@dataclass(frozen=True)
class Judged:
    """One scenario's judgement, or the reason there is none.

    Separate from `ScenarioResult` on purpose. The report prints the two beside each other and
    nothing merges them, so a category cannot reach a pass or a failure list.
    """

    scenario_id: str
    verdicts: dict[str, Verdict] | None = None
    deployment: str = ""
    note: str = ""

    @property
    def ran(self) -> bool:
        return self.verdicts is not None


def _stated(label: str, value: Any) -> list[str]:
    """One expectation field, or nothing where this scenario does not carry it."""
    if not value:
        return []
    if isinstance(value, list):
        return [f"{label}:", *(f"- {item}" for item in value), ""]
    return [f"{label}: {value}", ""]


def context_for(record: Any, scenario: dict[str, Any], reported: str) -> str:
    """What the judge reads: the incident as reported, the brief as delivered, the expectation.

    The brief already renders every candidate with its label and its references, so the diagnosis
    match has what it needs without being handed the evidence set. Where a scenario states no
    expected cause, none is written here and the rubric returns `not_applicable` for the match.
    """
    parts = [
        f"Incident {record.incident_id}, as reported: {reported}",
        "",
        f"The brief it produced, reported as {record.outcome.value}:",
        "",
        record.brief.text,
        "",
        "What a correct investigation of this was expected to reach:",
        "",
    ]
    expectation = scenario.get("evaluation", {})
    parts += _stated("Expected cause", scenario.get("root_cause"))
    parts += _stated("Acceptable alternatives", expectation.get("acceptable_alternatives"))
    parts += _stated("The behavior this scenario tests", expectation.get("behavior_tested"))
    parts += _stated("How written guidance should matter", expectation.get("knowledge_should"))
    parts += _stated("A recommendation that fits", expectation.get("expected_recommendation"))
    return "\n".join(parts).strip()


def _verdict(payload: dict[str, Any], key: str, allowed: tuple[str, ...]) -> Verdict:
    entry = payload.get(key)
    if not isinstance(entry, dict):
        raise UnusableVerdict(f"the judge returned no verdict for {key}")
    category = str(entry.get("category", "")).strip()
    if category not in allowed:
        raise UnusableVerdict(
            f"the judge answered {key} with {category!r}, which is not one of {', '.join(allowed)}"
        )
    why = str(entry.get("why", "")).strip()
    if not why:
        raise UnusableVerdict(f"the judge gave a category for {key} without saying why")
    return Verdict(category=category, why=why)


def read_verdicts(text: str) -> dict[str, Verdict]:
    """The judgement in a response, or a refusal naming what was wrong with it."""
    cleaned = (text or "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise UnusableVerdict("the judge returned no JSON object")
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as error:
        raise UnusableVerdict(f"the judge's response is not readable JSON: {error}") from error
    if not isinstance(payload, dict):
        raise UnusableVerdict("the judge returned JSON that is not an object")

    verdicts = {name: _verdict(payload, name, QUALITY_CATEGORIES) for name in QUALITIES}
    verdicts[DIAGNOSIS_MATCH] = _verdict(payload, DIAGNOSIS_MATCH, MATCH_CATEGORIES)
    return verdicts


def judge(model: Any, record: Any, scenario: dict[str, Any], reported: str) -> Judged:
    """One call, one judgement.

    The model is passed in rather than built here, so which deployment answers is the caller's
    choice and this module never has an opinion about it. No deadline: nothing is racing an
    offline report, and the investigation whose bounds would have applied is long over.
    """
    prompt = get_prompt("judge", prompts_dir=PROMPTS)
    result: ChatResult = model.complete(
        JUDGE_TASK,
        [
            ChatMessage(role="system", content=prompt.text),
            ChatMessage(role="user", content=context_for(record, scenario, reported)),
        ],
        None,
    )
    return Judged(
        scenario_id=scenario.get("id", ""),
        verdicts=read_verdicts(result.text),
        deployment=result.deployment,
    )
