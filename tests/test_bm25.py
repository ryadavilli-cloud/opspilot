"""BM25 runtime retriever — lexical retrieval with no ML stack.

Exercises the deterministic runtime backend: kind/service filtering, distractor exclusion, and the
guarantee that no embedder is constructed. Needs only rank-bm25 (a runtime dependency), so it runs
in the minimal CI lane.
"""

from __future__ import annotations

from opspilot.config import DISTRACTOR_DIR, KB_DIR
from opspilot.retrieval.bm25 import BM25Retriever


def _bm25() -> BM25Retriever:
    return BM25Retriever(KB_DIR)


def test_backend_name_is_bm25():
    assert _bm25().backend_name == "bm25"


def test_runbook_query_returns_a_runbook():
    hits = _bm25().search("payment gateway authorization timeout", k=5,
                          kinds=("runbook", "architecture"))
    assert hits and any(h.kind == "runbook" for h in hits)


def test_architecture_query_returns_an_architecture_doc():
    hits = _bm25().search("service dependencies blast radius architecture", k=5,
                          kinds=("architecture",))
    assert hits and all(h.kind == "architecture" for h in hits)


def test_kind_filter_restricts_results():
    hits = _bm25().search("checkout failures", k=5, kinds=("postmortem",))
    assert hits and all(h.kind == "postmortem" for h in hits)


def test_service_filter_restricts_results():
    retriever = _bm25()
    services = {d.doc_id: set(d.services) for d in retriever.docs}
    hits = retriever.search("payment authorization timeout", k=5, services=("payment-api",))
    assert hits and all("payment-api" in services.get(h.doc_id, set()) for h in hits)


def test_distractors_are_never_loaded_in_production_mode():
    # include_distractors defaults False even when a distractor dir is provided.
    retriever = BM25Retriever(KB_DIR, DISTRACTOR_DIR)
    assert retriever.docs and all(not d.is_distractor for d in retriever.docs)


def test_no_embedder_is_constructed_for_bm25(monkeypatch):
    import opspilot.retrieval.embeddings as embeddings

    def _boom(*_args, **_kwargs):
        raise AssertionError("BM25 mode must not construct an embedder")

    monkeypatch.setattr(embeddings.Embedder, "__init__", _boom)
    retriever = BM25Retriever(KB_DIR)  # would raise if it touched the embedder
    assert retriever.search("payment", k=3)
