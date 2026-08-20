"""What one investigation carries while it runs, and the bounds it runs inside.

All of it is ephemeral. The run holds this in memory for the length of one streaming request and
nothing here is persisted: the completed record is a separate, much smaller artifact, and proposals,
working hypotheses, and bounds are working state rather than findings.

Bounds are set once, by code, at objective time. No agent widens one, and there is no path by which
a model's output becomes a bound: the roles propose actions and assessments, and every number below
is written here or not at all. Spending is likewise counted here rather than reported by the thing
being counted.

The deadline is absolute rather than a countdown, because a remaining-time field has to be written
back after every step and is wrong the moment someone forgets.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum

from opspilot.assessment.contracts import Assessment, Outcome
from opspilot.evidence.operations import EvidenceSet
from opspilot.grounding.gate import Issue
from opspilot.intake.contracts import NormalizedIncidentContext
from opspilot.retrieval.retriever import Passage
from opspilot.stream.contracts import ActivityEvent


class FailureCategory(StrEnum):
    """Why an execution failed, in terms an engineer can act on and a provider cannot leak into.

    A failed execution is not an outcome. It leaves no record, and it is deliberately distinct from
    an inconclusive investigation, which is a real result that observed something and could not
    settle a cause.
    """

    NO_EVIDENCE = "no_admitted_evidence"
    UNUSABLE_ASSESSMENT = "unusable_assessment"
    UNGROUNDED_ASSESSMENT = "ungrounded_assessment"
    SAVE_FAILED = "save_failed"
    DEADLINE_EXPIRED = "deadline_expired"
    INTERNAL_ERROR = "internal_error"


@dataclass
class Bounds:
    """The five pieces of deterministic state an investigation runs inside."""

    expires_at: float
    capability_calls: int
    model_calls: int
    correction_used: bool = False
    return_used: bool = False

    @classmethod
    def starting(cls, *, seconds: float, capability_calls: int, model_calls: int) -> Bounds:
        return cls(
            expires_at=time.monotonic() + seconds,
            capability_calls=capability_calls,
            model_calls=model_calls,
        )

    @property
    def remaining_s(self) -> float:
        return max(0.0, self.expires_at - time.monotonic())

    @property
    def expired(self) -> bool:
        return self.remaining_s <= 0.0


@dataclass
class InvestigationState:
    """One investigation, mid-flight.

    Two sets make continuation decidable without judgment. `answered_questions` holds the questions
    already put, and `executed_calls` holds the calls already made, as capability and arguments.
    Both are membership tests rather than opinions about similarity.

    The second exists because the first is the model's own prose. Asked twice for the same data, an
    investigator phrases the question differently each time and the run would spend a bound on a
    query whose answer it already holds, since admission correctly declines to admit the same
    observation twice. Same capability, same arguments, same answer: that is the same question
    however it is worded.

    `knowledge` sits beside `evidence` rather than inside it, and the separation is the point. A
    passage is what someone wrote down before this incident; an observation is what a source
    reported about it. Retrieval never passes through admission, so a passage cannot become an
    observation, and holding the two apart is what lets the grounding gate refuse a knowledge
    reference offered as current operational support. A retrieval still leaves its mark on the
    evidence set, though, on the two axes that are about the call rather than its content: the
    operation it attempted, and the limitation it becomes when it does not answer.
    """

    investigation_id: str
    incident: NormalizedIncidentContext
    bounds: Bounds
    evidence: EvidenceSet
    knowledge: list[Passage] = field(default_factory=list)
    objective: str = ""
    answered_questions: set[str] = field(default_factory=set)
    executed_calls: set[str] = field(default_factory=set)
    capability_calls_made: int = 0
    model_calls_made: int = 0
    assessment: Assessment | None = None
    issues: list[Issue] = field(default_factory=list)
    outcome: Outcome | None = None
    stopped_because: str = ""
    # Set when analysis is sent back to gather, cleared by the step that acts on it. Its
    # presence is what routes the one return, so it is the question in flight rather than a
    # record that one was asked: `return_used` is what remembers that.
    open_question: str = ""
    failure: FailureCategory | None = None
    # Emitted as they happen; the streaming request drains what it has not yet sent.
    events: list[ActivityEvent] = field(default_factory=list)
    model_deployment: str = ""
    prompt_versions: dict[str, str] = field(default_factory=dict)

    @property
    def knowledge_refs(self) -> set[str]:
        """What the run retrieved, as the gate reads it: knowledge, never operational support."""
        return {passage.reference for passage in self.knowledge}

    @property
    def capability_budget_left(self) -> bool:
        return self.capability_calls_made < self.bounds.capability_calls

    @property
    def model_budget_left(self) -> bool:
        return self.model_calls_made < self.bounds.model_calls
