"""Typed contracts for the deterministic tools.

Every tool takes a validated request and returns the uniform envelope `ToolResult`. The envelope
answers two independent questions: did the operation execute, and if it did, how complete was the
answer. They are separate fields because collapsing them is the specific mistake that turns an
unreachable source into a clean bill of health.

Records mirror the corpus; `evidence_refs` carry the provenance keys admission assigns evidence
references from (see `evidence/references.py`). A tool reports what it saw; it does not decide
what becomes evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Caps — tool-local guardrails (keep queries bounded; real limits tighten in the reliability layer).
MAX_RESULTS = 500
MAX_WINDOW_DAYS = 90


def to_utc(dt: datetime) -> datetime:
    """Normalize to tz-aware UTC so corpus (…Z) and caller-supplied times compare cleanly."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# --- records (mirror the corpus rows) ---------------------------------------------------------
class IncidentRecord(BaseModel):
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


class DocHit(BaseModel):
    doc_id: str  # the retrieval ref, e.g. runbook:payment-timeout, also the evidence ref
    kind: str  # runbook | architecture | postmortem
    title: str
    services: list[str]
    score: float


# --- requests (validated at the tool-service boundary) ----------------------------------------
class GetIncidentRequest(BaseModel):
    incident_id: str = Field(min_length=1)


class GetCorrelatedAlertsRequest(BaseModel):
    incident_id: str = Field(min_length=1)
    start_time: datetime | None = None
    end_time: datetime | None = None

    @model_validator(mode="after")
    def _check_window(self) -> GetCorrelatedAlertsRequest:
        self.start_time = to_utc(self.start_time) if self.start_time else None
        self.end_time = to_utc(self.end_time) if self.end_time else None
        if self.start_time and self.end_time and self.end_time < self.start_time:
            raise ValueError("end_time is before start_time")
        return self


class GetDeploymentsRequest(BaseModel):
    services: list[str] = Field(min_length=1)
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def _check_window(self) -> GetDeploymentsRequest:
        self.start_time = to_utc(self.start_time)
        self.end_time = to_utc(self.end_time)
        if self.end_time < self.start_time:
            raise ValueError("end_time is before start_time")
        if (self.end_time - self.start_time).days > MAX_WINDOW_DAYS:
            raise ValueError(f"time window exceeds {MAX_WINDOW_DAYS} days")
        return self


class GetLogsRequest(BaseModel):
    service: str = Field(min_length=1)
    start_time: datetime | None = None
    end_time: datetime | None = None
    level: str | None = None  # optional filter, e.g. "error"
    contains: str | None = None  # optional case-insensitive message substring

    @model_validator(mode="after")
    def _check_window(self) -> GetLogsRequest:
        self.start_time = to_utc(self.start_time) if self.start_time else None
        self.end_time = to_utc(self.end_time) if self.end_time else None
        if self.start_time and self.end_time and self.end_time < self.start_time:
            raise ValueError("end_time is before start_time")
        return self


class GetMetricsRequest(BaseModel):
    service: str = Field(min_length=1)  # service or infra entity that emits metrics
    metric: str | None = None  # optional single metric; else all for the entity
    start_time: datetime | None = None
    end_time: datetime | None = None

    @model_validator(mode="after")
    def _check_window(self) -> GetMetricsRequest:
        self.start_time = to_utc(self.start_time) if self.start_time else None
        self.end_time = to_utc(self.end_time) if self.end_time else None
        if self.start_time and self.end_time and self.end_time < self.start_time:
            raise ValueError("end_time is before start_time")
        return self


class GetServiceDependenciesRequest(BaseModel):
    service: str | None = None  # None -> the whole graph
    direction: Literal["upstream", "downstream", "both"] = "both"


class SearchRunbooksRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=MAX_RESULTS)
    service: str | None = None  # optional metadata filter


class SearchPastIncidentsRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=MAX_RESULTS)
    service: str | None = None


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


# The legal pairings. Any other combination is a defect in the adapter that produced it, so the
# envelope refuses to construct rather than carrying a pairing nothing downstream can read.
LEGAL_PAIRINGS: Mapping[ExecutionOutcome, frozenset[Completeness]] = MappingProxyType(
    {
        ExecutionOutcome.SUCCEEDED: frozenset(
            {Completeness.COMPLETE, Completeness.EMPTY, Completeness.PARTIAL}
        ),
        ExecutionOutcome.TIMED_OUT: frozenset({Completeness.NOT_APPLICABLE}),
        ExecutionOutcome.UNAVAILABLE: frozenset({Completeness.NOT_APPLICABLE}),
        ExecutionOutcome.REJECTED: frozenset({Completeness.NOT_APPLICABLE}),
        ExecutionOutcome.FAILED: frozenset({Completeness.NOT_APPLICABLE}),
    }
)


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
        if self.completeness not in LEGAL_PAIRINGS[self.outcome]:
            raise ValueError(
                f"illegal result pairing {self.outcome}/{self.completeness} from {self.tool_name}"
            )
        if self.outcome is not ExecutionOutcome.SUCCEEDED and (self.results or self.evidence_refs):
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


def legacy_status(result: ToolResult[object]) -> str:
    """TEMPORARY. Collapses the two axes back to the binary the old runtime reads.

    It exists so the old planner keeps working through the change and dies with that runtime. No
    new caller may use it: collapsing here is exactly the loss the two axes exist to prevent,
    because an unreachable source and a source that answered with nothing both become "error" and
    "ok" respectively, and the distinction is gone.
    """
    return "ok" if result.outcome is ExecutionOutcome.SUCCEEDED else "error"
