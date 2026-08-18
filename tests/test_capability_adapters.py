"""What changes when the capabilities read a container instead of the image.

The ordinary per-capability behavior is covered in `test_tools.py` and `test_tools_operational.py`
and is unchanged by the move. What is asserted here is what the move makes newly possible to get
wrong: a deadline that never reaches the source, a bound a request can set for itself, an
unreachable source that reads as a clean answer, and a corpus still reachable from the image.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fake_operational_records import FakeContainer, corpus_container, corpus_documents

from opspilot.data.operational_records import OperationalRecords, SourceUnavailable
from opspilot.tools.contracts import Completeness, ExecutionOutcome
from opspilot.tools.service import ToolService

DEADLINE = 4.5

# Every capability that reads the container, with arguments that reach a real partition.
CAPABILITY_CALLS = [
    ("get_incident", {"incident_id": "inc-004"}),
    ("get_correlated_alerts", {"incident_id": "inc-004"}),
    (
        "get_deployments",
        {
            "services": ["checkout-api"],
            "start_time": datetime(2026, 6, 1, tzinfo=UTC),
            "end_time": datetime(2026, 6, 30, tzinfo=UTC),
        },
    ),
    ("query_logs", {"service": "payment-api"}),
    ("get_metrics", {"service": "redis-cache"}),
    ("get_service_dependencies", {}),
]
CAPABILITY_NAMES = [name for name, _ in CAPABILITY_CALLS]


@pytest.fixture
def bounded() -> tuple[ToolService, FakeContainer]:
    container = corpus_container()
    return ToolService(OperationalRecords(container), deadline_s=DEADLINE), container


# --- the deadline reaches the source ----------------------------------------------------------
@pytest.mark.parametrize("name,arguments", CAPABILITY_CALLS, ids=CAPABILITY_NAMES)
def test_every_capability_hands_its_deadline_to_the_source(bounded, name, arguments):
    """Checking a deadline between stages is not enough: a single call that outlives its turn is a
    bound violation even when the data it returns is correct. So the assertion is made at the
    source, on what the container was actually given, not on what the caller intended."""
    service, container = bounded
    result = service.call(name, **arguments)

    assert result.answered
    assert container.timeouts, f"{name} reached the container without issuing a read"
    assert all(timeout == DEADLINE for timeout in container.timeouts)


@pytest.mark.parametrize("name,arguments", CAPABILITY_CALLS, ids=CAPABILITY_NAMES)
def test_no_source_call_exceeds_the_deadline_it_was_given(bounded, name, arguments):
    service, container = bounded
    service.call(name, **arguments)
    assert all(timeout <= DEADLINE for timeout in container.timeouts)


def test_a_capability_that_issues_several_reads_bounds_every_one_of_them(bounded):
    """The readiness count walks all six kinds in one call. Each read carries the bound; a loop
    that carried it only on the first would pass every single-read assertion above."""
    service, container = bounded
    service.records.kind_counts(deadline_s=DEADLINE)
    assert len(container.timeouts) == 6
    assert all(timeout == DEADLINE for timeout in container.timeouts)


def test_a_failed_read_still_carried_its_deadline():
    """A bound that only holds on the happy path is not a bound."""
    container = corpus_container(unreachable=True)
    service = ToolService(OperationalRecords(container), deadline_s=DEADLINE)
    service.get_incident(incident_id="inc-004")
    assert container.timeouts == [DEADLINE]


# --- the deadline is a bound, not an argument -------------------------------------------------
@pytest.mark.parametrize("name,arguments", CAPABILITY_CALLS, ids=CAPABILITY_NAMES)
def test_dispatch_refuses_a_request_that_names_its_own_deadline(bounded, name, arguments):
    """Bounds live in code and are unreachable from a prompt. This is the parameter a model would
    reach for to buy itself more time, so it is refused at dispatch rather than dropped quietly:
    a silently ignored deadline leaves the request looking honored."""
    service, container = bounded
    result = service.call(name, **arguments, deadline_s=3600.0)

    assert result.outcome is ExecutionOutcome.REJECTED
    assert result.completeness is Completeness.NOT_APPLICABLE
    assert result.error == "a request may not set its own deadline"
    assert container.timeouts == [], "the request was refused, so nothing should have executed"


def test_a_refused_deadline_does_not_change_the_one_in_force(bounded):
    service, container = bounded
    service.call("get_incident", incident_id="inc-004", deadline_s=3600.0)
    service.call("get_incident", incident_id="inc-004")
    assert container.timeouts == [DEADLINE]


# --- an unreachable source is not an answer ---------------------------------------------------
@pytest.mark.parametrize("name,arguments", CAPABILITY_CALLS, ids=CAPABILITY_NAMES)
def test_an_unreachable_container_is_unavailable_not_empty(name, arguments):
    """The distinction the two axes exist to protect. A source that answered with nothing settles
    its question; a source that could not be reached leaves it open. Collapsing them turns an
    unreachable container into a clean bill of health."""
    service = ToolService(OperationalRecords(corpus_container(unreachable=True)))
    result = service.call(name, **arguments)

    assert result.outcome is ExecutionOutcome.UNAVAILABLE
    assert result.completeness is Completeness.NOT_APPLICABLE
    assert result.answered is False
    assert result.results == [] and result.evidence_refs == []


@pytest.mark.parametrize("name,arguments", CAPABILITY_CALLS, ids=CAPABILITY_NAMES)
def test_an_unreachable_container_is_not_reported_as_an_internal_defect(name, arguments):
    """`failed` says the capability's own code broke, which sends an operator to the wrong place.
    The two are separately representable and must stay separately reported."""
    service = ToolService(OperationalRecords(corpus_container(unreachable=True)))
    result = service.call(name, **arguments)
    assert result.outcome is not ExecutionOutcome.FAILED


def test_the_provider_failure_never_travels_with_the_result():
    service = ToolService(OperationalRecords(corpus_container(unreachable=True)))
    result = service.get_incident(incident_id="inc-004")
    assert result.error == "source unavailable"
    assert "refused the connection" not in (result.error or "")


def test_the_source_raises_rather_than_returning_nothing():
    """The reader itself must not translate a failed read into an empty one, or every caller above
    would have to guess which it was holding."""
    records = OperationalRecords(corpus_container(unreachable=True))
    with pytest.raises(SourceUnavailable):
        records.incident("inc-004", deadline_s=DEADLINE)


# --- nothing falls back to the corpus in the image --------------------------------------------
@pytest.mark.parametrize("name,arguments", CAPABILITY_CALLS, ids=CAPABILITY_NAMES)
def test_an_empty_container_answers_empty_rather_than_from_the_image(name, arguments):
    """The structural proof that the corpus files are no longer a source. The authored corpus is
    still on disk in a development tree, so a capability that had kept reading it would answer
    these calls with real RetailEase records against a container holding nothing."""
    service = ToolService(OperationalRecords(FakeContainer([])))
    result = service.call(name, **arguments)

    assert result.outcome is ExecutionOutcome.SUCCEEDED
    assert result.completeness is Completeness.EMPTY
    assert result.results == []


# --- reads are scoped to the partitions their capability owns ---------------------------------
@pytest.mark.parametrize("name,arguments", CAPABILITY_CALLS, ids=CAPABILITY_NAMES)
def test_every_read_names_the_record_kind_it_wants(bounded, name, arguments):
    """`kind` is the first partition level. A read that omitted it would answer correctly and scan
    the whole container to do it, which no assertion about the result would catch."""
    service, container = bounded
    service.call(name, **arguments)
    assert all("c.kind = @kind" in query for query in container.queries)


def test_no_query_is_assembled_from_a_caller_supplied_value(bounded):
    """Values arrive as parameters. A caller that could reach the query text could widen the read
    surface through an argument."""
    service, container = bounded
    service.get_incident(incident_id="inc-004' OR 1=1 --")
    assert all("1=1" not in query for query in container.queries)


# --- the dependency edge's own kind survives the partition key ---------------------------------
def test_dependency_edges_report_their_relationship_not_the_partition_value():
    """A dependency edge names its own kind, and so does the container's first partition level.
    Preparation carries the edge's under `dependency_kind`; if the adapter read `kind` instead,
    every edge would report the literal "dependency" and the graph would lose its meaning.
    """
    service = ToolService(OperationalRecords(corpus_container()))
    result = service.get_service_dependencies()

    kinds = {edge.kind for edge in result.results}
    assert result.answered and kinds
    assert "dependency" not in kinds
    assert {"sync-http", "cache"} <= kinds


def test_the_prepared_edge_carries_both_its_partition_kind_and_its_own():
    edges = [doc for doc in corpus_documents() if doc["kind"] == "dependency"]
    assert edges
    assert all(doc["dependency_kind"] and doc["dependency_kind"] != "dependency" for doc in edges)


# --- the investigation's remaining time bounds the call too --------------------------------------
@pytest.mark.parametrize("name,arguments", CAPABILITY_CALLS, ids=CAPABILITY_NAMES)
def test_a_call_takes_the_smaller_of_the_ceiling_and_the_remaining_time(bounded, name, arguments):
    """Two bounds, and a call is subject to both. The ceiling keeps one source from hanging; the
    remaining time keeps the sum of them inside the investigation that asked."""
    service, container = bounded
    remaining = DEADLINE / 3

    service.call(name, remaining, **arguments)

    assert container.timeouts, f"{name} reached the container without issuing a read"
    assert all(timeout == remaining for timeout in container.timeouts)


def test_the_ceiling_still_applies_when_the_investigation_has_longer_left(bounded):
    """The remaining time is the other bound, not a replacement for the ceiling: an investigation
    with minutes left must still not let one source hang for minutes."""
    service, container = bounded

    service.call("get_incident", DEADLINE * 100, incident_id="inc-004")

    assert container.timeouts == [DEADLINE]


def test_a_nearly_expired_investigation_cannot_start_a_full_length_call(bounded):
    """The case the ceiling alone gets wrong. With a moment left, a call that took the whole
    ceiling would outlive the run it belongs to and report into an investigation already over."""
    service, container = bounded

    service.call("get_incident", 0.05, incident_id="inc-004")

    assert container.timeouts == [0.05]
    assert all(timeout < DEADLINE for timeout in container.timeouts)


def test_an_expired_investigation_leaves_no_time_to_spend(bounded):
    """Not a negative deadline, and not the ceiling. Nothing remains, so nothing may be taken."""
    service, container = bounded

    service.call("get_incident", -5.0, incident_id="inc-004")

    assert container.timeouts == [0.0]


@pytest.mark.parametrize("name,arguments", CAPABILITY_CALLS, ids=CAPABILITY_NAMES)
def test_no_capability_can_outlive_the_remaining_bound_it_was_given(bounded, name, arguments):
    """Stated over every capability rather than one, because this is the property that has to hold
    by construction: the bound is applied where the call is made, not per adapter."""
    service, container = bounded
    remaining = 1.25

    service.call(name, remaining, **arguments)

    assert all(timeout <= remaining for timeout in container.timeouts)


def test_a_request_naming_the_remaining_time_cannot_widen_its_own_bound(bounded):
    """The parameter is positional-only for exactly this reason. A model's arguments arrive as
    keywords, so a named one here could be bound by an argument the model chose; kept out of the
    keyword space it lands among the arguments instead, where the capability refuses it."""
    service, container = bounded

    result = service.call("get_incident", 0.05, incident_id="inc-004", remaining_s=3600.0)

    assert result.outcome is ExecutionOutcome.REJECTED
    assert container.timeouts == [], "the request was refused, so nothing should have executed"


def test_the_service_holds_no_investigation_state_between_calls(bounded):
    """One process-wide service serves every investigation, so a deadline stored on it would
    belong to whichever run wrote it last. Passing it per call is what keeps runs independent."""
    service, container = bounded

    service.call("get_incident", 0.5, incident_id="inc-004")
    service.call("get_incident", None, incident_id="inc-004")

    assert container.timeouts == [0.5, DEADLINE]
