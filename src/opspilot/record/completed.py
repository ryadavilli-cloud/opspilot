"""The one artifact an investigation leaves behind.

Written once, after the gate passes and before the terminal event, and read afterwards for the
brief, the question, and evaluation. There is exactly one per investigation, and nothing reopens or
revises it.

What it carries is what someone has to be able to reconstruct later: what was asked, what was
observed, what could not be, what was attempted, what the analyst concluded, what the engineer was
shown, and which deployment and prompts produced it. What it deliberately does not carry is
ephemeral working state: no bounds, no proposals, no working hypotheses. Those shaped the run
without being findings, and persisting them would invite reading a discarded idea as a conclusion.

The operations list records the attempt, not the call: an identifier, the capability, and how it
ended. Arguments and raw results stay out, because the record is an account of what the
investigation did, not a transcript it could be replayed from.

`investigation_id` is also the telemetry correlation reference. Spans are correlated by it alone,
so a second field naming the same thing would be one more place for the two to disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from opspilot.assessment.contracts import Assessment, Brief, Outcome
from opspilot.evidence.admission import AdmittedObservation, Limitation
from opspilot.evidence.operations import Operation


@dataclass(frozen=True)
class CompletedInvestigation:
    """One completed investigation. Frozen: a delivered brief is never edited."""

    investigation_id: str
    incident_id: str
    objective: str
    outcome: Outcome
    # Why gathering ended, in the caller's terms. Recorded because an investigation that stopped at
    # a bound and one that stopped because the evidence was ready are different runs, and the
    # outcome alone does not tell them apart.
    stopped_because: str
    assessment: Assessment
    brief: Brief
    model_deployment: str
    observations: tuple[AdmittedObservation, ...] = ()
    limitations: tuple[Limitation, ...] = ()
    operations: tuple[Operation, ...] = ()
    prompt_versions: tuple[str, ...] = field(default_factory=tuple)
