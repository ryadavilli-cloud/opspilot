"""The reference model: one parser, one type map, one resolver.

The checks a reviewer would not think to write are the ones about the boundary between the two
reference types, and about a reference that is well formed but names nothing. Both are places
where a permissive answer looks like success.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fake_operational_records import corpus_records, log_documents, records_from

from opspilot.data.operational_records import OperationalRecords
from opspilot.evidence.admission import admit
from opspilot.evidence.operations import TurnEvidence
from opspilot.evidence.references import (
    PREFIX_TYPES,
    RETIRED_PREFIXES,
    Reference,
    ReferenceError,
    ReferenceResolver,
    ReferenceType,
    entities_named,
    parse,
    reference_type_of,
    try_parse,
)
from opspilot.tools.contracts import Completeness, ExecutionOutcome, ToolMetadata, ToolResult

EVIDENCE_REFS = [
    "logs:payment-api:evt-001-01",
    "metrics:checkout-api:http_5xx_rate@2026-05-12T14:30:00Z",
    "deploys:payment-api:dep-20260512-01",
    "deps:checkout-api->payment-api",
    "absence:get_deployments:op-0007",
]
KNOWLEDGE_REFS = [
    "runbook:payment-timeout",
    "architecture:service-dependency-map",
    "postmortem:inc-001",
]


# --- the type map is the single discriminator -------------------------------------------------
def test_every_prefix_has_exactly_one_declared_type():
    assert set(PREFIX_TYPES) == {
        "logs",
        "metrics",
        "deploys",
        "deps",
        "absence",
        "runbook",
        "architecture",
        "postmortem",
    }
    assert all(isinstance(v, ReferenceType) for v in PREFIX_TYPES.values())


@pytest.mark.parametrize("raw", EVIDENCE_REFS)
def test_evidence_prefixes_parse_as_evidence(raw):
    assert reference_type_of(raw) is ReferenceType.EVIDENCE


@pytest.mark.parametrize("raw", KNOWLEDGE_REFS)
def test_knowledge_prefixes_parse_as_knowledge(raw):
    assert reference_type_of(raw) is ReferenceType.KNOWLEDGE


def test_the_prefix_map_is_not_mutable_by_a_caller():
    with pytest.raises(TypeError):
        PREFIX_TYPES["telemetry"] = ReferenceType.EVIDENCE  # type: ignore[index]


# --- the type alone decides what a reference may be used for -----------------------------------
def test_architecture_is_knowledge_and_so_can_never_be_current_proof():
    """Architecture docs orient an investigation but are not evidence about this incident. That
    restriction rides on the reference type rather than on a special case at any call site."""
    assert parse("architecture:service-dependency-map").is_knowledge


# --- the retired spelling ---------------------------------------------------------------------
def test_the_retired_postmortem_spelling_is_rejected_with_its_replacement():
    """Two spellings for one document would defeat a single resolver and corrupt admission's
    duplicate key, so the retired form fails loudly rather than resolving alongside the canonical
    one."""
    with pytest.raises(ReferenceError, match="retired"):
        parse("past_incident:inc-001")
    assert "past_incident" not in PREFIX_TYPES
    assert RETIRED_PREFIXES["past_incident"] == "postmortem"


# --- parsing shape ----------------------------------------------------------------------------
def test_metric_reference_splits_entity_metric_and_instant():
    parsed = parse("metrics:redis-cache:used_memory_pct@2026-06-22T11:35:00Z")
    assert parsed.entities == ("redis-cache",)
    assert parsed.metric == "used_memory_pct"
    assert parsed.observed_at == datetime(2026, 6, 22, 11, 35, tzinfo=UTC)


def test_dependency_reference_names_both_endpoints():
    assert parse("deps:checkout-api->payment-api").entities == ("checkout-api", "payment-api")


def test_log_and_deploy_references_name_one_service_and_an_identifier():
    assert parse("logs:payment-api:evt-001-01").identifier == "evt-001-01"
    assert parse("deploys:payment-api:dep-20260512-01").entities == ("payment-api",)


# --- authoritative absence ----------------------------------------------------------------------
def test_an_absence_reference_names_its_capability_and_producing_operation():
    parsed = parse("absence:get_deployments:op-0007")
    assert parsed.reference_type is ReferenceType.EVIDENCE
    assert parsed.capability == "get_deployments"
    assert parsed.identifier == "op-0007"


def test_an_absence_reference_is_evidence_not_knowledge():
    """It reports what a scope contained, which is a current operational observation. Classing it
    as knowledge would bar it from standing as support for the claims it can genuinely settle."""
    parsed = parse("absence:query_logs:op-0002")
    assert parsed.is_evidence and not parsed.is_knowledge


def test_a_bare_operation_reference_is_still_not_an_evidence_reference():
    """An operation names an attempt, not an observation. Embedding one inside an absence
    reference must not make the bare form citable."""
    for raw in ("op-0001", "op-0007"):
        with pytest.raises(ReferenceError):
            parse(raw)
        assert try_parse(raw) is None


def test_an_absence_reference_names_no_entity():
    """The queried scope is carried by the admitted observation, not smuggled into the reference:
    a capability name is not a service, and treating it as one would put it into cause analysis."""
    assert parse("absence:get_deployments:op-0007").entities == ()
    assert entities_named(["absence:get_deployments:op-0007"]) == set()


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "logs",
        "logs:",
        "nonsense:payment-api:evt-1",
        "deps:checkout-api",
        "metrics:checkout-api:http_5xx_rate",
        "metrics:checkout-api:http_5xx_rate@not-a-time",
        "metrics:checkout-api:http_5xx_rate@2026-05-12T14:30:00",
        "runbook:a:b",
        "absence:",
        "absence:get_deployments",
        "absence::op-0007",
        "absence:get_deployments:",
        "absence:get_deployments:op-0007:extra",
    ],
)
def test_malformed_references_raise_rather_than_degrade(raw):
    with pytest.raises(ReferenceError):
        parse(raw)
    assert try_parse(raw) is None


def test_a_naive_metric_timestamp_is_refused():
    """Without the trailing Z an instant is ambiguous, and a citation that resolves against the
    wrong instant is worse than one that fails."""
    with pytest.raises(ReferenceError, match="UTC"):
        parse("metrics:checkout-api:http_5xx_rate@2026-05-12T14:30:00")


# --- entity extraction ------------------------------------------------------------------------
def test_entities_named_collects_services_and_ignores_knowledge():
    found = entities_named(EVIDENCE_REFS + KNOWLEDGE_REFS)
    assert found == {"payment-api", "checkout-api"}


def test_entities_named_ignores_unparseable_entries():
    assert entities_named(["logs:payment-api:evt-1", "garbage", ""]) == {"payment-api"}


# --- resolution -------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def resolver() -> ReferenceResolver:
    return ReferenceResolver(corpus_records())


@pytest.mark.parametrize(
    "raw",
    [
        "logs:checkout-api:evt-005-01",
        "metrics:redis-cache:used_memory_pct@2026-06-22T11:35:00Z",
        "deps:checkout-api->redis-cache",
        "runbook:redis-cache-degradation",
        "architecture:service-dependency-map",
        "postmortem:inc-001",
    ],
)
def test_authored_references_resolve_against_the_real_corpus(resolver, raw):
    assert resolver.resolve(raw).resolved


def test_a_wellformed_reference_that_names_nothing_is_unresolved_not_malformed():
    """The distinction matters: malformed means nobody can interpret it, unresolved means it was
    interpreted fine and the thing is not there. Collapsing them hides a corpus gap as a syntax
    error."""
    resolver = ReferenceResolver(corpus_records())
    result = resolver.resolve("logs:payment-api:evt-does-not-exist")
    assert result.reference.prefix == "logs"
    assert result.resolved is False
    assert result.record is None


def test_a_metric_reference_off_the_sample_instant_does_not_resolve():
    """The instant is part of the reference. A near-miss resolving would let a citation point at a
    sample that never existed."""
    resolver = ReferenceResolver(corpus_records())
    assert not resolver.resolves("metrics:redis-cache:used_memory_pct@2026-06-22T11:36:00Z")


def test_a_reversed_dependency_edge_does_not_resolve():
    """Direction carries the meaning: checkout depends on redis, not the reverse."""
    resolver = ReferenceResolver(corpus_records())
    assert resolver.resolves("deps:checkout-api->redis-cache")
    assert not resolver.resolves("deps:redis-cache->checkout-api")


def test_resolves_is_false_for_a_malformed_reference_rather_than_raising():
    assert ReferenceResolver(corpus_records()).resolves("past_incident:inc-001") is False


def test_resolution_accepts_an_already_parsed_reference():
    resolver = ReferenceResolver(corpus_records())
    parsed = parse("deps:checkout-api->redis-cache")
    assert resolver.resolve(parsed).resolved


def test_resolver_reads_the_container_it_was_given():
    records = records_from(
        log_documents([{"service": "svc-a", "event_id": "evt-9", "ts": "2026-01-01T00:00:00Z"}])
    )
    resolver = ReferenceResolver(records)
    assert resolver.resolves("logs:svc-a:evt-9")
    assert not resolver.resolves("logs:svc-a:evt-8")


def test_an_absence_reference_resolves_to_the_admitted_observation(container):
    """An absence has no source row by definition, so it resolves against what admission recorded.
    Resolving it against the container would ask a source to produce the row whose non-existence
    is the finding."""
    turn = TurnEvidence(investigation_id="inv-1", turn_id="turn-1")
    empty = ToolResult(
        tool_name="get_deployments",
        outcome=ExecutionOutcome.SUCCEEDED,
        completeness=Completeness.EMPTY,
        metadata=ToolMetadata(tool_name="get_deployments", duration_ms=1.0, result_count=0),
    )
    outcome = admit(empty, turn=turn, question="did anything change", request_scope={"svc": "a"})
    observation = outcome.observations[0]

    resolver = ReferenceResolver(OperationalRecords(container), absences=turn.observations)
    result = resolver.resolve(observation.evidence_ref)
    assert result.resolved
    assert result.record is observation
    assert result.record.is_authoritative_absence


def test_an_absence_reference_the_resolver_was_not_given_is_unresolved_not_malformed(container):
    """Well formed and naming nothing here. Raising instead would report a turn's own absence as a
    grammar error once the reference travelled outside that turn."""
    resolver = ReferenceResolver(OperationalRecords(container))
    result = resolver.resolve("absence:get_deployments:op-0007")
    assert result.reference.prefix == "absence"
    assert result.resolved is False
    assert result.record is None


def test_a_malformed_absence_reference_does_not_resolve(container):
    assert ReferenceResolver(OperationalRecords(container)).resolves("absence:op-0007") is False


def test_reference_dataclass_is_frozen():
    parsed = parse("logs:payment-api:evt-001-01")
    with pytest.raises(AttributeError):
        parsed.raw = "logs:other:evt-2"  # type: ignore[misc]
    assert isinstance(parsed, Reference)
