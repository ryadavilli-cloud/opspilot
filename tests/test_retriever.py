"""Tests for the Cosmos-backed retrieval subsystem: passage-level results, category routing, dense
and lexical fusion, exact-identifier promotion, the passage budget, and deadline propagation.
Deterministic throughout: a fake container and a fake query embedder stand in for Cosmos and Azure
OpenAI; nothing here reaches a live backend, and no model ranks anything at any stage.
"""

from __future__ import annotations

from typing import Any

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
    PASSAGE_BUDGET,
    POSTMORTEM,
    RUNBOOK,
    Retriever,
    route_category,
)


def _doc(name: str, text: str, *, identifiers: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "id": name,
        "chunk_id": f"runbook:{name}#0",
        "category": RUNBOOK,
        "doc_id": f"runbook:{name}",
        "title": name.title(),
        "text": text,
        "services": ["payment-api"],
        "identifiers": list(identifiers),
        "date": None,
        "provenance": {},
        "embedding": hash_embed(text, 32),
    }


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


def test_results_are_ranked_by_fused_score_when_the_question_names_no_identifier():
    """Fusion decides the order on its own. Promotion is the only thing that may disturb it, and a
    question naming no identifier gives it nothing to act on."""
    retriever = knowledge_retriever()
    hits = retriever.search(
        "why is it slow and what should be checked first",
        k=5,
        collection=(RUNBOOK, ARCHITECTURE),
        deadline_s=5.0,
    )
    assert hits == sorted(hits, key=lambda h: -h.score)


# --- exact-identifier promotion -----------------------------------------------------------------
# `common` shares the question's vocabulary, so both signals rank it above `named` and fusion puts
# it first. `named` shares almost none, and carries the deploy identifier in the field corpus
# preparation extracts rather than in its own text: what lifts it can only be the identifier match,
# never term overlap. The two searches below differ by that identifier and nothing else.
_DEPLOY_ID = "dep-20260512-01"
_QUESTION = "checkout gateway timeout authorization failure"


def _promotion_corpus() -> list[dict[str, Any]]:
    return [
        _doc("common", "checkout gateway timeout authorization failure during payment"),
        _doc("named", "routine cache warmup notes", identifiers=(_DEPLOY_ID,)),
    ]


def test_a_passage_the_question_names_by_identifier_is_promoted_above_a_better_fused_one():
    retriever = retriever_from(_promotion_corpus())

    unnamed = retriever.search(_QUESTION, k=2, collection=RUNBOOK, deadline_s=5.0)
    assert [h.reference for h in unnamed] == ["runbook:common", "runbook:named"]

    named = retriever.search(
        f"{_QUESTION} after {_DEPLOY_ID}", k=2, collection=RUNBOOK, deadline_s=5.0
    )
    assert [h.reference for h in named] == ["runbook:named", "runbook:common"]


def test_promotion_keeps_the_fused_order_among_the_passages_it_lifts():
    """Stable, not re-ranked: promotion partitions, and each side keeps the order fusion gave it.
    Re-scoring the promoted set would be a second ranking nothing asked for."""
    retriever = retriever_from(
        [
            _doc("stronger", f"checkout gateway timeout {_DEPLOY_ID}", identifiers=(_DEPLOY_ID,)),
            _doc("weaker", f"unrelated cache notes {_DEPLOY_ID}", identifiers=(_DEPLOY_ID,)),
            _doc("plain", "checkout gateway timeout authorization"),
        ]
    )
    hits = retriever.search(
        f"{_QUESTION} after {_DEPLOY_ID}", k=3, collection=RUNBOOK, deadline_s=5.0
    )
    assert [h.reference for h in hits[:2]] == ["runbook:stronger", "runbook:weaker"]
    assert hits[0].score >= hits[1].score


def test_promotion_reaches_a_passage_that_fusion_left_below_the_budget():
    """The case promotion exists for. The named passage is last by fusion, so truncating first and
    promoting afterwards could never surface it; promotion runs over the whole fused list."""
    filler = [_doc(f"filler{i}", f"{_QUESTION} variant {i}") for i in range(PASSAGE_BUDGET + 2)]
    retriever = retriever_from([*filler, _doc("named", "cache notes", identifiers=(_DEPLOY_ID,))])

    hits = retriever.search(
        f"{_QUESTION} after {_DEPLOY_ID}",
        k=PASSAGE_BUDGET,
        collection=RUNBOOK,
        deadline_s=5.0,
    )
    assert hits[0].reference == "runbook:named"


def test_the_passage_budget_bounds_what_one_call_returns():
    """A ceiling, not a default. What reaches a prompt is bounded by the budget however much the
    corpus holds and whatever the caller asks for."""
    retriever = retriever_from(
        [_doc(f"passage{i}", f"{_QUESTION} variant {i}") for i in range(PASSAGE_BUDGET + 4)]
    )
    hits = retriever.search(_QUESTION, k=PASSAGE_BUDGET + 4, collection=RUNBOOK, deadline_s=5.0)
    assert len(hits) == PASSAGE_BUDGET


def test_a_caller_may_ask_for_fewer_than_the_budget():
    retriever = retriever_from(
        [_doc(f"passage{i}", f"{_QUESTION} variant {i}") for i in range(PASSAGE_BUDGET + 4)]
    )
    assert len(retriever.search(_QUESTION, k=2, collection=RUNBOOK, deadline_s=5.0)) == 2


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
