"""Sufficiency gate + fail-closed routing (no ML stack required).

Code decides when the diagnosis loop may stop. These tests pin the deterministic stop rule: the
severity-scaled coverage, the ready truth table (each dimension independently blocks), and the
fail-closed router branches.
"""

from __future__ import annotations

from opspilot.diagnosis.contracts import EvidenceCitation, Hypothesis, SufficiencyState
from opspilot.diagnosis.sufficiency import compute_sufficiency, evidence_class
from opspilot.router import after_safety_validate, diagnose_continue
from opspilot.state import InvestigationState


def _suff(**over) -> SufficiencyState:
    base = dict(evidence_classes=["logs"], required_classes=[">=1"], evidence_coverage=1.0,
                citation_coverage=1.0, contradictions_unresolved=0,
                unresolved_critical_questions=0, plan_can_advance=False)
    base.update(over)
    return SufficiencyState(**base)


# --- evidence class + severity scaling -------------------------------------------------------
def test_evidence_class_reads_the_ref_prefix():
    assert evidence_class("deploys:checkout-api:d1") == "deploys"
    assert evidence_class("metrics:payment-api:p95@2026-06-28T10:10:00Z") == "metrics"
    assert evidence_class("deps:checkout-api->payment-api") == "deps"


def test_sev1_requires_all_four_core_classes():
    two = compute_sufficiency("SEV1", {"logs:a:1", "deploys:a:1"}, None, False)
    assert two.evidence_coverage == 0.5 and not two.ready
    four = compute_sufficiency(
        "SEV1", {"logs:a:1", "metrics:a:m@t", "deps:a->b", "deploys:a:1"}, None, False)
    assert four.evidence_coverage == 1.0 and four.ready


def test_sev2_requires_two_classes_sev3_requires_one():
    assert compute_sufficiency("SEV2", {"logs:a:1"}, None, False).evidence_coverage == 0.5
    two = compute_sufficiency("SEV2", {"logs:a:1", "deps:a->b"}, None, False)
    assert two.evidence_coverage == 1.0
    assert compute_sufficiency("SEV3", {"logs:a:1"}, None, False).evidence_coverage == 1.0


def test_citation_coverage_flags_ungrounded_citation():
    hyp = Hypothesis(statement="x", confidence=0.8,
                     citations=[EvidenceCitation(source="logs", ref="invented:ref")])
    s = compute_sufficiency("SEV3", {"logs:a:1"}, hyp, False)
    assert s.citation_coverage == 0.0 and not s.ready


# --- ready truth table (each dimension independently blocks) ---------------------------------
def test_ready_only_when_every_dimension_passes():
    assert _suff().ready
    assert not _suff(evidence_coverage=0.5).ready
    assert not _suff(citation_coverage=0.5).ready
    assert not _suff(contradictions_unresolved=1).ready       # unresolved contradiction blocks
    assert not _suff(unresolved_critical_questions=1).ready


# --- router: sufficiency gate ----------------------------------------------------------------
def test_diagnose_continue_stops_when_ready():
    assert diagnose_continue(InvestigationState(sufficiency=_suff())) == "synthesize_report"


def test_diagnose_continue_escalates_when_plan_cannot_advance():
    s = _suff(evidence_coverage=0.5, plan_can_advance=False)
    assert diagnose_continue(InvestigationState(sufficiency=s, diagnose_iters=1)) == "escalate"


def test_diagnose_continue_loops_while_advancing_under_budget():
    s = _suff(evidence_coverage=0.5, plan_can_advance=True)
    assert diagnose_continue(InvestigationState(sufficiency=s, diagnose_iters=1)) == "diagnose"


def test_diagnose_continue_escalates_on_budget_exhaustion():
    s = _suff(evidence_coverage=0.5, plan_can_advance=True)
    assert diagnose_continue(InvestigationState(sufficiency=s, diagnose_iters=5)) == "escalate"


# --- router: fail-closed safety --------------------------------------------------------------
def test_after_safety_validate_fails_closed_on_missing_state():
    assert after_safety_validate(InvestigationState(safety=None)) == "escalate"
    assert after_safety_validate(InvestigationState(safety={})) == "escalate"


def test_after_safety_validate_routes_on_verdict():
    assert after_safety_validate(InvestigationState(safety={"passed": True})) == "hitl_gate"
    assert after_safety_validate(InvestigationState(safety={"passed": False})) == "escalate"
