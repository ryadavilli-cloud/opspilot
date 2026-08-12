"""The governed structured-query path, tested by layer rather than through a fake database.

Three things are true here and each is established where it actually lives:

- **What the query says** belongs to `translate`, and is asserted on the emitted text and the bound
  parameter values. A wrong predicate is caught by reading the query, not by executing it against a
  stand-in that would have to be a database to disagree.
- **What a refusal is** belongs to `validate`, and is asserted before anything executes.
- **How an outcome becomes two axes** belongs to the capability, and is asserted with a container
  that ignores the query entirely. Rows, nothing, or a raise: the mapping cannot depend on what the
  query said, so the stand-in deliberately does not read it.

That the emitted query means what it appears to mean is Cosmos's answer, established by one live
run and recorded in `status.md`. No fake here filters, so no test here can pass because a fake and
the translator were wrong in the same way.
"""

from __future__ import annotations

import pytest
from fake_operational_records import CannedContainer

from opspilot import config
from opspilot.data.operational_records import OperationalRecords
from opspilot.data.structured_query import (
    APPROVED_SURFACE,
    Predicate,
    PredicateOp,
    QueryRejected,
    StructuredQuery,
    translate,
    validate,
)
from opspilot.tools.contracts import Completeness, ExecutionOutcome
from opspilot.tools.service import ToolService

DEADLINE = 3.0


def _query(**overrides) -> StructuredQuery:
    base = {"collection": "incident", "projection": ["incident_id"], "limit": 10}
    return StructuredQuery(**{**base, **overrides})


def _service(container) -> ToolService:
    return ToolService(OperationalRecords(container), deadline_s=DEADLINE)


# --- what the query says -------------------------------------------------------------------------
def test_a_projection_names_its_fields_and_binds_its_kind():
    text, parameters = translate(_query())
    assert text == "SELECT TOP 10 c.incident_id FROM c WHERE c.kind = @kind"
    assert parameters == [{"name": "@kind", "value": "incident"}]


def test_every_predicate_form_emits_its_fragment_and_binds_its_values():
    """The values matter as much as the names: a translator binding the right parameter to the
    wrong value passes any check that reads names alone."""
    text, parameters = translate(
        _query(
            collection="deployment",
            projection=["deploy_id", "version"],
            predicates=[
                Predicate(field="service", op=PredicateOp.EQ, value="checkout-api"),
                Predicate(field="version", op=PredicateOp.IN, values=["v1", "v2"]),
                Predicate(
                    field="ts",
                    op=PredicateOp.BETWEEN,
                    low="2026-06-01T00:00:00Z",
                    high="2026-06-30T00:00:00Z",
                ),
            ],
        )
    )
    assert text == (
        "SELECT TOP 10 c.deploy_id, c.version FROM c WHERE "
        "c.kind = @kind AND c.service = @p0 AND ARRAY_CONTAINS(@p1, c.version) "
        "AND (c.ts >= @p2lo AND c.ts <= @p2hi)"
    )
    assert parameters == [
        {"name": "@kind", "value": "deployment"},
        {"name": "@p0", "value": "checkout-api"},
        {"name": "@p1", "value": ["v1", "v2"]},
        {"name": "@p2lo", "value": "2026-06-01T00:00:00Z"},
        {"name": "@p2hi", "value": "2026-06-30T00:00:00Z"},
    ]


def test_presence_and_absence_bind_nothing():
    text, parameters = translate(
        _query(predicates=[Predicate(field="resolved_at", op=PredicateOp.ABSENT)])
    )
    assert "(NOT IS_DEFINED(c.resolved_at) OR IS_NULL(c.resolved_at))" in text
    assert parameters == [{"name": "@kind", "value": "incident"}]


def test_the_count_form_carries_no_row_limit_because_it_returns_no_rows():
    """A count answers with one value, so there are no rows for a limit to bound, and Cosmos
    rejects every form that tries to impose one. The limit is still mandatory in the structure;
    what bounds this form's work is the deadline.

    Asserted as the exact text because the earlier bounded form also passed a text assertion and
    was refused by the source: a golden query proves the translator consistent, never valid."""
    text, _ = translate(_query(projection=[], aggregate="count", limit=25))
    assert text == "SELECT VALUE COUNT(1) FROM c WHERE c.kind = @kind"
    assert "TOP" not in text


def test_no_caller_supplied_string_reaches_the_query_text():
    """Field names are written from the approved surface, never from the request, so a name is not
    a place a fragment can be smuggled through. The value still travels as a parameter."""
    text, parameters = translate(
        _query(predicates=[Predicate(field="category", op=PredicateOp.EQ, value="x' OR 1=1 --")])
    )
    assert "1=1" not in text
    assert parameters[1]["value"] == "x' OR 1=1 --"


# --- what a refusal is ---------------------------------------------------------------------------
def test_a_structure_referencing_an_ungranted_collection_is_refused_before_execution():
    """The check a reviewer expects to be redundant. The collection is on the approved surface and
    the structure is well formed; it was simply not granted to this request, and being expressible
    is not the same as being permitted."""
    query = _query(collection="alert", projection=["alert_id"])
    validate(query)  # approved outright
    with pytest.raises(QueryRejected, match="not granted"):
        validate(query, frozenset({"incident"}))


@pytest.mark.parametrize(
    "query,reason",
    [
        (_query(collection="log", projection=["message"]), "approved surface"),
        (_query(projection=["root_cause"]), "approved surface"),
        (
            _query(predicates=[Predicate(field="resolution", op=PredicateOp.EQ, value="x")]),
            "approved surface",
        ),
        (_query(predicates=[Predicate(field="made_sla", op=PredicateOp.EQ, value="yes")]), "type"),
        (
            _query(predicates=[Predicate(field="category", op=PredicateOp.GT, value="a")]),
            "operation",
        ),
        (
            _query(
                predicates=[Predicate(field="state", op=PredicateOp.BETWEEN, low="a", high="b")]
            ),
            "operation",
        ),
    ],
)
def test_a_structure_off_the_approved_surface_is_refused(query, reason):
    with pytest.raises(QueryRejected, match=reason):
        validate(query)


def test_the_answer_bearing_fields_are_absent_from_the_surface():
    """This path lets a model choose its own projection, and the corpus carries its own answers.
    Excluding them from the surface is what makes them unaskable rather than merely unasked."""
    incident = APPROVED_SURFACE["incident"]
    for field in ("root_cause", "resolution", "close_code", "short_description"):
        assert field not in incident
    assert "note" not in APPROVED_SURFACE["deployment"]


def test_a_limit_is_mandatory_and_bounded_by_the_ceiling():
    with pytest.raises(ValueError):
        _query(limit=config.STRUCTURED_QUERY_MAX_LIMIT + 1)
    with pytest.raises(ValueError):
        StructuredQuery(collection="incident", projection=["incident_id"])  # no limit at all
    with pytest.raises(ValueError):
        _query(limit=0)


def test_a_query_names_either_a_projection_or_the_count_form():
    with pytest.raises(ValueError):
        _query(projection=[], aggregate=None)
    with pytest.raises(ValueError):
        _query(projection=["incident_id"], aggregate="count")


@pytest.mark.parametrize("absent", ["group_by", "order_by", "having", "sum", "avg", "join"])
def test_the_excluded_operations_have_no_representable_form(absent):
    """Absent from the structure rather than rejected by a rule: unsupported, not
    forbidden-but-expressible."""
    with pytest.raises(ValueError):
        StructuredQuery(
            collection="incident", projection=["incident_id"], limit=5, **{absent: "anything"}
        )


# --- how an outcome becomes two axes -------------------------------------------------------------
def test_rows_are_a_complete_answer():
    container = CannedContainer([{"incident_id": "inc-004"}])
    result = _service(container).structured_query(**_query().model_dump())
    assert result.outcome is ExecutionOutcome.SUCCEEDED
    assert result.completeness is Completeness.COMPLETE
    assert result.results == [{"incident_id": "inc-004"}]


def test_no_rows_is_an_authoritative_absence_not_a_failure():
    result = _service(CannedContainer([])).structured_query(**_query().model_dump())
    assert result.outcome is ExecutionOutcome.SUCCEEDED
    assert result.completeness is Completeness.EMPTY


def test_a_container_that_cannot_answer_is_unavailable():
    result = _service(CannedContainer(unreachable=True)).structured_query(**_query().model_dump())
    assert result.outcome is ExecutionOutcome.UNAVAILABLE
    assert result.completeness is Completeness.NOT_APPLICABLE


def test_a_count_answers_with_its_number():
    container = CannedContainer([7])
    result = _service(container).structured_query(
        **_query(projection=[], aggregate="count").model_dump()
    )
    assert result.results == [{"count": 7}]
    assert result.evidence_refs == [], "a count is about the scope, not a record to cite"


def test_a_refused_query_is_rejected_and_never_reaches_the_container():
    container = CannedContainer([{"incident_id": "inc-004"}])
    service = ToolService(
        OperationalRecords(container), deadline_s=DEADLINE, granted_collections=frozenset({"alert"})
    )
    result = service.structured_query(**_query().model_dump())

    assert result.outcome is ExecutionOutcome.REJECTED
    assert result.completeness is Completeness.NOT_APPLICABLE
    assert result.results == []
    assert container.queries == [], "a rejected query still spent a read"


def test_the_query_carries_the_deadline_it_was_given():
    container = CannedContainer([])
    _service(container).structured_query(**_query().model_dump())
    assert container.timeouts == [DEADLINE]


def test_the_capability_is_reachable_only_through_dispatch():
    container = CannedContainer([{"incident_id": "inc-004"}])
    service = _service(container)
    assert "structured_query" in service.tool_names
    assert service.call("structured_query", **_query().model_dump()).answered
