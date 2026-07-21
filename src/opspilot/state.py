"""Incident investigation state — the typed, versioned contract between graph nodes.

Migrated from a `TypedDict` to a Pydantic model so schema validation is real, and so the
seams an LLM will later plug into are frozen and correct (see docs/code-guidelines §4/§7):

- **Separated identifiers.** `incident_id` (business) is distinct from `investigation_id`
  (one attempt, minted at ingest) and `thread_id` (derived from it). A reopened or rerun
  incident can no longer overwrite or resume the wrong graph state.
- **Keyed, deduplicated evidence.** `evidence_by_id` is a dict keyed by content hash with a
  merge reducer, replacing the old `list + operator.add` channel that appended the same
  reference on every diagnose re-entry (observed 5x duplication). Distinct hashes are never
  collapsed, so contradictory observations survive.
- **One source of truth.** The hypothesis (statement + confidence + citations) lives only on
  `hypothesis: Hypothesis`; the old scalar `confidence` and the duplicated `diagnosis`
  hypothesis-dump are gone. `retrieved_sources` is derived from evidence, not stored.

`report` is a typed, frozen `IncidentReport` bound by a `report_hash` (5a). Approval / safety /
postmortem / alert stay as dicts here; each is typed when its own stage lands (approval at the
real-HITL stage). This model types the seams the pre-LLM hardening and report stages target, not
the whole future state.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from opspilot.contracts import IncidentReport
from opspilot.diagnosis.contracts import (
    Hypothesis,
    StopReason,
    SufficiencyState,
    ToolObservation,
)

_UNIT_SEP = "\x1f"


class Intent(StrEnum):
    KNOWN_ISSUE = "known_issue"
    NOVEL_INVESTIGATION = "novel_investigation"
    INFO_ONLY = "info_only"


def evidence_hash(source: str, ref: str, content: str) -> str:
    """Content hash for dedup + integrity: sha256 over the canonical `source|ref|content`.

    `content` is included so two observations sharing a ref but disagreeing on content get
    distinct keys and are never silently collapsed (contradictions must survive).
    """
    canonical = _UNIT_SEP.join((source, ref, content)).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class EvidenceItem(BaseModel):
    """A single piece of evidence produced by a tool during this run. `ref` uses the frozen
    grammar (`logs:<svc>:<id>`, `deploys:<svc>:<id>`, `runbook:<id>`, ...)."""

    source: str  # runbook | past_incident | logs | metrics | deploys | deps
    ref: str
    content: str = ""
    content_hash: str

    @classmethod
    def make(cls, source: str, ref: str, content: str = "") -> EvidenceItem:
        return cls(source=source, ref=ref, content=content,
                   content_hash=evidence_hash(source, ref, content))


def merge_evidence(
    existing: dict[str, EvidenceItem], incoming: dict[str, EvidenceItem]
) -> dict[str, EvidenceItem]:
    """Reducer: merge by content-hash key, first-seen wins. Associative and deterministic;
    dedups across loop re-entry and parallel branches without collapsing distinct hashes."""
    merged = dict(existing)
    for key, item in incoming.items():
        merged.setdefault(key, item)
    return merged


def merge_refs(existing: list[str], incoming: list[str]) -> list[str]:
    """Reducer: accumulate the tool-produced evidence-ref trail across diagnose turns. The LLM
    loop executes one question per turn, so a last-write field would drop earlier turns' evidence.
    Order-preserving union, so the grounding set only ever grows and stays deterministic."""
    seen = list(existing)
    known = set(existing)
    for ref in incoming:
        if ref not in known:
            seen.append(ref)
            known.add(ref)
    return seen


def append_observations(
    existing: list[ToolObservation], incoming: list[ToolObservation]
) -> list[ToolObservation]:
    """Reducer: accumulate the full observation trail across diagnose turns, so a model planner can
    see all it has already done (and not repeat calls). `diagnosis` holds only the last turn."""
    return existing + incoming


class DiagnosisTrace(BaseModel):
    """The observable trail of one diagnostic cycle — the tool observations and why it stopped.
    The hypothesis it produced is not duplicated here; it lives on the state's `hypothesis`."""

    observations: list[ToolObservation] = Field(default_factory=list)
    stop_reason: StopReason | None = None


class InvestigationState(BaseModel):
    schema_version: Literal["1.0"] = "1.0"

    # identifiers — separated (never conflate incident_id with thread_id)
    incident_id: str = ""
    investigation_id: str = ""   # one attempt; minted at ingest (UUID)
    thread_id: str = ""          # derived from investigation_id
    workflow_version: str = ""
    idempotency_key: str = ""

    alert: dict[str, Any] = Field(default_factory=dict)  # raw ingested event (typed later)
    severity: str | None = None
    category: str | None = None
    intent: str | None = None
    matched_incident: str = ""   # a past match (candidate + verification lands with the fast path)

    affected_services: list[str] = Field(default_factory=list)
    onset: str = ""              # earliest alert/incident time (ISO)
    triage: dict[str, Any] = Field(default_factory=dict)

    # keyed collection — dedup by content hash, never blind-append
    evidence_by_id: Annotated[dict[str, EvidenceItem], merge_evidence] = Field(default_factory=dict)

    # the tool-produced evidence-ref trail (accumulated across diagnose turns) — the grounding set
    # the safety guardrail validates a hypothesis's citations against. Distinct from evidence_by_id
    # (built from the *cited* refs): a hypothesis may only cite what a tool actually produced.
    produced_refs: Annotated[list[str], merge_refs] = Field(default_factory=list)

    hypothesis: Hypothesis | None = None       # single source of truth (statement/confidence/cites)
    diagnosis: DiagnosisTrace | None = None    # observations + stop reason (last turn only)
    # full observation history across turns — what a model planner sees so it never repeats a call
    observation_trail: Annotated[list[ToolObservation], append_observations] = Field(
        default_factory=list)
    sufficiency: SufficiencyState | None = None  # deterministic stop-rule inputs (per turn)
    answered_questions: list[str] = Field(default_factory=list)  # plan-advancement: keys asked
    diagnose_iters: int = 0

    # The published report is a typed, frozen IncidentReport (5a); report_hash is its content hash,
    # recomputed on synthesis and on every edit, so an approval can be bound to exact report bytes.
    report: IncidentReport | None = None
    report_hash: str = ""
    safety: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    postmortem: dict[str, Any] | None = None

    degraded: bool = False
    error: str = ""

    def evidence_refs(self) -> list[str]:
        """Derive the produced-reference list from evidence (the single source), preserving
        insertion order — replaces the old separately-stored `retrieved_sources` channel."""
        return [item.ref for item in self.evidence_by_id.values()]
