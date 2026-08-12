"""Typed schemas for model responses.

The LLM's raw JSON is validated *through* these before any code acts on it: malformed output (wrong
types, an unknown intent) raises `ValidationError`, and the caller falls back closed. This keeps the
model's output at arm's length — the graph, not the model, decides what a valid action is.

Shapes match what the planner/triager already emit (a batch of tool calls, a single next_tool, a
`done` conclusion, a triage decision), so recorded cassettes validate and replay unchanged.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from opspilot.state import Intent


class ToolCallSpec(BaseModel):
    """One proposed tool call in a planner batch."""

    tool: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    why: str = ""


class PlannerResponse(BaseModel):
    """A diagnosis-planner turn: a tool-call batch, a single `next_tool`, or a `done` verdict."""

    tool_calls: list[ToolCallSpec] = Field(default_factory=list)
    next_tool: str | None = None  # single-call back-compat
    params: dict[str, Any] = Field(default_factory=dict)
    why: str = ""
    done: bool = False
    root_cause: str = ""
    citations: list[str] = Field(default_factory=list)


class CausalClaimResponse(BaseModel):
    """The model's PROPOSED structured causal claim (Stage 5e). Fields are loose (`str`) here —
    code ADMITS them into the strict `CausalClaim` (topology + Literal validation), falling back
    closed if the model proposes something inadmissible. Optional on `SynthesisResponse` so
    cassettes recorded before the synth prompt asked for it still validate and replay unchanged."""

    cause_type: str = ""
    cause_entity: str = ""
    cause_event_ref: str = ""
    onset_start: str = ""
    onset_end: str = ""
    affected_entities: list[str] = Field(default_factory=list)
    support_refs: list[str] = Field(default_factory=list)
    counter_refs: list[str] = Field(default_factory=list)


class ReportClaimResponse(BaseModel):
    """A proposed secondary report-level claim (Stage 5e); admitted into a typed `ReportClaim`."""

    kind: str = ""
    statement: str = ""
    support_refs: list[str] = Field(default_factory=list)


class SynthesisResponse(BaseModel):
    """The model's grounded conclusion. `root_cause`/`citations` are the original prose shape; the
    optional `causal`/`report_claims` are the Stage 5e structured claim (populated once the synth
    prompt asks for them — until then they stay empty and behaviour is unchanged)."""

    root_cause: str = ""
    citations: list[str] = Field(default_factory=list)
    causal: CausalClaimResponse | None = None
    report_claims: list[ReportClaimResponse] = Field(default_factory=list)


class TriageResponse(BaseModel):
    """A triage decision. `intent` is a closed set — an unknown value fails validation (fail-closed
    to novel_investigation in the caller)."""

    intent: Literal[
        Intent.KNOWN_ISSUE,
        Intent.NOVEL_INVESTIGATION,
        Intent.INFO_ONLY,
    ]
    matched_incident: str = ""
    why: str = ""
