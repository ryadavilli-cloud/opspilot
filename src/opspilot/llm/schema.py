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
    next_tool: str | None = None            # single-call back-compat
    params: dict[str, Any] = Field(default_factory=dict)
    why: str = ""
    done: bool = False
    root_cause: str = ""
    citations: list[str] = Field(default_factory=list)


class SynthesisResponse(BaseModel):
    """The model's grounded conclusion."""

    root_cause: str = ""
    citations: list[str] = Field(default_factory=list)


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
