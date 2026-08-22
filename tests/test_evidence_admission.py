"""The two axes, and admission as the only door into the evidence set.

The distinction this suite exists to protect is `succeeded + empty` against `unavailable`. A
source that answered authoritatively with nothing and a source that never answered must stay
separately representable, separately admitted, and separately visible, because collapsing them
turns an unreachable source into a clean bill of health.

The second thing it protects is citability. Every capability that can produce an observation must
produce one carrying a reference that parses and resolves, including the two forms with no stored
row behind them: an authoritative absence and an aggregate.
"""

from __future__ import annotations

import pytest
from fake_operational_records import corpus_records
from pydantic import ValidationError

from opspilot.evidence.admission import CAPABILITY_EVIDENCE_TYPES, EvidenceType, admit
from opspilot.evidence.operations import EvidenceSet, is_operation_ref
from opspilot.evidence.references import ReferenceResolver, ReferenceType, try_parse
from opspilot.tools import CAPABILITY_NAMES
from opspilot.tools.contracts import (
    Completeness,
    ExecutionOutcome,
    ToolMetadata,
    ToolResult,
)
from opspilot.tools.service import ToolService


def _meta(name: str, count: int = 0) -> ToolMetadata:
    return ToolMetadata(tool_name=name, duration_ms=1.0, result_count=count)


def _result(name: str, outcome: ExecutionOutcome, completeness: Completeness, **kw) -> ToolResult:
    return ToolResult(
        tool_name=name, outcome=outcome, completeness=completeness, metadata=_meta(name), **kw
    )


def _evidence() -> EvidenceSet:
    return EvidenceSet(investigation_id="inv-1")


# --- the one pairing rule -------------------------------------------------------------------
def test_a_non_answering_result_cannot_carry_content():
    """Content on a failed outcome is how fabricated evidence would get in."""
    with pytest.raises(ValidationError):
        _result(
            "query_logs",
            ExecutionOutcome.UNAVAILABLE,
            Completeness.NOT_APPLICABLE,
            evidence_refs=["logs:a:e1"],
        )


@pytest.mark.parametrize(
    "outcome", [o for o in ExecutionOutcome if o is not ExecutionOutcome.SUCCEEDED]
)
def test_a_call_that_did_not_answer_has_no_completeness_to_describe(outcome):
    assert _result("query_logs", outcome, Completeness.NOT_APPLICABLE).answered is False
    with pytest.raises(ValidationError):
        _result("query_logs", outcome, Completeness.COMPLETE)


def test_an_answer_always_has_a_completeness():
    """The other half of the same rule. A succeeded result that declined to say how complete it
    was would let an empty answer and a full one read alike."""
    with pytest.raises(ValidationError):
        _result("query_logs", ExecutionOutcome.SUCCEEDED, Completeness.NOT_APPLICABLE)


# --- the distinction that matters ---------------------------------------------------------------
def test_empty_is_admitted_as_a_positive_observation():
    evidence = _evidence()
    admitted = admit(
        _result("query_logs", ExecutionOutcome.SUCCEEDED, Completeness.EMPTY),
        evidence=evidence,
        question="were there errors for payment-api in the window",
        request_scope={"service": "payment-api"},
    )
    observation = admitted[0]
    assert observation.is_authoritative_absence
    assert "payment-api" in str(observation.observation)
    assert evidence.limitations == []


def test_an_absence_is_assigned_a_canonical_evidence_reference():
    """It must be citable. A reference that is only an operation identifier would make the finding
    uncitable, because an operation names an attempt rather than an observation."""
    evidence = _evidence()
    observation = admit(
        _result("get_deployments", ExecutionOutcome.SUCCEEDED, Completeness.EMPTY),
        evidence=evidence,
        question="did anything change before the incident",
        request_scope={"service": "payment-api"},
    )[0]
    operation_ref = evidence.operations[-1].operation_ref

    assert observation.evidence_ref == f"absence:get_deployments:{operation_ref}"
    parsed = try_parse(observation.evidence_ref)
    assert parsed is not None and parsed.reference_type is ReferenceType.EVIDENCE
    assert parsed.capability == "get_deployments"
    assert parsed.identifier == operation_ref


def test_an_aggregate_is_citable_by_the_operation_that_produced_it():
    """A count is a fact about a scope and has no underlying row, so nothing else could carry the
    citation. Leaving it uncited would make a counted answer unusable in an assessment."""
    evidence = _evidence()
    observation = admit(
        _result(
            "structured_query",
            ExecutionOutcome.SUCCEEDED,
            Completeness.COMPLETE,
            results=[{"count": 7}],
        ),
        evidence=evidence,
        question="how many prior incidents named this category",
    )[0]
    operation_ref = evidence.operations[-1].operation_ref

    assert observation.evidence_ref == f"query:{operation_ref}"
    parsed = try_parse(observation.evidence_ref)
    assert parsed is not None and parsed.reference_type is ReferenceType.EVIDENCE
    assert parsed.identifier == operation_ref
    assert observation.observation == [{"count": 7}]


def test_the_operation_reference_stays_distinct_from_the_evidence_reference():
    """The absence reference embeds the operation reference; it does not replace it, and the bare
    operation reference must remain uncitable."""
    evidence = _evidence()
    observation = admit(
        _result("get_deployments", ExecutionOutcome.SUCCEEDED, Completeness.EMPTY),
        evidence=evidence,
        question="did anything change before the incident",
    )[0]
    operation_ref = evidence.operations[-1].operation_ref

    assert observation.operation_ref == operation_ref
    assert observation.evidence_ref != operation_ref
    assert try_parse(operation_ref) is None


def test_unavailable_produces_a_limitation_and_no_observation():
    evidence = _evidence()
    admitted = admit(
        _result("search_runbooks", ExecutionOutcome.UNAVAILABLE, Completeness.NOT_APPLICABLE),
        evidence=evidence,
        question="does a runbook describe this failure",
    )
    assert admitted == []
    limitation = evidence.limitations[0]
    assert limitation.question == "does a runbook describe this failure"
    assert "could not be reached" in limitation.reason
    assert evidence.observations == []


def test_empty_and_unavailable_stay_distinguishable_after_admission():
    """The one comparison this module exists for. Both went through the same door; only one left
    an observation behind, and the other left a question openly unanswered."""
    evidence = _evidence()
    admit(
        _result("query_logs", ExecutionOutcome.SUCCEEDED, Completeness.EMPTY),
        evidence=evidence,
        question="any errors",
    )
    admit(
        _result("get_metrics", ExecutionOutcome.UNAVAILABLE, Completeness.NOT_APPLICABLE),
        evidence=evidence,
        question="what did latency do",
    )
    assert len(evidence.observations) == 1 and len(evidence.limitations) == 1
    assert evidence.observations[0].completeness is Completeness.EMPTY
    assert evidence.limitations[0].outcome is ExecutionOutcome.UNAVAILABLE
    assert [op.outcome for op in evidence.operations] == [
        ExecutionOutcome.SUCCEEDED,
        ExecutionOutcome.UNAVAILABLE,
    ]


@pytest.mark.parametrize(
    "outcome",
    [
        ExecutionOutcome.TIMED_OUT,
        ExecutionOutcome.UNAVAILABLE,
        ExecutionOutcome.REJECTED,
        ExecutionOutcome.FAILED,
    ],
)
def test_every_non_answering_outcome_names_its_unanswered_question(outcome):
    evidence = _evidence()
    admit(
        _result("get_metrics", outcome, Completeness.NOT_APPLICABLE),
        evidence=evidence,
        question="what did latency do at onset",
    )
    limitation = evidence.limitations[0]
    assert limitation.question == "what did latency do at onset"
    assert limitation.reason
    assert limitation.operation_ref == evidence.operations[-1].operation_ref
    assert evidence.observations == []


def test_limitation_carries_no_category_beyond_the_execution_outcome():
    """A limitation classifies nothing on its own. The execution outcome is the vocabulary, and a
    second one beside it would be invented."""
    evidence = _evidence()
    admit(
        _result("get_metrics", ExecutionOutcome.FAILED, Completeness.NOT_APPLICABLE),
        evidence=evidence,
        question="q",
    )
    fields = set(vars(evidence.limitations[0]))
    assert fields == {"question", "reason", "operation_ref", "capability", "outcome"}


# --- partial travels marked ---------------------------------------------------------------------
def test_a_partial_observation_stays_marked_partial():
    evidence = _evidence()
    observation = admit(
        _result(
            "query_logs",
            ExecutionOutcome.SUCCEEDED,
            Completeness.PARTIAL,
            results=[{"n": 1}],
            evidence_refs=["logs:payment-api:evt-1"],
        ),
        evidence=evidence,
        question="q",
    )[0]
    assert observation.completeness is Completeness.PARTIAL
    assert observation.limitations, "a partial observation must carry what it did not see"


# --- admission is the only door -----------------------------------------------------------------
def test_admission_assigns_identity_and_provenance_to_every_observation():
    evidence = _evidence()
    observation = admit(
        _result(
            "query_logs",
            ExecutionOutcome.SUCCEEDED,
            Completeness.COMPLETE,
            results=[{"n": 1}],
            evidence_refs=["logs:payment-api:evt-1"],
        ),
        evidence=evidence,
        question="q",
        request_scope={"service": "payment-api"},
    )[0]
    assert observation.investigation_id == "inv-1"
    assert observation.operation_ref == evidence.operations[-1].operation_ref
    assert observation.evidence_type is EvidenceType.LOG_EVENT
    assert observation.entities == ("payment-api",)
    assert observation.provenance


def test_the_investigation_is_the_only_identity_an_observation_carries():
    """One investigation, one run, one record. A second identity beside it would have to be kept
    consistent by every reader, and there is nothing for it to name."""
    evidence = _evidence()
    observation = admit(
        _result("query_logs", ExecutionOutcome.SUCCEEDED, Completeness.EMPTY),
        evidence=evidence,
        question="q",
    )[0]
    assert "investigation_id" in vars(observation)
    assert not [name for name in vars(observation) if name.endswith("turn_id")]


def test_the_same_item_is_not_admitted_twice():
    evidence = _evidence()
    for _ in range(2):
        admit(
            _result(
                "query_logs",
                ExecutionOutcome.SUCCEEDED,
                Completeness.COMPLETE,
                results=[{"n": 1}],
                evidence_refs=["logs:payment-api:evt-1"],
            ),
            evidence=evidence,
            question="q",
        )
    assert len(evidence.observations) == 1
    assert len(evidence.operations) == 2, "both attempts are still recorded as operations"


def test_retrieval_results_are_not_admitted_as_operational_evidence():
    """A document cannot observe the running system, so retrieval produces knowledge rather than
    current proof. Admitting it here would put a runbook into the evidence set."""
    evidence = _evidence()
    admitted = admit(
        _result(
            "search_runbooks",
            ExecutionOutcome.SUCCEEDED,
            Completeness.COMPLETE,
            results=[{"doc": 1}],
            evidence_refs=["runbook:payment-timeout"],
        ),
        evidence=evidence,
        question="q",
    )
    assert admitted == [] and evidence.observations == []
    assert len(evidence.operations) == 1


# --- the operations list ------------------------------------------------------------------------
def test_the_operations_list_identifies_every_attempted_call_including_failed_ones():
    """What the investigation attempted is a separate question from what it observed. A reader of
    the record must be able to see a call that answered nothing, or an unreachable source
    disappears from the account of the run."""
    evidence = _evidence()
    admit(
        _result("get_metrics", ExecutionOutcome.UNAVAILABLE, Completeness.NOT_APPLICABLE),
        evidence=evidence,
        question="what did latency do",
    )
    admit(
        _result(
            "query_logs",
            ExecutionOutcome.SUCCEEDED,
            Completeness.COMPLETE,
            results=[{"n": 1}],
            evidence_refs=["logs:payment-api:evt-1"],
        ),
        evidence=evidence,
        question="any errors",
    )
    assert [(op.capability, op.outcome) for op in evidence.operations] == [
        ("get_metrics", ExecutionOutcome.UNAVAILABLE),
        ("query_logs", ExecutionOutcome.SUCCEEDED),
    ]
    assert all(is_operation_ref(op.operation_ref) for op in evidence.operations)
    assert len({op.operation_ref for op in evidence.operations}) == 2


def test_an_operation_carries_its_identifier_capability_and_outcome_and_nothing_else():
    """Not its arguments, not its raw result, and not the transport it took: an investigation
    reaches every capability directly, so a recorded transport would be a constant. Where the two
    transports differ is the span, which records mcp against direct for the same capability."""
    evidence = _evidence()
    admit(
        _result("get_metrics", ExecutionOutcome.FAILED, Completeness.NOT_APPLICABLE),
        evidence=evidence,
        question="q",
    )
    assert set(vars(evidence.operations[0])) == {"operation_ref", "capability", "outcome"}


def test_operation_references_are_opaque_unique_and_not_evidence_references():
    evidence = _evidence()
    for _ in range(3):
        admit(
            _result("get_metrics", ExecutionOutcome.FAILED, Completeness.NOT_APPLICABLE),
            evidence=evidence,
            question="q",
        )
    refs = [op.operation_ref for op in evidence.operations]
    assert len(set(refs)) == 3
    assert all(is_operation_ref(r) for r in refs)
    # The two identifier spaces must not overlap: an operation names an attempt, not an
    # observation, so the evidence parser must refuse it.
    assert all(try_parse(r) is None for r in refs)


# --- every capability produces a citable observation ---------------------------------------------
_CITABLE_CALLS = {
    "incident record": ("get_incident", {"incident_id": "inc-004"}),
    "alerts": ("get_correlated_alerts", {"incident_id": "inc-004"}),
    "logs": ("query_logs", {"service": "payment-api"}),
    "dependencies": ("get_service_dependencies", {}),
    "query rows": (
        "structured_query",
        {"collection": "incident", "projection": ["category"], "limit": 5},
    ),
    "query count": (
        "structured_query",
        {"collection": "incident", "aggregate": "count", "limit": 5},
    ),
}


@pytest.mark.parametrize(
    "capability,arguments", list(_CITABLE_CALLS.values()), ids=list(_CITABLE_CALLS)
)
def test_every_admitted_observation_carries_a_reference_that_parses_and_resolves(
    capability, arguments
):
    """The end-to-end citability proof. A capability whose observations cannot be cited cannot
    support a claim, so its results would be unusable however correct they are."""
    records = corpus_records()
    evidence = EvidenceSet(investigation_id="inv-1")
    result = ToolService(records).call(capability, **arguments)
    assert result.answered and result.results, f"{capability} produced nothing to admit"

    admitted = admit(result, evidence=evidence, question="q")
    assert admitted, f"{capability} admitted no observation"

    resolver = ReferenceResolver(records, observations=evidence.observations)
    for observation in admitted:
        parsed = try_parse(observation.evidence_ref)
        assert parsed is not None, f"{observation.evidence_ref} does not parse"
        assert parsed.reference_type is ReferenceType.EVIDENCE
        assert resolver.resolves(observation.evidence_ref), (
            f"{observation.evidence_ref} does not resolve"
        )


def test_an_admitted_incident_record_carries_no_cause_or_resolution():
    """The corpus holds its own answers. What an agent may observe of an incident is the approved
    structured-query surface and nothing wider, so the answer text is unreachable rather than
    merely unread."""
    evidence = EvidenceSet(investigation_id="inv-1")
    result = ToolService(corpus_records()).call("get_incident", incident_id="inc-001")
    observation = admit(result, evidence=evidence, question="what is this incident")[0]

    assert observation.observation["incident_id"] == "inc-001"
    for field in ("root_cause", "resolution", "close_code", "short_description"):
        assert field not in observation.observation


# --- the static maps ----------------------------------------------------------------------------
def test_every_registered_capability_has_a_declared_evidence_type():
    assert set(CAPABILITY_EVIDENCE_TYPES) == set(CAPABILITY_NAMES)


def test_declared_evidence_types_are_all_accepted_ones():
    declared = {v for v in CAPABILITY_EVIDENCE_TYPES.values() if v is not None}
    assert declared <= set(EvidenceType)


def test_the_capability_inventory_is_the_registry():
    """One list, not two. A second inventory is how a mutating capability eventually becomes
    reachable."""
    assert set(ToolService(corpus_records()).tool_names) == set(CAPABILITY_NAMES)
