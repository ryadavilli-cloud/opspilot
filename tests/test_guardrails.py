"""Executable-guardrail tests (no ML stack required).

The two policies promoted into code now: read-only tools, and no unsupported hypothesis. Includes
the deliberately-unsupported hypothesis that must be rejected.
"""

from __future__ import annotations

from opspilot.guardrails.policies import hypothesis_supported, is_read_only, unsupported_citations
from opspilot.nodes.investigation import safety_validate
from opspilot.router import after_safety_validate
from opspilot.state import Intent


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
    state = {
        "report": {"citations": ["invented:ref"]},
        "evidence": [{"source": "logs", "ref": "logs:a:b", "content": ""}],
    }
    result = safety_validate(state)
    assert result["safety"]["passed"] is False and result["safety"]["violations"]
    assert after_safety_validate({**state, **result}) == "escalate"


def test_safety_validate_passes_grounded_report():
    state = {
        "report": {"citations": ["logs:a:b"]},
        "evidence": [{"source": "logs", "ref": "logs:a:b", "content": ""}],
    }
    result = safety_validate(state)
    assert result["safety"]["passed"] is True
    assert after_safety_validate({**state, **result}) == "hitl_gate"


def test_info_only_reply_is_exempt_from_citation_gate():
    state = {"intent": Intent.INFO_ONLY.value, "report": {"citations": []}, "evidence": []}
    assert safety_validate(state)["safety"]["passed"] is True
