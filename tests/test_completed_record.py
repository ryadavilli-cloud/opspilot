"""The completed investigation, and the two operations that store and return it.

Three properties matter here, and each is asserted against both backends rather than against
whichever one was convenient. A record survives being stored: what comes back carries the same
contents, through a real serialization rather than by handing back the caller's own object. One
completed record per investigation: a second save is refused rather than overwriting an account
someone may already have read. And the record answers for itself: every reference its assessment
cites resolves against the evidence and passages carried in the same record, so a reader holding it
needs nothing else.

Both backends run the same cases through one fixture. A store that passed here and failed in
production would mean the two disagree about what storing does, which is exactly what the shared
parametrization is for.
"""

from __future__ import annotations

from typing import Any

import pytest

from opspilot.assessment.contracts import (
    Action,
    Assessment,
    Brief,
    Candidate,
    Outcome,
    SupportLabel,
)
from opspilot.evidence.admission import AdmittedObservation, EvidenceType, Limitation
from opspilot.evidence.operations import Operation
from opspilot.record.completed import CompletedInvestigation
from opspilot.record.cosmos import CosmosCompletedInvestigations
from opspilot.record.memory import InMemoryCompletedInvestigations
from opspilot.record.port import AlreadySaved
from opspilot.retrieval.retriever import Passage
from opspilot.tools.contracts import Completeness, ExecutionOutcome

LOG = "logs:checkout-api:evt-005-01"
MEMORY = "metrics:redis-cache:used_memory_pct@2026-06-22T11:35:00Z"
ABSENCE = "absence:get_deployments:op-0003"
RUNBOOK = "runbook:redis-cache-degradation"


class _FakeCosmosContainer:
    """Enough of a Cosmos container for the two calls this store makes.

    It answers like the real one in the two ways that matter: a create against an id it already
    holds conflicts, and a read of an absent id is a 404 rather than an empty answer. It also adds
    the system properties Cosmos stamps on every document, so a record that only round-trips
    because nothing extra came back would fail here.
    """

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}

    def create_item(self, body: dict[str, Any]) -> dict[str, Any]:
        if body["id"] in self.documents:
            raise _CosmosError(409)
        self.documents[body["id"]] = dict(body)
        return body

    def read_item(self, item: str, partition_key: str) -> dict[str, Any]:
        if item not in self.documents:
            raise _CosmosError(404)
        return {
            **self.documents[item],
            "_rid": "abc==",
            "_ts": 1_780_000_000,
            "_etag": '"0x8DA"',
            "_self": "dbs/x/colls/y/docs/z",
        }


class _CosmosError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"cosmos status {status_code}")
        self.status_code = status_code


def _record(investigation_id: str = "inv-1") -> CompletedInvestigation:
    """One record with every part populated, including a failed operation and a partial
    observation, so the round trip is asserted over the shapes that actually vary."""
    return CompletedInvestigation(
        investigation_id=investigation_id,
        incident_id="inc-005",
        objective="explain the checkout latency rise",
        outcome=Outcome.PARTIAL,
        stopped_because="the investigator reported nothing further worth checking",
        observations=[
            AdmittedObservation(
                evidence_ref=LOG,
                investigation_id=investigation_id,
                operation_ref="op-0001",
                evidence_type=EvidenceType.LOG_EVENT,
                source="query_logs",
                completeness=Completeness.COMPLETE,
                observation={"message": "upstream call failed; retrying"},
                entities=("checkout-api",),
                provenance="query_logs(service=checkout-api)",
            ),
            AdmittedObservation(
                evidence_ref=MEMORY,
                investigation_id=investigation_id,
                operation_ref="op-0002",
                evidence_type=EvidenceType.METRIC,
                source="get_metrics",
                completeness=Completeness.PARTIAL,
                observation={"value": 99.0},
                entities=("redis-cache",),
                provenance="get_metrics(service=redis-cache)",
                limitations=("the source returned part of the requested scope",),
            ),
            AdmittedObservation(
                evidence_ref=ABSENCE,
                investigation_id=investigation_id,
                operation_ref="op-0003",
                evidence_type=EvidenceType.DEPLOYMENT_OR_CHANGE,
                source="get_deployments",
                completeness=Completeness.EMPTY,
                observation="no matching observations for get_deployments(service=checkout-api)",
                provenance="get_deployments(service=checkout-api)",
            ),
        ],
        limitations=[
            Limitation(
                question="what did the change history show",
                reason="the source could not be reached",
                operation_ref="op-0004",
                capability="get_deployments",
                outcome=ExecutionOutcome.UNAVAILABLE,
            )
        ],
        operations=[
            Operation("op-0001", "query_logs", ExecutionOutcome.SUCCEEDED),
            Operation("op-0002", "get_metrics", ExecutionOutcome.SUCCEEDED),
            Operation("op-0003", "get_deployments", ExecutionOutcome.SUCCEEDED),
            Operation("op-0004", "get_deployments", ExecutionOutcome.UNAVAILABLE),
        ],
        passages=[
            Passage(
                reference=RUNBOOK,
                category="runbook",
                title="Redis cache degradation",
                text="Raise the memory ceiling and confirm eviction returns to zero.",
                services=("redis-cache",),
                score=0.031,
            )
        ],
        assessment=Assessment(
            what_happened="checkout latency rose while the cache evicted keys",
            what_happened_refs=[LOG],
            candidates=[
                Candidate(
                    statement="redis-cache hit its memory ceiling",
                    label=SupportLabel.LEADING,
                    established=True,
                    supporting=[MEMORY],
                    weakening=[ABSENCE],
                )
            ],
            limitations=["what did the change history show"],
            actions=[
                Action(action="raise the cache memory ceiling", now=True, knowledge_ref=RUNBOOK)
            ],
            knowledge_used=[RUNBOOK],
        ),
        brief=Brief(outcome=Outcome.PARTIAL, text="Outcome: partial\n\nWhat happened..."),
        trace_id="inv-1",
        model_deployment="gpt-5-mini",
        prompt_versions={"rca_synthesis": "v2"},
    )


def _memory() -> InMemoryCompletedInvestigations:
    return InMemoryCompletedInvestigations()


def _cosmos() -> CosmosCompletedInvestigations:
    return CosmosCompletedInvestigations(_FakeCosmosContainer())


@pytest.fixture(params=[_memory, _cosmos], ids=["memory", "cosmos"])
def repository(request):
    """Both backends, same cases. What storing means must not depend on which one is behind the
    seam."""
    return request.param()


# --- the record survives being stored -----------------------------------------------------------
def test_a_saved_record_reads_back_with_the_same_contents(repository):
    original = _record()
    repository.save(original)

    read_back = repository.get("inv-1")

    assert read_back == CompletedInvestigation.model_validate(original.model_dump(mode="json"))


def test_the_read_carries_every_part_the_record_was_given(repository):
    """Field by field, because an equality that passed while a list silently emptied would still
    be equal to an equally empty expectation."""
    repository.save(_record())
    read_back = repository.get("inv-1")

    assert read_back is not None
    assert read_back.incident_id == "inc-005"
    assert read_back.objective == "explain the checkout latency rise"
    assert read_back.outcome is Outcome.PARTIAL
    assert read_back.stopped_because
    assert [o.evidence_ref for o in read_back.observations] == [LOG, MEMORY, ABSENCE]
    assert [limitation.question for limitation in read_back.limitations] == [
        "what did the change history show"
    ]
    assert [p.reference for p in read_back.passages] == [RUNBOOK]
    assert read_back.assessment.candidates[0].established is True
    assert read_back.brief.outcome is Outcome.PARTIAL
    assert read_back.model_deployment == "gpt-5-mini"
    assert read_back.prompt_versions == {"rca_synthesis": "v2"}


def test_the_operations_list_keeps_the_calls_that_answered_nothing(repository):
    """An account of a run that dropped its failed calls would read as more complete than the run
    was, and the evaluation reads this list to check no attempted operation was a write."""
    repository.save(_record())
    read_back = repository.get("inv-1")

    assert read_back is not None
    assert [(op.operation_ref, op.outcome) for op in read_back.operations] == [
        ("op-0001", ExecutionOutcome.SUCCEEDED),
        ("op-0002", ExecutionOutcome.SUCCEEDED),
        ("op-0003", ExecutionOutcome.SUCCEEDED),
        ("op-0004", ExecutionOutcome.UNAVAILABLE),
    ]


def test_a_partial_observation_stays_partial_across_the_round_trip(repository):
    repository.save(_record())
    read_back = repository.get("inv-1")

    assert read_back is not None
    partial = next(o for o in read_back.observations if o.evidence_ref == MEMORY)
    assert partial.completeness is Completeness.PARTIAL
    assert partial.limitations


# --- one record per investigation ---------------------------------------------------------------
def test_a_second_save_of_the_same_identifier_is_refused(repository):
    """A delivered brief is never edited and a terminal outcome is never reopened, so the second
    save is refused rather than replacing an account someone may already have read."""
    repository.save(_record())

    with pytest.raises(AlreadySaved):
        repository.save(_record())


def test_the_refused_save_leaves_the_first_record_intact(repository):
    repository.save(_record())
    with pytest.raises(AlreadySaved):
        repository.save(_record())

    read_back = repository.get("inv-1")
    assert read_back is not None
    assert read_back.objective == "explain the checkout latency rise"


def test_reading_an_investigation_that_was_never_saved_is_a_clean_absence(repository):
    """Absent is an answer. A store that raised here would make "no such investigation"
    indistinguishable from a store that could not be reached."""
    assert repository.get("inv-never") is None


def test_saving_one_investigation_does_not_create_another(repository):
    repository.save(_record("inv-1"))
    assert repository.get("inv-2") is None


def test_two_investigations_are_stored_independently(repository):
    repository.save(_record("inv-1"))
    repository.save(_record("inv-2"))

    first, second = repository.get("inv-1"), repository.get("inv-2")
    assert first is not None and second is not None
    assert first.investigation_id == "inv-1" and second.investigation_id == "inv-2"


# --- the record answers for its own citations ---------------------------------------------------
def test_every_reference_the_assessment_cites_resolves_within_the_saved_record(repository):
    """The property that makes the record self-contained: a reader holding it can check a citation
    without the corpus, the run, or anything else that may have moved on."""
    repository.save(_record())
    read_back = repository.get("inv-1")
    assert read_back is not None

    available = read_back.evidence_refs
    assessment = read_back.assessment
    cited = {
        *assessment.what_happened_refs,
        *(ref for candidate in assessment.candidates for ref in candidate.supporting),
        *(ref for candidate in assessment.candidates for ref in candidate.weakening),
        *(action.knowledge_ref for action in assessment.actions if action.knowledge_ref),
        *assessment.knowledge_used,
    }

    assert cited, "the fixture must cite something for this to mean anything"
    assert cited <= available, f"unresolvable in the record: {sorted(cited - available)}"


def test_the_records_own_references_span_both_evidence_and_retrieved_knowledge():
    record = _record()
    assert LOG in record.evidence_refs
    assert RUNBOOK in record.evidence_refs


# --- the Cosmos document shape ------------------------------------------------------------------
def test_the_cosmos_document_carries_the_identity_cosmos_requires():
    """Cosmos needs an `id` on every document and the record does not carry one, so the store
    attaches the identity the record already has rather than inventing a second key."""
    container = _FakeCosmosContainer()
    CosmosCompletedInvestigations(container).save(_record())

    document = container.documents["inv-1"]
    assert document["id"] == "inv-1"
    assert document["investigation_id"] == "inv-1"


def test_cosmos_system_properties_never_reach_the_record():
    """Every read comes back stamped with the container's own bookkeeping. None of it is part of
    the investigation, and the record has no field for it."""
    container = _FakeCosmosContainer()
    store = CosmosCompletedInvestigations(container)
    store.save(_record())

    read_back = store.get("inv-1")

    assert read_back is not None
    assert not [name for name in vars(read_back) if name.startswith("_")]
    assert read_back == CompletedInvestigation.model_validate(_record().model_dump(mode="json"))
