"""Stage 5e wiring: admission, rendering, and the typed result union.

Slice 1 froze the conclusion contracts; this covers what happens to them at runtime. The three
properties under test are the ones the gaps name: a proposed claim is admitted by code rather than
trusted (G-29), the published prose is rendered from the admitted structure so the two cannot
disagree (G-50), and a run's outcome carries a variant tag so a consumer can tell a grounded RCA
from a briefing or an escalation without reading prose (G-49).
"""

from __future__ import annotations

from opspilot.contracts import IncidentReport
from opspilot.diagnosis.admission import (
    admit_causal_claim,
    admit_report_claims,
    entities_from_refs,
)
from opspilot.diagnosis.contracts import CausalClaim, OnsetWindow, ReportClaim
from opspilot.diagnosis.render import render_causal_statement, render_report_claim_statement
from opspilot.llm.schema import CausalClaimResponse, ReportClaimResponse
from opspilot.state import Intent

_REFS = {"metrics:payment-api:p95@t1", "deploys:checkout-api:d-9", "deps:checkout-api->payment-api"}


def _proposed(**overrides) -> CausalClaimResponse:
    base = dict(
        cause_type="dependency_failure",
        cause_entity="payment-api",
        cause_event_ref="",
        onset_start="2026-03-01T10:00:00+00:00",
        onset_end="",
        affected_entities=["checkout-api"],
        support_refs=["metrics:payment-api:p95@t1"],
        counter_refs=[],
    )
    return CausalClaimResponse(**{**base, **overrides})


# --- entity resolution --------------------------------------------------------------------------
def test_entities_are_read_out_of_the_frozen_ref_grammar():
    assert entities_from_refs(_REFS) == {"payment-api", "checkout-api"}


def test_refs_that_name_no_service_contribute_no_entity():
    """A runbook cannot be a cause entity, so `runbook:` and `past_incident:` refs contribute
    nothing to the resolvable set."""
    assert entities_from_refs({"runbook:rb-1", "past_incident:inc-002"}) == set()


# --- admission (G-29) ---------------------------------------------------------------------------
def test_a_grounded_claim_is_admitted_into_the_strict_contract():
    claim = admit_causal_claim(
        _proposed(), produced_refs=_REFS, known_entities=entities_from_refs(_REFS)
    )
    assert isinstance(claim, CausalClaim)
    assert claim.cause_type == "dependency_failure"
    assert claim.support_refs == ["metrics:payment-api:p95@t1"]


def test_an_unresolvable_entity_is_refused():
    assert (
        admit_causal_claim(
            _proposed(cause_entity="invented-service"),
            produced_refs=_REFS,
            known_entities=entities_from_refs(_REFS),
        )
        is None
    )


def test_a_claim_with_no_produced_support_ref_is_refused():
    """A deterministic check over a model-controlled input is deterministic in form only. A claim
    supported by nothing this run produced must not become a grounded RCA."""
    assert (
        admit_causal_claim(
            _proposed(support_refs=["metrics:ghost:invented@t"]),
            produced_refs=_REFS,
            known_entities=entities_from_refs(_REFS),
        )
        is None
    )


def test_an_unrecognized_cause_type_degrades_to_unknown_rather_than_failing_the_claim():
    """'We could not classify the mechanism' is honest and still carries grounded refs; an
    unresolvable entity is not, which is why only the latter fails the whole claim."""
    claim = admit_causal_claim(
        _proposed(cause_type="sunspots"),
        produced_refs=_REFS,
        known_entities=entities_from_refs(_REFS),
    )
    assert claim is not None and claim.cause_type == "unknown"


def test_an_unproduced_cause_event_ref_is_dropped_not_carried():
    claim = admit_causal_claim(
        _proposed(cause_event_ref="deploys:ghost:d-1"),
        produced_refs=_REFS,
        known_entities=entities_from_refs(_REFS),
    )
    assert claim is not None and claim.cause_event_ref == ""


def test_ungrounded_report_claims_are_dropped():
    """G-51: every published claim cites produced evidence, not just the headline root cause."""
    admitted = admit_report_claims(
        [
            ReportClaimResponse(kind="onset", statement="a", support_refs=["metrics:ghost:x@t"]),
            ReportClaimResponse(
                kind="blast_radius", statement="b", support_refs=["deploys:checkout-api:d-9"]
            ),
            ReportClaimResponse(kind="not_a_kind", statement="c", support_refs=list(_REFS)),
        ],
        produced_refs=_REFS,
    )
    assert [c.kind for c in admitted] == ["blast_radius"]


# --- rendering (G-50) ---------------------------------------------------------------------------
def test_the_rendered_statement_can_only_name_the_claimed_entity():
    claim = CausalClaim(
        cause_type="deployment",
        cause_entity="checkout-api",
        onset_window=OnsetWindow(start="2026-03-01T10:00:00+00:00"),
        affected_entities=["checkout-api", "cart-api"],
        support_refs=["deploys:checkout-api:d-9"],
    )
    rendered = render_causal_statement(claim)
    assert "checkout-api" in rendered and "deployment" in rendered
    assert "cart-api" in rendered  # affected entities are disclosed, not hidden
    assert rendered.endswith(".")


def test_every_cause_type_renders_a_sentence_naming_the_entity():
    """A new Literal member without a template must not render an empty or misleading sentence."""
    for cause_type in (
        "deployment",
        "dependency_failure",
        "resource_exhaustion",
        "config_change",
        "external",
        "unknown",
    ):
        claim = CausalClaim(
            cause_type=cause_type,  # type: ignore[arg-type]
            cause_entity="svc-a",
            onset_window=OnsetWindow(start=""),
            support_refs=["logs:svc-a:1"],
        )
        assert "svc-a" in render_causal_statement(claim)


def test_a_report_claim_renders_its_kind_and_its_supporting_refs():
    rendered = render_report_claim_statement(
        ReportClaim(kind="ruled_out", statement="not the cache", support_refs=["logs:svc-a:1"])
    )
    assert rendered.startswith("Ruled out:")
    assert "logs:svc-a:1" in rendered


# --- the result union (G-49) --------------------------------------------------------------------
def _report(**overrides) -> IncidentReport:
    base: dict = dict(
        incident_id="inc-004",
        severity="SEV2",
        category="deployment",
        hypothesis="h",
        confidence=0.7,
        evidence=[],
        recommended_next_step="s",
        citations=["logs:svc-a:1"],
    )
    return IncidentReport.model_validate({**base, **overrides})


def _outcome(state: dict, report=None, *, status="completed", reason=None):
    from opspilot.api import _build_outcome

    return _build_outcome(state, report, status=status, reason=reason)


def test_a_run_with_an_admitted_claim_is_a_grounded_rca():
    claim = CausalClaim(
        cause_type="deployment",
        cause_entity="checkout-api",
        onset_window=OnsetWindow(start=""),
        support_refs=["deploys:checkout-api:d-9"],
    )
    outcome = _outcome({"incident_id": "inc-004", "causal": claim}, _report())
    assert outcome.result_type == "grounded_rca"
    assert outcome.causal.cause_entity == "checkout-api"


def test_a_completed_run_without_a_claim_is_partial_not_a_grounded_rca():
    """The deterministic floor lands here by design. It has a report and passed the citation gate,
    but nothing structured was verified, so calling it a grounded RCA would be the euphemism the
    union exists to prevent."""
    outcome = _outcome({"incident_id": "inc-004", "causal": None}, _report())
    assert outcome.result_type == "partial"
    assert "no structured causal claim" in outcome.reason


def test_an_escalated_run_carries_the_machine_readable_reason():
    outcome = _outcome(
        {"incident_id": "inc-004"}, None, status="escalated", reason="guardrail_blocked: x"
    )
    assert outcome.result_type == "escalation"
    assert outcome.reason == "guardrail_blocked: x"


def test_an_info_only_reply_is_a_briefing_never_an_rca():
    outcome = _outcome({"incident_id": "inc-004", "intent": Intent.INFO_ONLY.value}, _report())
    assert outcome.result_type == "knowledge_briefing"
