"""The assessment one investigation produces, and the brief that presents it.

The assessment is the analyst's answer: what happened, which causes are in play and which of them
the evidence establishes, what stayed unknown, what could not be established, what to check next,
and what to do. Every reference it carries is a plain string; the prefix already says whether it
names operational evidence or retrieved knowledge, so nothing here carries a role, a provenance
category, or a strength vocabulary beside the fields below.

Two absences are deliberate.

No shape here re-checks whether a claim is supported. Grounding owns that question and owns it
alone, so a validator repeating it would either agree (and be dead weight) or disagree (and make
deliverability depend on which layer ran first). What the model proposed is what the gate sees.

No number appears anywhere. Model confidence is not a form of support, and a float on any of these
would become one the moment something sorted or thresholded on it. How well supported an
explanation is follows from the evidence attached to it and from the label it carries.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SupportLabel(StrEnum):
    """How well the evidence supports a candidate, qualitatively. Kept as an enum because it is
    reused and because model output should be constrained to known values."""

    LEADING = "leading"
    PLAUSIBLE = "plausible"
    WEAKLY_SUPPORTED = "weakly_supported"


class Outcome(StrEnum):
    """What the investigation reached. Follows from two facts the assessment already holds:
    whether any candidate is established, and whether any limitation was recorded."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    INCONCLUSIVE = "inconclusive"


class Candidate(BaseModel):
    """One explanation, its label, and the references that bear on it in each direction.

    `established` means the brief may present it as current fact. Contradicting evidence is
    attached to the candidate it bears on rather than dropped to make the assessment read cleanly.
    """

    model_config = ConfigDict(frozen=True)

    statement: str
    label: SupportLabel
    established: bool = False
    supporting: list[str] = Field(default_factory=list)
    weakening: list[str] = Field(default_factory=list)


class Action(BaseModel):
    """A recommended action. Nothing executes one, and none implies an operational write.

    `now` separates immediate action or verification from longer-term follow-up and prevention.
    `knowledge_ref` is present where retrieved guidance supplied the action; an action without one
    is general practice and the brief says so.
    """

    model_config = ConfigDict(frozen=True)

    action: str
    now: bool = False
    knowledge_ref: str | None = None


class Assessment(BaseModel):
    """Exactly one per investigation. No other component produces a competing one.

    `candidates` is ordered and the first is the leading one. Whether a supported conclusion exists
    is not a stored field: it is exactly "some candidate is established".
    """

    model_config = ConfigDict(frozen=True)

    what_happened: str = ""
    what_happened_refs: list[str] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    # The recorded limitations the analyst acknowledges, by the questions they went unanswered on.
    limitations: list[str] = Field(default_factory=list)
    next_check: str | None = None
    actions: list[Action] = Field(default_factory=list)
    history: str | None = None
    history_refs: list[str] = Field(default_factory=list)
    knowledge_used: list[str] = Field(default_factory=list)

    @property
    def established(self) -> list[Candidate]:
        """The candidates the assessment presents as current fact, in their order."""
        return [candidate for candidate in self.candidates if candidate.established]


class Brief(BaseModel):
    """The engineer-facing rendering of one assessment, and the outcome it reached.

    A rendering, not a second analysis: it introduces nothing the assessment does not hold and
    drops nothing it does. Section layout is a presentation choice and is not a schema, so the
    rendered text is one string rather than a set of typed sections.
    """

    model_config = ConfigDict(frozen=True)

    outcome: Outcome
    text: str
