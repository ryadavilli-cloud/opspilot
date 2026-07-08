"""Typed contracts for the deterministic tools.

Every tool takes a validated request and returns the uniform envelope `ToolResult`:
`{tool_name, status, results, evidence_refs, error, metadata}`. Records mirror the corpus;
`evidence_refs` use the frozen ref grammar (see data/answer_key/README.md) so a tool's output
resolves against the answer key. Evidence-bearing tools (deployments now; logs/metrics later)
populate `evidence_refs`; navigational record lookups may leave it empty.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

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


# --- requests (validated at the tool-service boundary) ----------------------------------------
class GetIncidentRequest(BaseModel):
    incident_id: str = Field(min_length=1)


class GetCorrelatedAlertsRequest(BaseModel):
    incident_id: str = Field(min_length=1)
    start_time: datetime | None = None
    end_time: datetime | None = None

    @model_validator(mode="after")
    def _check_window(self) -> GetCorrelatedAlertsRequest:
        if self.start_time and self.end_time and self.end_time < self.start_time:
            raise ValueError("end_time is before start_time")
        return self


class GetDeploymentsRequest(BaseModel):
    services: list[str] = Field(min_length=1)
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def _check_window(self) -> GetDeploymentsRequest:
        if self.end_time < self.start_time:
            raise ValueError("end_time is before start_time")
        if (self.end_time - self.start_time).days > MAX_WINDOW_DAYS:
            raise ValueError(f"time window exceeds {MAX_WINDOW_DAYS} days")
        return self


# --- uniform envelope -------------------------------------------------------------------------
class ToolMetadata(BaseModel):
    tool_name: str
    duration_ms: float
    result_count: int
    truncated: bool = False


class ToolResult[T](BaseModel):
    tool_name: str
    status: Literal["ok", "error"]
    results: list[T] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    error: str | None = None
    metadata: ToolMetadata
