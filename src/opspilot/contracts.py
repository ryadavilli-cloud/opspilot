"""Pydantic contracts — the validated shape of node outputs.

These are the deterministic safety net over LangGraph's silent-failure point: the
inter-node contract. If a node stops producing a well-formed report, the contract test
fails loudly instead of the demo failing quietly.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    source: str
    ref: str
    content: str


class IncidentReport(BaseModel):
    incident_id: str
    severity: str
    category: str
    hypothesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceItem]
    recommended_next_step: str
    citations: list[str]
