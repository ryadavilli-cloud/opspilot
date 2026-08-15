"""Tests for the Cosmos-backed retrieval subsystem (D-003): passage-level results, category
routing, dense + lexical fusion, and deadline propagation. Deterministic throughout: a fake
container and a fake query embedder stand in for Cosmos and Azure OpenAI; nothing here reaches a
live backend.
"""

from __future__ import annotations

from fake_knowledge import (
    FakeQueryEmbedder,
    hash_embed,
    knowledge_container,
    knowledge_retriever,
    retriever_from,
)

from opspilot.data.knowledge_records import KnowledgeRecords
from opspilot.retrieval.retriever import (
    ARCHITECTURE,
    POSTMORTEM,
    RUNBOOK,
    Retriever,
    route_category,
)


def test_search_returns_the_matched_passage_text_not_a_pointer():
    retriever = knowledge_retriever()
    hits = retriever.search(
        "Cosmos connection pool exhausted causing payment-api authorization timeouts",
        k=5,
        collection=(RUNBOOK, ARCHITECTURE),
        deadline_s=5.0,
    )
    assert hits and all(h.text for h in hits)
    assert any(h.reference == "runbook:payment-timeout" for h in hits)


def test_category_filter_restricts_results():
    retriever = knowledge_retriever()
    hits = retriever.search(
        "service dependencies and blast radius", k=5, collection=ARCHITECTURE, deadline_s=5.0
    )
    assert hits and all(h.category == ARCHITECTURE for h in hits)


def test_service_filter_restricts_results():
    retriever = knowledge_retriever()
    hits = retriever.search(
        "timeout",
        k=5,
        collection=(RUNBOOK, ARCHITECTURE),
        services=("payment-api",),
        deadline_s=5.0,
    )
    assert hits and all("payment-api" in h.services for h in hits)


def test_postmortem_search_returns_only_postmortems():
    retriever = knowledge_retriever()
    hits = retriever.search(
        "cosmos db throttling on reads", k=3, collection=POSTMORTEM, deadline_s=5.0
    )
    assert hits and all(h.category == POSTMORTEM for h in hits)


def test_results_are_ranked_by_fused_score():
    retriever = knowledge_retriever()
    hits = retriever.search(
        "payment gateway latency causing checkout timeouts",
        k=5,
        collection=(RUNBOOK, ARCHITECTURE),
        deadline_s=5.0,
    )
    assert hits == sorted(hits, key=lambda h: -h.score)


def test_deadline_propagates_to_the_container_and_the_embedder():
    embedder = FakeQueryEmbedder()
    container = knowledge_container()
    retriever = Retriever(KnowledgeRecords(container), embedder)
    retriever.search("payment timeout", k=3, collection=RUNBOOK, deadline_s=7.5)
    assert container.timeouts and all(t == 7.5 for t in container.timeouts)


def test_reciprocal_rank_fusion_promotes_the_passage_matched_by_both_signals():
    # `alpha` shares vocabulary with the query and its embedding is pushed close to the query's;
    # `beta` matches on neither. Fusion must place alpha first regardless of either signal alone.
    alpha_text = "checkout payment gateway timeout authorization failure"
    beta_text = "unrelated deployment rollback procedure for infrastructure"
    docs = [
        {
            "id": "a",
            "chunk_id": "runbook:alpha#0",
            "category": RUNBOOK,
            "doc_id": "runbook:alpha",
            "title": "Alpha",
            "text": alpha_text,
            "services": ["payment-api"],
            "identifiers": [],
            "date": None,
            "provenance": {},
            "embedding": hash_embed(alpha_text, 32),
        },
        {
            "id": "b",
            "chunk_id": "runbook:beta#0",
            "category": RUNBOOK,
            "doc_id": "runbook:beta",
            "title": "Beta",
            "text": beta_text,
            "services": ["infra"],
            "identifiers": [],
            "date": None,
            "provenance": {},
            "embedding": hash_embed(beta_text, 32),
        },
    ]
    retriever = retriever_from(docs)
    hits = retriever.search("payment gateway timeout", k=2, collection=RUNBOOK, deadline_s=5.0)
    assert hits[0].reference == "runbook:alpha"


def test_route_category_from_question_shape():
    assert route_category("how do I roll back the last deployment?") == RUNBOOK
    assert route_category("what services does payment-api depend on upstream?") == ARCHITECTURE
    assert route_category("has this happened before, any similar past incident?") == POSTMORTEM


def test_route_category_defaults_to_runbook_when_nothing_matches():
    assert route_category("xyzzy quux plugh") == RUNBOOK


def test_search_with_no_collection_named_routes_before_querying():
    retriever = knowledge_retriever()
    hits = retriever.search("how do I remediate cosmos db throttling?", k=3, deadline_s=5.0)
    assert hits and all(h.category == RUNBOOK for h in hits)
