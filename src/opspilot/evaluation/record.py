"""The document a kept evaluation run is persisted as.

One run, as the runner saw it when it finished: what it ran under, what each scenario did and how it
fared on the deterministic checks and before the judge, and what each comparison found. It is a
point-in-time reading and is never edited; the runner writes it and the application only reads it.

Deterministic results and judge categories sit in separate fields, so nothing can merge them, and
there is no aggregate anywhere in the shape: a number would invite a threshold, and no threshold has
a measured baseline to stand on. This is a model because it crosses a persistence boundary and is
read back by another process; what it composes are plain shapes serialized here and nowhere else.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeterministicCheck(BaseModel):
    """One mechanical check on one scenario: its name, whether it passed, and the failures it
    named. A check that passed names nothing."""

    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    failures: list[str] = Field(default_factory=list)


class JudgeVerdict(BaseModel):
    """One judged quality: the category the judge chose and the sentence that decided it."""

    model_config = ConfigDict(frozen=True)

    quality: str
    category: str
    why: str


class ScenarioRun(BaseModel):
    """What one scenario did in this run.

    `provenance` says how its investigation was obtained: replayed, obtained live, or not run, and
    `source` names the recording, the deployment, or the reason it did not run. Where the judge
    gave no verdicts, `judge_note` says why, so an absent judgement is stated rather than blank.
    """

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    provenance: str
    source: str
    outcome: str = ""
    checks: list[DeterministicCheck] = Field(default_factory=list)
    verdicts: list[JudgeVerdict] = Field(default_factory=list)
    judge_deployment: str = ""
    judge_note: str = ""


class ComparisonDifference(BaseModel):
    """One thing that differed between a comparison's two conditions. The detail names the
    condition the difference fell on."""

    model_config = ConfigDict(frozen=True)

    dimension: str
    detail: str


class ComparisonRun(BaseModel):
    """One controlled comparison: what differed, or why it could not be set up.

    `ran` is false when a condition could not be obtained, and `note` then carries the reason. When
    it ran, `note` carries any caveat the comparison stated about itself, and a comparison that ran
    and found nothing is a result: the differences are simply empty.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    scenario_id: str
    ran: bool = True
    differences: list[ComparisonDifference] = Field(default_factory=list)
    note: str = ""


class EvaluationRun(BaseModel):
    """One kept run. `run_id` is the partition key and is date-ordered, so the history reads in
    the order it was written; `configuration` is what the run ran under, the runtime's identity
    and the judge's, and is the whole basis on which two runs are comparable."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    taken_at: datetime
    label: str = ""
    configuration: dict[str, str] = Field(default_factory=dict)
    scenarios: list[ScenarioRun] = Field(default_factory=list)
    comparisons: list[ComparisonRun] = Field(default_factory=list)


class EvaluationRunSummary(BaseModel):
    """One kept run as a listing shows it. The configuration travels with the summary because a
    listing has to show where one run stops being comparable with the one above it."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    taken_at: datetime
    label: str = ""
    configuration: dict[str, str] = Field(default_factory=dict)
