"""Tests for the Cosmos-backed retrieval subsystem: passage-level results, the collection and
service filters, dense and lexical fusion, exact-identifier promotion, the passage budget, and
deadline propagation. Every search names the collection it searches, because the retriever does not
choose one. Deterministic throughout: a fake container and a fake query embedder stand in for Cosmos
and Azure OpenAI; nothing here reaches a live backend, and no model ranks anything at any stage.
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
    SECTIONS_PER_INCIDENT,
    Retriever,
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


# --- past incidents come back as incidents ------------------------------------------------------
def _incidents(query: str, k: int = PASSAGE_BUDGET) -> list[Any]:
    return knowledge_retriever().search_incidents(query, k=k, deadline_s=5.0)


def test_one_result_is_one_past_incident():
    """The question is whether this has happened before, so a result is an incident. Five views of
    the write-up that matched most often is one candidate presented five times, which is the
    opposite of what a history worth searching is for."""
    results = _incidents("checkout-api returning 500s shortly after this morning's deployment.")

    references = [p.reference for p in results]
    assert len(references) == len(set(references))
    assert all(ref.startswith("postmortem:") for ref in references)


def test_at_most_the_budget_of_distinct_incidents_comes_back():
    results = _incidents("checkout latency deployment queue cache timeout")
    assert 0 < len(results) <= PASSAGE_BUDGET
    assert len({p.reference for p in results}) == len(results)


def test_a_caller_may_ask_for_fewer_incidents():
    assert len(_incidents("checkout deployment", k=2)) <= 2


def test_an_incident_carries_at_most_two_of_its_sections():
    """Enough that a precedent says what happened and how it was settled, and short of shipping the
    whole write-up for a question that asked which incidents resemble this one."""
    for passage in _incidents("checkout latency deployment queue cache timeout"):
        assert passage.text.count("\n## ") <= SECTIONS_PER_INCIDENT


def test_an_incident_says_its_title_once():
    """Corpus preparation prefixes the title to every section so that ranking can see it. Delivered
    together under one heading, those prefixes would be the same line repeated."""
    for passage in _incidents("checkout-api 500s after a deployment"):
        assert passage.title
        assert passage.text.count(passage.title) == 1
        assert passage.text.startswith(passage.title)


def test_an_incident_never_carries_a_section_that_is_only_its_heading():
    """The opening section of a write-up is the heading and nothing else, and it ranks first on a
    question that echoes the title. It still places its incident; it has no content to send."""
    for passage in _incidents("checkout-api returning 500s after this morning's deployment."):
        body = passage.text[len(passage.title) :].strip()
        assert body, f"{passage.reference} came back with a heading and no content"


def test_an_incident_takes_its_position_from_its_best_section_not_from_how_much_it_holds():
    """Summing what a write-up's sections scored would rank by length: more sections means more
    chances to accumulate, and the longest history would win every question."""
    long_doc = [
        _doc(f"long-{i}", "checkout deployment regression rollback revision") for i in range(8)
    ]
    for row in long_doc:
        row["doc_id"], row["category"] = "postmortem:long", POSTMORTEM
    short_doc = [_doc("short-0", "checkout deployment regression rollback revision")]
    short_doc[0]["doc_id"], short_doc[0]["category"] = "postmortem:short", POSTMORTEM

    retriever = retriever_from(long_doc + short_doc)
    results = retriever.search_incidents("checkout deployment regression", k=5, deadline_s=5.0)

    assert {p.reference for p in results} == {"postmortem:long", "postmortem:short"}
    assert results[0].score == max(p.score for p in results)


def test_grouping_happens_after_promotion_not_before():
    """An identifier lifts the section that carried it. Grouping first would let one mention
    anywhere in a write-up promote every part of it."""
    named = _doc("named", "The reservation queue drained slowly.", identifiers=("dep-20260625-01",))
    named["doc_id"], named["category"] = "postmortem:named", POSTMORTEM
    other = _doc("other", "checkout deployment regression rollback revision")
    other["doc_id"], other["category"] = "postmortem:other", POSTMORTEM

    results = retriever_from([other, named]).search_incidents(
        "what happened around dep-20260625-01", k=5, deadline_s=5.0
    )

    assert results[0].reference == "postmortem:named"


def test_runbook_search_still_answers_with_sections():
    """Guidance is different. A single section can be exactly the right answer to "how is this
    handled", so nothing is grouped there and the same document may answer more than once."""
    results = knowledge_retriever().search(
        "redis cache eviction memory",
        k=PASSAGE_BUDGET,
        collection=(RUNBOOK, ARCHITECTURE),
        deadline_s=5.0,
    )

    assert results
    assert all(p.category in {RUNBOOK, ARCHITECTURE} for p in results)


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


def test_one_search_spends_one_deadline_across_its_internal_operations():
    """A search embeds, then searches by vector, then reads candidates. Given the same duration
    each, three sequential operations could take three times what the caller allowed while every
    one of them honoured its own bound. The deadline is fixed once and spent down, so what a later
    operation gets is what is actually left."""
    embedder = FakeQueryEmbedder()
    container = knowledge_container()
    retriever = Retriever(KnowledgeRecords(container), embedder)

    retriever.search("payment timeout", k=3, collection=RUNBOOK, deadline_s=7.5)

    assert container.timeouts, "the container was reached without a deadline"
    assert all(0 < timeout <= 7.5 for timeout in container.timeouts)
    assert container.timeouts == sorted(container.timeouts, reverse=True), (
        f"a later operation was given more time than an earlier one: {container.timeouts}"
    )


def test_a_search_with_no_time_left_still_bounds_what_it_reaches():
    """Nothing inside a search may treat an exhausted deadline as unbounded."""
    embedder = FakeQueryEmbedder()
    container = knowledge_container()
    retriever = Retriever(KnowledgeRecords(container), embedder)

    retriever.search("payment timeout", k=3, collection=RUNBOOK, deadline_s=0.0)

    assert container.timeouts
    assert all(timeout == 0.0 for timeout in container.timeouts)


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
