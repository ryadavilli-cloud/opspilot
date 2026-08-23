"""Tests for the corpus identity a run records beside its deployment and prompt versions (D-012).

Two properties carry the whole point of the value and are asserted from both directions here: it
must not move when the corpus did not, or every comparison across two runs reports a difference
that is not there; and it must move when retrieval would return or rank anything differently, or
two incomparable runs go on looking comparable. Everything else is a consequence of those.

Deterministic throughout: a fake container and a fake query embedder stand in for Cosmos and Azure
OpenAI, and the authored corpus is shaped by preparation itself rather than by a fixture that
would be free to shape it differently.
"""

from __future__ import annotations

from typing import Any

from fake_knowledge import (
    FakeKnowledgeContainer,
    knowledge_container,
    knowledge_documents,
    knowledge_retriever,
)
from fake_operational_records import corpus_records

from opspilot.data.knowledge_records import KnowledgeRecords
from opspilot.retrieval.fingerprint import embedding_identity, fingerprint
from opspilot.retrieval.retriever import Retriever
from opspilot.tools.service import ToolService

EMBEDDING = embedding_identity("text-embedding-3-small", 1536)


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "runbook~payment-timeout~0",
        "category": "runbook",
        "doc_id": "runbook:payment-timeout",
        "title": "Payment timeout",
        "text": "When payment-api times out, check the gateway before the deploy history.",
        "services": ["payment-api"],
        "identifiers": ["payment-api", "504"],
        "date": None,
    }
    row.update(overrides)
    return row


def _of(*rows: dict[str, Any]) -> str:
    return fingerprint(rows, embedding=EMBEDDING)


# --- the value follows the corpus and nothing else ----------------------------------------------


def test_the_same_corpus_fingerprints_the_same_way_twice():
    assert _of(_row()) == _of(_row())


def test_the_order_rows_arrive_in_does_not_change_the_value():
    first, second, third = _row(id="a"), _row(id="b"), _row(id="c")
    assert _of(first, second, third) == _of(third, first, second)


def test_a_set_valued_field_is_a_membership_not_an_ordering():
    assert _of(_row(services=["a", "b"])) == _of(_row(services=["b", "a"]))
    assert _of(_row(identifiers=["504", "payment-api"])) == _of(
        _row(identifiers=["payment-api", "504"])
    )


def test_what_retrieval_cannot_act_on_does_not_contribute():
    """Provenance, the untranslated chunk id, and the embedding vector itself.

    Nothing in the query path branches on whether a passage is a distractor, the chunk id is the
    id already hashed in another notation, and a vector is a function of the text and the
    deployment that produced it. A value that moved with any of them would report a corpus change
    where retrieval would return exactly what it returned before.
    """
    bare = _row()
    decorated = _row(
        chunk_id="runbook:payment-timeout#0",
        provenance={"source": "data/distractors", "doc_id": "runbook:payment-timeout"},
        embedding=[0.1, 0.2, 0.3],
    )
    assert _of(bare) == _of(decorated)


# --- the value moves when retrieval would ------------------------------------------------------


def test_edited_passage_text_changes_the_value():
    assert _of(_row()) != _of(_row(text="Something else entirely."))


def test_an_added_passage_changes_the_value():
    assert _of(_row()) != _of(_row(), _row(id="second", doc_id="runbook:other"))


def test_metadata_retrieval_reads_changes_the_value():
    """Each of these decides whether a passage is a candidate, how it ranks, or what a passage
    says it is when it comes back."""
    baseline = _of(_row())
    assert baseline != _of(_row(category="postmortem"))
    assert baseline != _of(_row(services=["checkout-api"]))
    assert baseline != _of(_row(identifiers=["payment-api"]))
    assert baseline != _of(_row(doc_id="runbook:other"))
    assert baseline != _of(_row(title="Another title"))
    assert baseline != _of(_row(date="2026-06-01T00:00:00Z"))


def test_an_absent_date_and_an_empty_one_are_different_corpora():
    assert _of(_row(date=None)) != _of(_row(date=""))


def test_the_same_passages_under_another_embedding_are_another_corpus():
    """The passages are unchanged to the character; the vector space they are searched in is not,
    so a run against one cannot be compared with a run against the other."""
    rows = [_row()]
    assert fingerprint(rows, embedding=EMBEDDING) != fingerprint(
        rows, embedding=embedding_identity("text-embedding-3-large", 1536)
    )


def test_one_deployment_at_two_dimensions_is_two_corpora():
    rows = [_row()]
    assert fingerprint(
        rows, embedding=embedding_identity("text-embedding-3-small", 1536)
    ) != fingerprint(rows, embedding=embedding_identity("text-embedding-3-small", 256))


# --- what the retriever reports over the authored corpus ---------------------------------------


def test_the_retriever_reports_the_corpus_it_searches():
    """Computed from what the container holds, and equal to the value taken over the prepared
    documents directly: the store and the checkout describe one corpus."""
    retriever = knowledge_retriever()
    expected = fingerprint(knowledge_documents(), embedding=embedding_identity("hash-embed", 32))
    assert retriever.corpus_fingerprint(deadline_s=5.0) == expected


def test_the_corpus_is_read_once_however_often_it_is_asked_for():
    """A re-seed is a deployment and a deployment is a new process, so the corpus cannot move
    underneath a running one. Paying for the whole container per investigation would buy nothing."""
    container = knowledge_container()
    retriever = Retriever(KnowledgeRecords(container), _CountingEmbedder())
    first = retriever.corpus_fingerprint(deadline_s=5.0)
    reads = len(container.queries)
    assert retriever.corpus_fingerprint(deadline_s=5.0) == first
    assert len(container.queries) == reads


def test_the_read_carries_the_whole_corpus_rather_than_a_capped_page():
    """Every other read here is capped, and a capped identity would stop changing the moment the
    corpus outgrew the cap while going on reporting that two corpora are one."""
    container = knowledge_container()
    rows = KnowledgeRecords(container).corpus_rows(deadline_s=5.0)
    assert len(rows) == len(knowledge_documents())
    assert not any("TOP" in query for query in container.queries)


def test_a_changed_passage_in_the_container_changes_what_the_retriever_reports():
    documents = knowledge_documents()
    before = Retriever(
        KnowledgeRecords(knowledge_container()), _CountingEmbedder()
    ).corpus_fingerprint(deadline_s=5.0)

    documents[0] = {**documents[0], "text": documents[0]["text"] + " and one more sentence."}
    after = Retriever(
        KnowledgeRecords(FakeKnowledgeContainer(documents)), _CountingEmbedder()
    ).corpus_fingerprint(deadline_s=5.0)
    assert before != after


class _CountingEmbedder:
    """An embedder with a fixed identity, so a test about the corpus is not also a test about
    which embedder a fixture happened to build."""

    dimensions = 32

    def embed(self, text: str, *, deadline_s: float) -> list[float]:
        return [0.0] * self.dimensions

    @property
    def identity(self) -> str:
        return embedding_identity("hash-embed", self.dimensions)


# --- an unnamed corpus is a blank field, never a failure ---------------------------------------


def test_an_unreachable_container_leaves_the_corpus_unnamed():
    """The record then says the corpus was not recorded. Failing the investigation over a field it
    never reads would trade the whole result for the identity of the corpus that produced it."""
    service = ToolService(
        corpus_records(),
        retriever_factory=lambda: Retriever(
            KnowledgeRecords(knowledge_container(unreachable=True)), _CountingEmbedder()
        ),
    )
    assert service.corpus_fingerprint == ""


def test_a_service_with_no_reachable_retriever_leaves_the_corpus_unnamed():
    def unavailable() -> Retriever:
        raise RuntimeError("no credential")

    service = ToolService(corpus_records(), retriever_factory=unavailable)
    assert service.corpus_fingerprint == ""
    assert service.retrieval_backend == "unavailable"


def test_the_service_reports_the_corpus_its_retriever_searches():
    service = ToolService(corpus_records(), retriever_factory=knowledge_retriever)
    assert service.corpus_fingerprint == knowledge_retriever().corpus_fingerprint(deadline_s=5.0)
