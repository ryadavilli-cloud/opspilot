"""Typed contracts for the deterministic tools.

Every capability returns the uniform envelope `ToolResult`. The envelope answers two independent
questions: did the operation execute, and if it did, how complete was the answer. They are separate
fields because collapsing them is the specific mistake that turns an unreachable source into a
clean bill of health.

Records mirror the corpus; `evidence_refs` carry the references admission assigns to observations
(see `evidence/references.py`). A tool reports what it saw; it does not decide what becomes
evidence.

Capability arguments are the adapters' own typed parameters, validated where the registry invokes
them. There is no request model per capability: a conceptual request is a function's parameter
list, and the two constraints that are not expressible in a type, an impossible time window and an
oversized one, are checked by `check_window` at the one boundary that owns them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Caps — tool-local guardrails (keep queries bounded; real limits tighten in the reliability layer).
MAX_RESULTS = 500
MAX_WINDOW_DAYS = 90

# A string argument that must name something. Shared because five capabilities take one, and
# because "" reaching a partition-scoped read would query a partition that cannot exist.
NonEmptyText = Annotated[str, Field(min_length=1)]


class RequestRejected(ValueError):
    """A request that will not be executed, and why, in caller-safe terms.

    Raised before anything reaches a source, so the refusal becomes a limitation naming the
    question it failed to answer rather than an authoritative absence. The two would read
    identically to anything counting rows and they mean opposite things.
    """


def to_utc(dt: datetime) -> datetime:
    """Normalize to tz-aware UTC so corpus (…Z) and caller-supplied times compare cleanly."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def check_window(
    start: datetime | None, end: datetime | None, *, max_days: int | None = None
) -> None:
    """Refuse a window that cannot be satisfied, before the read is spent on it.

    An end before its start describes no interval at all, and a window wider than the ceiling is a
    scan rather than a query. Both are refusals rather than empty answers.
    """
    if start and end and end < start:
        raise RequestRejected("end_time is before start_time")
    if max_days is not None and start and end and (end - start).days > max_days:
        raise RequestRejected(f"time window exceeds {max_days} days")


# --- records (mirror the corpus rows) ---------------------------------------------------------
class IncidentRecord(BaseModel):
    """The stored incident row.

    Read whole here because incident selection needs the reported symptom and the time anchor.
    What an agent may observe is narrower: the `get_incident` capability admits only the fields the
    approved structured-query surface exposes, so `root_cause` and `resolution` never leave the
    adapter.
    """

    number: str
    incident_id: str
    short_description: str
    category: str
    priority: str
    impact: str
    urgency: str
    opened_at: datetime
    state: str
    made_sla: bool
    reassignment_count: int
    is_known_error: bool
    resolved_at: datetime | None = None
    close_code: str | None = None
    root_cause: str | None = None
    resolution: str | None = None


class AlertRecord(BaseModel):
    alert_id: str
    incident_id: str | None
    service: str
    severity: str
    role: str
    is_trigger: bool
    signal: str
    title: str
    fired_at: datetime
    dedup_key: str


class DeploymentRecord(BaseModel):
    deploy_id: str
    service: str
    ts: datetime
    version: str
    note: str


class LogRecord(BaseModel):
    event_id: str
    ts: datetime
    service: str
    level: str
    message: str
    incident_id: str | None = None
    label: str | None = None


class MetricSample(BaseModel):
    service: str
    metric: str
    ts: datetime
    value: float
    unit: str


class DependencyEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_service: str = Field(alias="from")
    to_service: str = Field(alias="to")
    kind: str
    critical: bool = False


# --- the two axes -----------------------------------------------------------------------------
class ExecutionOutcome(StrEnum):
    """Whether the operation executed, and if not, why not."""

    SUCCEEDED = "succeeded"
    TIMED_OUT = "timed_out"
    UNAVAILABLE = "unavailable"
    REJECTED = "rejected"
    FAILED = "failed"


class Completeness(StrEnum):
    """How complete a successful answer was. `not_applicable` is the only legal value when no
    successful result exists, because completeness of a non-answer is not a question."""

    COMPLETE = "complete"
    EMPTY = "empty"
    PARTIAL = "partial"
    NOT_APPLICABLE = "not_applicable"


# --- uniform envelope -------------------------------------------------------------------------
class ToolMetadata(BaseModel):
    tool_name: str
    duration_ms: float
    result_count: int
    truncated: bool = False


class ToolResult[T](BaseModel):
    tool_name: str
    outcome: ExecutionOutcome
    completeness: Completeness
    results: list[T] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    error: str | None = None
    metadata: ToolMetadata

    @model_validator(mode="after")
    def _check_pairing(self) -> ToolResult[T]:
        """The one enforcement point for the two axes.

        Completeness is a property of an answer, so a succeeded result has one and nothing else
        does. That single rule is the whole legal-pairing space; a table enumerating it would say
        the same thing at more length. Content follows the same line: only a succeeded result may
        carry any, because content on a call that did not answer is how fabricated evidence gets in.
        """
        succeeded = self.outcome is ExecutionOutcome.SUCCEEDED
        if succeeded is (self.completeness is Completeness.NOT_APPLICABLE):
            raise ValueError(
                f"illegal result pairing {self.outcome}/{self.completeness} from {self.tool_name}"
            )
        if not succeeded and (self.results or self.evidence_refs):
            raise ValueError(
                f"{self.tool_name} returned content on a non-succeeded outcome {self.outcome}"
            )
        return self

    @property
    def answered(self) -> bool:
        """Whether the source answered at all. Deliberately not named `ok`, and deliberately not
        a substitute for reading the completeness: a source that answered with nothing has
        `answered` True and `completeness` empty, which is a finding, not a failure."""
        return self.outcome is ExecutionOutcome.SUCCEEDED
