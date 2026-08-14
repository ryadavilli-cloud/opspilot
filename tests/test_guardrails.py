"""Executable-guardrail tests (no ML stack required).

The two policies promoted into code now: read-only tools, and no unsupported hypothesis. Includes
the deliberately-unsupported hypothesis that must be rejected.
"""

from __future__ import annotations

from opspilot.contracts import IncidentReport
from opspilot.guardrails.policies import hypothesis_supported, is_read_only, unsupported_citations
from opspilot.nodes.investigation import apply_edit, safety_validate
from opspilot.router import after_approval, after_safety_validate
from opspilot.state import EvidenceItem, Intent, InvestigationState


def _evidence(source: str, ref: str, content: str = "") -> dict[str, EvidenceItem]:
    item = EvidenceItem.make(source, ref, content)
    return {item.content_hash: item}


def _report(citations: list[str], **overrides) -> IncidentReport:
    """A valid, typed report carrying the given citations — the state now holds a real
    IncidentReport, not a loose dict."""
    base: dict = dict(
        incident_id="inc-x",
        severity="SEV3",
        category="deployment",
        hypothesis="a deployment regression",
        confidence=0.5,
        evidence=[{"source": "logs", "ref": "logs:a:b", "content": "c"}],
        recommended_next_step="roll back",
        citations=citations,
    )
    base.update(overrides)
    return IncidentReport.model_validate(base)


def test_read_only_tool_policy():
    assert is_read_only("query_logs") and is_read_only("search_runbooks")
    assert not is_read_only("remediation_action")  # a future mutating tool is not allowed


def test_hypothesis_supported_accepts_grounded_citation():
    ok, violations = hypothesis_supported(["deploys:x:y"], {"deploys:x:y", "logs:a:b"})
    assert ok and not violations


def test_hypothesis_with_no_citations_is_rejected():
    ok, violations = hypothesis_supported([], {"logs:a:b"})
    assert not ok and violations


def test_invented_citation_is_flagged():
    assert unsupported_citations(["invented:ref"], {"logs:a:b"}) == ["invented:ref"]


def test_safety_validate_rejects_unsupported_report_and_escalates():
    state = InvestigationState(
        report=_report(["invented:ref"]),
        evidence_by_id=_evidence("logs", "logs:a:b"),
    )
    result = safety_validate(state)
    assert result["safety"]["passed"] is False and result["safety"]["violations"]
    assert after_safety_validate(state.model_copy(update=result)) == "escalate"


def test_safety_validate_passes_grounded_report():
    state = InvestigationState(
        report=_report(["logs:a:b"]),
        evidence_by_id=_evidence("logs", "logs:a:b"),
        produced_refs=["logs:a:b"],  # the citation was actually produced by a tool this run
    )
    result = safety_validate(state)
    assert result["safety"]["passed"] is True
    assert after_safety_validate(state.model_copy(update=result)) == "hitl_gate"


def test_info_only_reply_is_exempt_from_citation_gate():
    state = InvestigationState(intent=Intent.INFO_ONLY.value, report=_report([]))
    assert safety_validate(state)["safety"]["passed"] is True


def test_after_approval_routes_edit_to_revalidation_not_finalize():
    assert after_approval(InvestigationState(approval={"decision": "approve"})) == "finalize_report"
    assert after_approval(InvestigationState(approval={"decision": "edit"})) == "apply_edit"
    assert after_approval(InvestigationState(approval={"decision": "reject"})) == "escalate"
    assert after_approval(InvestigationState(approval=None)) == "escalate"  # fail closed


def test_edited_report_re_enters_validation_and_an_ungrounded_edit_is_caught():
    """The edit-revalidation fix: a human edit that cites something never produced this run must
    be rejected by safety_validate, not published — edit never shortcuts to finalize."""
    state = InvestigationState(
        report=_report(["logs:a:b"]),
        evidence_by_id=_evidence("logs", "logs:a:b"),
        approval={"decision": "edit", "edits": {"citations": ["invented:ref"]}},
    )
    edited = state.model_copy(update=apply_edit(state))
    assert edited.report.citations == ["invented:ref"]  # the edit was applied
    result = safety_validate(edited)
    assert result["safety"]["passed"] is False  # re-validation catches it
    assert after_safety_validate(edited.model_copy(update=result)) == "escalate"


def test_edit_that_preserves_grounding_passes_revalidation():
    state = InvestigationState(
        report=_report(["logs:a:b"]),
        evidence_by_id=_evidence("logs", "logs:a:b"),
        produced_refs=["logs:a:b"],
        approval={"decision": "edit", "edits": {"recommended_next_step": "roll back the deploy"}},
    )
    edited = state.model_copy(update=apply_edit(state))
    result = safety_validate(edited)
    assert result["safety"]["passed"] is True
    assert after_safety_validate(edited.model_copy(update=result)) == "hitl_gate"


# --- escalation attribution -------------------------------------------------------------------
# The blocking node names the cause; `escalate` reports what it was told. The old `escalate`
# inferred the cause by probing state in a fixed order, so a citation-gate block (which set
# nothing) surfaced as an exhausted iteration budget: specific, confident, and wrong.
def test_a_guardrail_block_escalates_with_a_guardrail_reason_not_a_budget_reason():
    from opspilot.config import MAX_DIAGNOSE_ITERS
    from opspilot.diagnosis.contracts import SufficiencyState
    from opspilot.nodes.investigation import escalate

    # State that would ALSO satisfy both budget probes the old inference tried first, so a wrong
    # attribution is observable rather than merely possible.
    state = InvestigationState(
        report=_report(["invented:ref"]),
        produced_refs=["logs:a:b"],
        diagnose_iters=MAX_DIAGNOSE_ITERS,
        sufficiency=SufficiencyState(
            evidence_classes=[],
            required_classes=["logs"],
            evidence_coverage=0.0,
            citation_coverage=0.0,
            plan_can_advance=False,
        ),
    )
    blocked = state.model_copy(update=safety_validate(state))
    assert after_safety_validate(blocked) == "escalate"

    reason = escalate(blocked)["error"]
    assert reason.startswith("guardrail_blocked: unsupported_citations")
    assert "iteration_budget_exhausted" not in reason
    assert "plan_exhausted_insufficient" not in reason


def test_escalate_reports_the_stamped_reason_verbatim():
    from opspilot.nodes.investigation import escalate

    stamped = InvestigationState(error="human_rejected by entra_jwt:oid-1")
    assert escalate(stamped)["error"] == "human_rejected by entra_jwt:oid-1"


def test_an_unstamped_escalation_is_reported_as_a_defect_not_a_plausible_guess():
    """The fallback must be obviously wrong, not plausibly right. A generic 'escalated to human'
    reads as a real cause and hides the missing stamp; this one names the defect."""
    from opspilot.nodes.investigation import escalate

    assert escalate(InvestigationState())["error"].startswith("unattributed_escalation")
