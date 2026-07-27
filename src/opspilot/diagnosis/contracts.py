"""Durable contracts for the diagnostic cycle — frozen before an LLM is placed inside them."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceCitation(BaseModel):
    """A reference to evidence produced during this run. `ref` uses the frozen grammar."""

    source: str          # logs | metrics | deploys | deps | runbook | past_incident
    ref: str
    note: str = ""       # why it supports the hypothesis
    # The role this citation plays in the causal argument. The model PROPOSES a role; code ADMITS it
    # at Stage 6b (the role-admissibility check — a citation cannot carry a role its evidence type
    # cannot support). Defaults to the neutral "context" so an unlabelled citation is never silently
    # treated as causal support.
    role: Literal["cause", "effect", "baseline", "context"] = "context"


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
    summary: str = ""   # compact `signal [ref]` view of the results, for a model planner


class Hypothesis(BaseModel):
    statement: str
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[EvidenceCitation] = Field(default_factory=list)


# --- Conclusion contracts (Stage 5e) -----------------------------------------------------------
# The typed shape the deterministic checks (Stage 6b) validate and the report is RENDERED from. The
# root cause stops being a prose sentence and becomes a structured proposition, so the prose a human
# reads cannot disagree with the structure a check validates (G-50), and every published claim — not
# just the headline root cause — is grounded in produced refs (G-51/G-29).


class OnsetWindow(BaseModel):
    """The window over which the incident's effect onset is observed. Half-open [start, end);
    an empty `end` means a point onset / still ongoing. ISO-8601, tz-aware UTC."""

    start: str
    end: str = ""


class CausalClaim(BaseModel):
    """The single structured causal proposition. Stage 6b's contradiction / causal-order /
    entity-support checks compare THESE typed fields (not prose); `cause_entity` is topology-
    validated there. The support/counter split makes the evidence *for* and the evidence that would
    *refute* the claim both first-class, instead of a flat citation list."""

    cause_type: Literal[
        "deployment", "dependency_failure", "resource_exhaustion",
        "config_change", "external", "unknown",
    ]
    cause_entity: str                          # a service / resource / dependency edge
    cause_event_ref: str = ""                  # ref of the causing event (e.g. a deploy), if any
    onset_window: OnsetWindow
    affected_entities: list[str] = Field(default_factory=list)
    support_refs: list[str] = Field(default_factory=list)
    counter_refs: list[str] = Field(default_factory=list)


class Acknowledgement(BaseModel):
    """A contradiction the reviewer is asked to accept, carried as a structured caveat rather than
    buried in report prose (so the HITL gate can surface it as an individually-acceptable item, §8).
    Which contradictions are acknowledgeable, and the confidence cap, are admission policy at 6b."""

    contradiction_id: str
    disposition: Literal["qualified", "inconclusive"]
    detail: str = ""
    support_refs: list[str] = Field(default_factory=list)
    counter_refs: list[str] = Field(default_factory=list)


class ReportClaim(BaseModel):
    """A secondary, structured report-level claim, so every published claim is grounded — not just
    the root cause (G-51). `statement` is RENDERED from the structured fields (template
    substitution, not generation) at 6b; `support_refs` must resolve against produced refs."""

    kind: Literal[
        "onset", "blast_radius", "sequence", "contributing_factor", "ruled_out", "recommendation"
    ]
    statement: str
    support_refs: list[str] = Field(default_factory=list)


class Conclusion(BaseModel):
    """What the planner produces when the loop stops reasoning: the prose hypothesis the report has
    always carried, plus the typed claim the 6b checks interrogate.

    `causal` is None whenever the model proposed nothing admissible. That is a real outcome, not an
    error: an unsupported or entity-unresolvable claim must NOT become a `GroundedRcaReport`, and
    the caller degrades rather than publishing a structure code could not admit.
    """

    hypothesis: Hypothesis
    causal: CausalClaim | None = None
    report_claims: list[ReportClaim] = Field(default_factory=list)


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
