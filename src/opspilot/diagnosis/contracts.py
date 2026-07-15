"""Durable contracts for the diagnostic cycle — frozen before an LLM is placed inside them."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceCitation(BaseModel):
    """A reference to evidence produced during this run. `ref` uses the frozen grammar."""

    source: str          # logs | metrics | deploys | deps | runbook | past_incident
    ref: str
    note: str = ""       # why it supports the hypothesis


class ToolCallRequest(BaseModel):
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)


class DiagnosticQuestion(BaseModel):
    """A thing to find out, and the approved tool call that answers it. `key` is stable so a
    re-entered loop can tell which questions are already answered and never re-ask them."""

    key: str
    question: str
    call: ToolCallRequest


class ToolObservation(BaseModel):
    """The result of executing one diagnostic question's tool call."""

    question: str
    tool: str
    status: str
    evidence_refs: list[str]
    result_count: int


class Hypothesis(BaseModel):
    statement: str
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class StopReason(BaseModel):
    reason: Literal["hypothesis_supported", "iteration_limit", "no_more_questions"]
    detail: str = ""


class SufficiencyState(BaseModel):
    """Deterministic inputs to the stop rule — code decides when the agent may stop, not model
    confidence. Computed each diagnose turn over gathered evidence (see diagnosis.sufficiency).
    """

    evidence_classes: list[str]        # distinct source types gathered
    required_classes: list[str]        # what this severity requires (for the audit trail)
    evidence_coverage: float = Field(ge=0.0, le=1.0)   # severity-scaled; 1.0 == requirement met
    citation_coverage: float = Field(ge=0.0, le=1.0)   # cited refs that were produced
    contradictions_unresolved: int = 0
    unresolved_critical_questions: int = 0
    plan_can_advance: bool = True      # unanswered questions remain (more loops could add evidence)

    @property
    def ready(self) -> bool:
        """The agent is *allowed* to stop only when every deterministic dimension is satisfied."""
        return (
            self.evidence_coverage >= 1.0
            and self.citation_coverage >= 1.0
            and self.contradictions_unresolved == 0
            and self.unresolved_critical_questions == 0
        )


class InvestigationPlan(BaseModel):
    max_iters: int
    questions: list[DiagnosticQuestion] = Field(default_factory=list)


class DiagnosisContext(BaseModel):
    incident_id: str
    affected_services: list[str] = Field(default_factory=list)
    onset: str = ""       # ISO timestamp
    category: str = ""
