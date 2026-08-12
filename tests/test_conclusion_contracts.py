"""Conclusion contracts (Stage 5e) — the typed claim shapes the 6b checks validate and the report
is rendered from. These assert the CONTRACTS only (validation, defaults, discrimination); wiring the
synthesis path to produce them, and rendering prose from them, land in the following 5e slices.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from opspilot.contracts import (
    EscalationNotice,
    GroundedRcaReport,
    IncidentReport,
    InvestigationResult,
    KnowledgeBriefing,
    PartialInvestigationReport,
)
from opspilot.diagnosis.contracts import (
    Acknowledgement,
    CausalClaim,
    EvidenceCitation,
    OnsetWindow,
    ReportClaim,
)

_RESULT: TypeAdapter[Any] = TypeAdapter(InvestigationResult)


def _report() -> IncidentReport:
    return IncidentReport(
        incident_id="inc-004",
        severity="SEV2",
        category="latency",
        hypothesis="payment-api timeouts drove checkout-api 500s",
        confidence=0.8,
        evidence=[],
        recommended_next_step="roll back the payment-api deploy",
        citations=["deploys:dep-12"],
    )


def _causal() -> CausalClaim:
    return CausalClaim(
        cause_type="deployment",
        cause_entity="payment-api",
        cause_event_ref="deploys:dep-12",
        onset_window=OnsetWindow(start="2026-07-01T09:00:00Z"),
        affected_entities=["checkout-api"],
        support_refs=["deploys:dep-12", "metrics:m-1"],
        counter_refs=[],
    )


# --- EvidenceCitation.role ---------------------------------------------------------------------


def test_citation_role_defaults_to_context():
    # An unlabelled citation is neutral — never silently treated as causal support.
    assert EvidenceCitation(source="metrics", ref="metrics:m-1").role == "context"


def test_citation_accepts_the_four_roles():
    for role in ("cause", "effect", "baseline", "context"):
        assert EvidenceCitation(source="metrics", ref="metrics:m-1", role=role).role == role


def test_citation_rejects_unknown_role():
    with pytest.raises(ValidationError):
        EvidenceCitation(source="metrics", ref="metrics:m-1", role="smoking_gun")


def test_baseline_role_citation_fixture_exists():
    # The 6b causal-order check's negative case, authored now: a baseline reading is NOT causal
    # support. Enforcement (rejecting it) is 6b; here we pin that the role is expressible.
    baseline = EvidenceCitation(source="metrics", ref="metrics:baseline-1", role="baseline")
    assert baseline.role == "baseline"


# --- CausalClaim -------------------------------------------------------------------------------


def test_causal_claim_validates():
    c = _causal()
    assert c.cause_entity == "payment-api"
    assert c.onset_window.end == ""  # point onset


def test_causal_claim_requires_onset_window():
    with pytest.raises(ValidationError):
        CausalClaim(cause_type="deployment", cause_entity="payment-api")  # type: ignore[call-arg]


def test_causal_claim_rejects_unknown_cause_type():
    with pytest.raises(ValidationError):
        CausalClaim(
            cause_type="sunspots",  # type: ignore[arg-type]
            cause_entity="payment-api",
            onset_window=OnsetWindow(start="2026-07-01T09:00:00Z"),
        )


# --- ReportClaim / Acknowledgement -------------------------------------------------------------


def test_report_claim_kind_is_constrained():
    ok = ReportClaim(
        kind="blast_radius", statement="checkout + orders impacted", support_refs=["metrics:m-1"]
    )
    assert ok.kind == "blast_radius"
    with pytest.raises(ValidationError):
        ReportClaim(kind="vibes", statement="x")  # type: ignore[arg-type]


def test_acknowledgement_disposition_is_constrained():
    ack = Acknowledgement(contradiction_id="c-1", disposition="qualified")
    assert ack.disposition == "qualified"
    with pytest.raises(ValidationError):
        Acknowledgement(contradiction_id="c-1", disposition="whatever")  # type: ignore[arg-type]


# --- InvestigationResult discriminated union ---------------------------------------------------


def test_grounded_rca_is_the_only_variant_carrying_a_causal_claim():
    res = GroundedRcaReport(report=_report(), causal=_causal())
    parsed = _RESULT.validate_python(res.model_dump())
    assert isinstance(parsed, GroundedRcaReport)
    assert parsed.causal.cause_entity == "payment-api"


def test_union_discriminates_by_result_type():
    esc = _RESULT.validate_python(
        {"result_type": "escalation", "incident_id": "inc-004", "reason": "budget"}
    )
    assert isinstance(esc, EscalationNotice)
    partial = _RESULT.validate_python(
        {"result_type": "partial", "incident_id": "inc-004", "summary": "gathered, inconclusive"}
    )
    assert isinstance(partial, PartialInvestigationReport)
    brief = _RESULT.validate_python(
        {"result_type": "knowledge_briefing", "incident_id": "inc-004", "answer": "see rb-1"}
    )
    assert isinstance(brief, KnowledgeBriefing)


def test_union_rejects_unknown_variant():
    with pytest.raises(ValidationError):
        _RESULT.validate_python({"result_type": "miracle", "incident_id": "inc-004"})


def test_degraded_rung_cannot_masquerade_as_grounded_rca():
    # A partial result dict has no CausalClaim; validating it as the union yields the PARTIAL type,
    # never a GroundedRcaReport — the ladder cannot ship a non-RCA answer under the RCA contract.
    parsed = _RESULT.validate_python(
        {"result_type": "partial", "incident_id": "inc-004", "summary": "no root cause"}
    )
    assert not isinstance(parsed, GroundedRcaReport)
