"""The reference model: one parser, one type map, one resolver.

The checks a reviewer would not think to write are the ones about the boundary between the two
reference types, and about a reference that is well formed but names nothing. Both are places
where a permissive answer looks like success.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from opspilot.data.repository import Repository
from opspilot.evidence.references import (
    PREFIX_TYPES,
    RETIRED_PREFIXES,
    CitationRole,
    Reference,
    ReferenceError,
    ReferenceResolver,
    ReferenceType,
    entities_named,
    parse,
    reference_type_of,
    role_is_admissible,
    try_parse,
)

EVIDENCE_REFS = [
    "logs:payment-api:evt-001-01",
    "metrics:checkout-api:http_5xx_rate@2026-05-12T14:30:00Z",
    "deploys:payment-api:dep-20260512-01",
    "deps:checkout-api->payment-api",
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


# --- citation-role compatibility is decidable from type alone ---------------------------------
def test_evidence_may_occupy_any_citation_role():
    assert all(role_is_admissible(ReferenceType.EVIDENCE, role) for role in CitationRole)


def test_knowledge_may_only_occupy_the_historical_role():
    """A document cannot observe the running system, so retrieved knowledge can never carry
    current operational support. Letting it would turn 'the runbook says' into current proof."""
    assert role_is_admissible(ReferenceType.KNOWLEDGE, CitationRole.HISTORICAL_CONTEXT)
    assert not role_is_admissible(ReferenceType.KNOWLEDGE, CitationRole.CURRENT_SUPPORT)
    assert not role_is_admissible(ReferenceType.KNOWLEDGE, CitationRole.CURRENT_CONTRADICTION)


def test_architecture_is_knowledge_and_so_carries_no_current_support():
    """Architecture docs orient an investigation but are not evidence about this incident. That
    restriction rides on the reference type rather than on a special case at any call site."""
    parsed = parse("architecture:service-dependency-map")
    assert parsed.is_knowledge
    assert not role_is_admissible(parsed.reference_type, CitationRole.CURRENT_SUPPORT)


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
    return ReferenceResolver()


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
    resolver = ReferenceResolver()
    result = resolver.resolve("logs:payment-api:evt-does-not-exist")
    assert result.reference.prefix == "logs"
    assert result.resolved is False
    assert result.record is None


def test_a_metric_reference_off_the_sample_instant_does_not_resolve():
    """The instant is part of the reference. A near-miss resolving would let a citation point at a
    sample that never existed."""
    resolver = ReferenceResolver()
    assert not resolver.resolves("metrics:redis-cache:used_memory_pct@2026-06-22T11:36:00Z")


def test_a_reversed_dependency_edge_does_not_resolve():
    """Direction carries the meaning: checkout depends on redis, not the reverse."""
    resolver = ReferenceResolver()
    assert resolver.resolves("deps:checkout-api->redis-cache")
    assert not resolver.resolves("deps:redis-cache->checkout-api")


def test_resolves_is_false_for_a_malformed_reference_rather_than_raising():
    assert ReferenceResolver().resolves("past_incident:inc-001") is False


def test_resolution_accepts_an_already_parsed_reference():
    resolver = ReferenceResolver()
    parsed = parse("deps:checkout-api->redis-cache")
    assert resolver.resolve(parsed).resolved


def test_resolver_reads_an_injected_repository_rather_than_the_default():
    repo = Repository.from_records(
        logs=[{"service": "svc-a", "event_id": "evt-9", "ts": "2026-01-01T00:00:00Z"}]
    )
    resolver = ReferenceResolver(repo=repo)
    assert resolver.resolves("logs:svc-a:evt-9")
    assert not resolver.resolves("logs:svc-a:evt-8")


def test_reference_dataclass_is_frozen():
    parsed = parse("logs:payment-api:evt-001-01")
    with pytest.raises(AttributeError):
        parsed.raw = "logs:other:evt-2"  # type: ignore[misc]
    assert isinstance(parsed, Reference)
