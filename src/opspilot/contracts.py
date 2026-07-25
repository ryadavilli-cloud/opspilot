"""Pydantic contracts — the validated shape of node outputs.

These are the deterministic safety net over LangGraph's silent-failure point: the
inter-node contract. If a node stops producing a well-formed report, the contract test
fails loudly instead of the demo failing quietly.
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from opspilot.diagnosis.contracts import Acknowledgement, CausalClaim, ReportClaim


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    ref: str
    content: str


class IncidentReport(BaseModel):
    """The published investigation report. Frozen so the object an approver signs off on cannot be
    mutated in place after its hash is taken — an edit produces a NEW report (and a new hash), which
    is what lets an approval be bound to exact bytes (the HITL stage rejects a stale/mismatched
    approval)."""

    model_config = ConfigDict(frozen=True)

    incident_id: str
    severity: str
    category: str
    hypothesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceItem]
    recommended_next_step: str
    citations: list[str]

    def content_hash(self) -> str:
        """Stable sha256 over the report's canonical JSON — the identity an approval binds to.

        `model_dump_json()` is deterministic (field-definition order, no whitespace), so the same
        report content always hashes the same across processes, and any change to any field — a
        reviewer edit, a re-synthesis — changes the hash.
        """
        return hashlib.sha256(self.model_dump_json().encode("utf-8")).hexdigest()


# --- InvestigationResult: the discriminated result union (Stage 5e, G-49) ----------------------
# A run's outcome is one of four DISTINCT types, tagged by `result_type`. Only a fully grounded RCA
# carries a CausalClaim; the degraded rungs (partial / knowledge-only) get their own types so the
# degradation ladder (Stage 10) can never ship a non-RCA answer under the RCA contract. Today's runs
# produce only `grounded_rca` and `escalation`; the middle two are defined now so nothing has to be
# retyped when Stage 10 builds the rungs that return them.


class GroundedRcaReport(BaseModel):
    """A full, grounded root-cause report — the ONLY variant that carries a `CausalClaim`."""

    result_type: Literal["grounded_rca"] = "grounded_rca"
    report: IncidentReport
    causal: CausalClaim
    report_claims: list[ReportClaim] = Field(default_factory=list)
    acknowledgements: list[Acknowledgement] = Field(default_factory=list)


class PartialInvestigationReport(BaseModel):
    """A degraded rung: evidence was gathered but no grounded root cause was reached (Stage 10)."""

    result_type: Literal["partial"] = "partial"
    incident_id: str
    summary: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    reason: str = ""


class KnowledgeBriefing(BaseModel):
    """A degraded rung: a knowledge / `info_only` answer, explicitly NOT an RCA (Stage 10)."""

    result_type: Literal["knowledge_briefing"] = "knowledge_briefing"
    incident_id: str
    answer: str
    citations: list[str] = Field(default_factory=list)


class EscalationNotice(BaseModel):
    """The run stopped and handed off to a human, carrying a machine-readable reason (G-36)."""

    result_type: Literal["escalation"] = "escalation"
    incident_id: str
    reason: str


InvestigationResult = Annotated[
    GroundedRcaReport | PartialInvestigationReport | KnowledgeBriefing | EscalationNotice,
    Field(discriminator="result_type"),
]
