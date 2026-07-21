"""Pydantic contracts — the validated shape of node outputs.

These are the deterministic safety net over LangGraph's silent-failure point: the
inter-node contract. If a node stops producing a well-formed report, the contract test
fails loudly instead of the demo failing quietly.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field


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
