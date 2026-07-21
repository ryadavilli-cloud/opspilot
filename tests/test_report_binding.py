"""5a — the published report is a typed, frozen IncidentReport bound by a content hash.

Proves the report is immutable, its hash is deterministic, and the bytes an approval is bound to are
exactly the bytes finalize publishes (the property the real HITL interrupt in 5c will enforce). All
ML-free: the report nodes are exercised on a hand-built state, no retrieval or model needed.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opspilot.contracts import IncidentReport
from opspilot.diagnosis.contracts import EvidenceCitation, Hypothesis
from opspilot.nodes.investigation import (
    apply_edit,
    finalize_report,
    hitl_gate,
    synthesize_report,
)
from opspilot.state import EvidenceItem, InvestigationState


def _state_with_evidence() -> InvestigationState:
    hyp = Hypothesis(
        statement="deployment regression in checkout-api",
        confidence=0.8,
        citations=[EvidenceCitation(source="deploys", ref="deploys:checkout-api:d1", note="")],
    )
    ev = EvidenceItem.make("deploys", "deploys:checkout-api:d1", "deploy d1 at 10:02")
    return InvestigationState(
        incident_id="inc-006", severity="SEV2", category="deployment",
        hypothesis=hyp, evidence_by_id={ev.content_hash: ev},
    )


def test_synthesize_emits_a_typed_report_and_its_hash():
    out = synthesize_report(_state_with_evidence())
    report = out["report"]
    assert isinstance(report, IncidentReport)
    assert report.incident_id == "inc-006" and report.citations
    assert out["report_hash"] == report.content_hash()


def test_content_hash_is_deterministic_across_identical_reports():
    r1 = synthesize_report(_state_with_evidence())["report"]
    r2 = synthesize_report(_state_with_evidence())["report"]
    assert r1 == r2
    assert r1.content_hash() == r2.content_hash()


def test_report_is_frozen():
    report = synthesize_report(_state_with_evidence())["report"]
    with pytest.raises(ValidationError):
        report.hypothesis = "tampered"  # type: ignore[misc]


def test_editing_changes_the_hash():
    state = _state_with_evidence().model_copy(update=synthesize_report(_state_with_evidence()))
    original = state.report_hash
    edit = {"approval": {"decision": "edit", "edits": {"recommended_next_step": "roll back d1"}}}
    state = state.model_copy(update=edit)
    edited = apply_edit(state)
    assert edited["report"].recommended_next_step == "roll back d1"
    assert edited["report_hash"] != original  # a different report, a new hash
    assert edited["report_hash"] == edited["report"].content_hash()


def test_approved_bytes_equal_published_bytes():
    """synthesize -> approve (binds the hash) -> finalize publishes the byte-exact object."""
    state = _state_with_evidence()
    state = state.model_copy(update=synthesize_report(state))
    state = state.model_copy(update=hitl_gate(state))
    approved_hash = state.approval["approved_report_hash"]
    assert approved_hash == state.report_hash  # approval bound to what it saw

    published = finalize_report(state)
    assert published["report"].content_hash() == approved_hash  # published == approved, byte-exact
    assert published["report_hash"] == approved_hash
