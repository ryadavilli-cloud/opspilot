"""The one artifact an investigation leaves behind.

Written once, after the investigation completes, and read afterwards for the brief, the question
over the record, and evaluation. It is the only thing that outlives the run: ephemeral working
state, the bounds, the proposals, and the working hypotheses are not here, because none of them is
part of what the investigation found.

This is a model rather than a plain shape because it persists, and it exists precisely in order to
cross that boundary. What it composes stays as it is: admitted observations, limitations,
operations, and passages are in-process shapes that no layer serializes on their own, so they stay
frozen dataclasses and are validated and serialized here as fields. Making them models to match
would be a pattern applied for its own sake.

The record is self-contained on purpose. Every reference an assessment cites is meant to resolve
against the evidence and passages carried here, so a reader that holds the record needs nothing
else to check a citation, and a question asked months later is answered from the same material the
analyst had.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opspilot.assessment.contracts import Assessment, Brief, Outcome
from opspilot.evidence.admission import AdmittedObservation, Limitation
from opspilot.evidence.operations import Operation
from opspilot.retrieval.retriever import Passage


class CompletedInvestigation(BaseModel):
    """One investigation, as it finished.

    `investigation_id` is the only identity, and it is the persistence key, the telemetry
    correlation handle, and what a later question names.
    """

    model_config = ConfigDict(frozen=True)

    investigation_id: str
    incident_id: str
    objective: str

    # What the run reached, and why it stopped gathering when it did. The outcome follows from the
    # assessment and the limitations; the reason is what a reader needs to judge whether the
    # investigation stopped because it was finished or because it ran out of room.
    outcome: Outcome
    stopped_because: str

    # The evidence set, whole: what was observed, what could not be established, and every call
    # attempted. Failed operations stay, because an account of a run that hides its unanswered
    # calls reads as more complete than the run was.
    observations: list[AdmittedObservation] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    operations: list[Operation] = Field(default_factory=list)

    # The passages the run retrieved, with their text, so a knowledge citation resolves against the
    # record rather than against a corpus that may have moved on.
    passages: list[Passage] = Field(default_factory=list)

    assessment: Assessment
    brief: Brief

    # How to find this run in telemetry, and what produced it. Version identity travels with the
    # record because an evaluation comparing two runs has to know whether the model or the prompts
    # moved underneath them.
    trace_id: str = ""
    model_deployment: str = ""
    prompt_versions: dict[str, str] = Field(default_factory=dict)

    # What the run cost, known at persist time and accounted for nowhere else. Facts about the run
    # in the same category as the deployment and prompt versions: not evidence, cited by nothing,
    # and read by nothing in the investigation. Token usage keeps input and output apart, under the
    # names the adapter reports them by.
    model_calls_made: int = 0
    capability_calls_made: int = 0
    token_usage: dict[str, int] = Field(default_factory=dict)
    duration_s: float = 0.0

    @property
    def evidence_refs(self) -> set[str]:
        """Every reference this record can answer for: admitted observations and retrieved
        passages. What a citation must resolve against, held in one place."""
        return {observation.evidence_ref for observation in self.observations} | {
            passage.reference for passage in self.passages
        }


class InvestigationSummary(BaseModel):
    """One completed investigation as a listing shows it: identity, outcome, what produced it, and
    what it cost.

    `taken_at` is when the record was written, which is when the investigation completed, because
    the record is written once and only then. The store supplies it from what it knows about the
    write; the record itself carries no clock.
    """

    model_config = ConfigDict(frozen=True)

    investigation_id: str
    incident_id: str
    taken_at: datetime
    outcome: Outcome
    model_deployment: str = ""
    model_calls_made: int = 0
    capability_calls_made: int = 0
    token_usage: dict[str, int] = Field(default_factory=dict)
    duration_s: float = 0.0
