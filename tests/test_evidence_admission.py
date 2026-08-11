"""The two axes, and admission as the only door into the evidence set.

The distinction this suite exists to protect is `succeeded + empty` against `unavailable`. A
source that answered authoritatively with nothing and a source that never answered must stay
separately representable, separately admitted, and separately visible, because collapsing them
turns an unreachable source into a clean bill of health.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opspilot.evidence.admission import (
    CAPABILITY_EVIDENCE_TYPES,
    AuthoritativeAbsence,
    EvidenceType,
    admit,
)
from opspilot.evidence.operations import TurnEvidence, is_operation_ref
from opspilot.evidence.references import try_parse
from opspilot.tools import CAPABILITY_NAMES
from opspilot.tools.contracts import (
    LEGAL_PAIRINGS,
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


def _turn() -> TurnEvidence:
    return TurnEvidence(investigation_id="inv-1", turn_id="turn-1")


# --- the pairing table ------------------------------------------------------------------------
@pytest.mark.parametrize("outcome", list(ExecutionOutcome))
@pytest.mark.parametrize("completeness", list(Completeness))
def test_only_legal_pairings_can_be_constructed(outcome, completeness):
    legal = completeness in LEGAL_PAIRINGS[outcome]
    if legal:
        assert _result("query_logs", outcome, completeness).completeness is completeness
    else:
        with pytest.raises(ValidationError):
            _result("query_logs", outcome, completeness)


def test_every_outcome_has_a_declared_pairing_set():
    assert set(LEGAL_PAIRINGS) == set(ExecutionOutcome)


def test_a_non_answering_result_cannot_carry_content():
    """Content on a failed outcome is how fabricated evidence would get in."""
    with pytest.raises(ValidationError):
        _result(
            "query_logs",
            ExecutionOutcome.UNAVAILABLE,
            Completeness.NOT_APPLICABLE,
            evidence_refs=["logs:a:e1"],
        )


# --- the distinction that matters ---------------------------------------------------------------
def test_empty_is_admitted_as_a_positive_observation():
    turn = _turn()
    outcome = admit(
        _result("query_logs", ExecutionOutcome.SUCCEEDED, Completeness.EMPTY),
        turn=turn,
        question="were there errors for payment-api in the window",
        request_scope={"service": "payment-api"},
    )
    assert outcome.admitted and not outcome.limitation
    observation = outcome.observations[0]
    assert observation.is_authoritative_absence
    assert isinstance(observation.observation, AuthoritativeAbsence)
    assert observation.observation.nothing_matched
    assert "payment-api" in str(observation.observation)
    assert turn.limitations == []


def test_unavailable_produces_a_limitation_and_no_observation():
    turn = _turn()
    outcome = admit(
        _result("search_runbooks", ExecutionOutcome.UNAVAILABLE, Completeness.NOT_APPLICABLE),
        turn=turn,
        question="does a runbook describe this failure",
    )
    assert not outcome.admitted and outcome.observations == []
    assert outcome.limitation is not None
    assert outcome.limitation.question == "does a runbook describe this failure"
    assert "could not be reached" in outcome.limitation.reason
    assert turn.observations == []
    assert len(turn.limitations) == 1


def test_empty_and_unavailable_stay_distinguishable_after_admission():
    """The one comparison this module exists for. Both went through the same door; only one left
    an observation behind, and the other left a question openly unanswered."""
    turn = _turn()
    admit(
        _result("query_logs", ExecutionOutcome.SUCCEEDED, Completeness.EMPTY),
        turn=turn,
        question="any errors",
    )
    admit(
        _result("get_metrics", ExecutionOutcome.UNAVAILABLE, Completeness.NOT_APPLICABLE),
        turn=turn,
        question="what did latency do",
    )
    assert len(turn.observations) == 1 and len(turn.limitations) == 1
    assert turn.observations[0].completeness is Completeness.EMPTY
    assert turn.limitations[0].outcome is ExecutionOutcome.UNAVAILABLE
    assert len(turn.ledger) == 2
    assert [r.admitted for r in turn.ledger.records] == [True, False]


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
    turn = _turn()
    result = admit(
        _result("get_metrics", outcome, Completeness.NOT_APPLICABLE),
        turn=turn,
        question="what did latency do at onset",
    )
    assert result.limitation is not None
    assert result.limitation.question == "what did latency do at onset"
    assert result.limitation.reason
    assert result.limitation.operation_ref == result.operation.operation_ref
    assert turn.observations == []


def test_limitation_carries_no_category_beyond_the_execution_outcome():
    """A limitation classifies nothing on its own. The execution outcome is the vocabulary, and a
    second one beside it would be invented."""
    turn = _turn()
    limitation = admit(
        _result("get_metrics", ExecutionOutcome.FAILED, Completeness.NOT_APPLICABLE),
        turn=turn,
        question="q",
    ).limitation
    assert limitation is not None
    fields = set(vars(limitation))
    assert fields == {"question", "reason", "operation_ref", "capability", "outcome"}


# --- partial travels marked ---------------------------------------------------------------------
def test_a_partial_observation_stays_marked_partial():
    turn = _turn()
    outcome = admit(
        _result(
            "query_logs",
            ExecutionOutcome.SUCCEEDED,
            Completeness.PARTIAL,
            results=[{"n": 1}],
            evidence_refs=["logs:payment-api:evt-1"],
        ),
        turn=turn,
        question="q",
    )
    observation = outcome.observations[0]
    assert observation.completeness is Completeness.PARTIAL
    assert observation.limitations, "a partial observation must carry what it did not see"


# --- admission is the only door -----------------------------------------------------------------
def test_admission_assigns_identity_and_provenance_to_every_observation():
    turn = _turn()
    outcome = admit(
        _result(
            "query_logs",
            ExecutionOutcome.SUCCEEDED,
            Completeness.COMPLETE,
            results=[{"n": 1}],
            evidence_refs=["logs:payment-api:evt-1"],
        ),
        turn=turn,
        question="q",
        request_scope={"service": "payment-api"},
    )
    observation = outcome.observations[0]
    assert observation.investigation_id == "inv-1" and observation.turn_id == "turn-1"
    assert observation.operation_ref == outcome.operation.operation_ref
    assert observation.evidence_type is EvidenceType.LOG_EVENT
    assert observation.entities == ("payment-api",)
    assert observation.provenance


def test_the_same_item_is_not_admitted_twice_in_one_turn():
    turn = _turn()
    for _ in range(2):
        admit(
            _result(
                "query_logs",
                ExecutionOutcome.SUCCEEDED,
                Completeness.COMPLETE,
                results=[{"n": 1}],
                evidence_refs=["logs:payment-api:evt-1"],
            ),
            turn=turn,
            question="q",
        )
    assert len(turn.observations) == 1
    assert len(turn.ledger) == 2, "both attempts are still recorded as operations"


def test_retrieval_results_are_not_admitted_as_operational_evidence():
    """A document cannot observe the running system, so retrieval produces knowledge rather than
    current proof. Admitting it here would put a runbook into the evidence set."""
    turn = _turn()
    outcome = admit(
        _result(
            "search_runbooks",
            ExecutionOutcome.SUCCEEDED,
            Completeness.COMPLETE,
            results=[{"doc": 1}],
            evidence_refs=["runbook:payment-timeout"],
        ),
        turn=turn,
        question="q",
    )
    assert outcome.observations == [] and turn.observations == []
    assert len(turn.ledger) == 1


# --- the static maps ----------------------------------------------------------------------------
def test_every_registered_capability_has_a_declared_evidence_type():
    assert set(CAPABILITY_EVIDENCE_TYPES) == set(CAPABILITY_NAMES)


def test_declared_evidence_types_are_all_accepted_ones():
    declared = {v for v in CAPABILITY_EVIDENCE_TYPES.values() if v is not None}
    assert declared <= set(EvidenceType)


def test_the_capability_inventory_is_the_registry():
    """One list, not two. A second inventory is how a mutating capability eventually becomes
    reachable."""
    assert set(ToolService().tool_names) == set(CAPABILITY_NAMES)


# --- operation references -----------------------------------------------------------------------
def test_operation_references_are_opaque_unique_and_not_evidence_references():
    turn = _turn()
    refs = []
    for _ in range(3):
        outcome = admit(
            _result("get_metrics", ExecutionOutcome.FAILED, Completeness.NOT_APPLICABLE),
            turn=turn,
            question="q",
        )
        refs.append(outcome.operation.operation_ref)
    assert len(set(refs)) == 3
    assert all(is_operation_ref(r) for r in refs)
    # The two identifier spaces must not overlap: an operation names an attempt, not an
    # observation, so the evidence parser must refuse it.
    assert all(try_parse(r) is None for r in refs)
