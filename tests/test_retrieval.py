"""Retrieval tests — corpus/chunking, retriever behavior, and the hybrid-beats-baseline proof.

Skipped entirely if the eval extras (sentence-transformers) aren't installed, so the core suite
still runs without the ML stack. Building the retriever embeds the corpus once (module fixture).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("sentence_transformers")
pytest.importorskip("rank_bm25")

from opspilot.retrieval.corpus import chunk, load_docs  # noqa: E402
from opspilot.retrieval.retriever import Retriever  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_golden():
    spec = importlib.util.spec_from_file_location(
        "retrieval_eval", REPO_ROOT / "eval/retrieval_eval.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EVAL = _load_golden()


@pytest.fixture(scope="module")
def retriever() -> Retriever:
    return Retriever(include_distractors=True)


@pytest.fixture(scope="module")
def scores(retriever):
    golden = EVAL.load_golden()
    return {
        "dense": EVAL.evaluate(retriever, golden, mode="dense", k=5),
        "hybrid": EVAL.evaluate(retriever, golden, mode="hybrid", k=5),
    }


def test_corpus_loads_labeled_and_distractor_docs():
    docs = load_docs(include_distractors=True)
    assert any(not d.is_distractor for d in docs) and any(d.is_distractor for d in docs)
    assert len([d for d in docs if not d.is_distractor]) == 12  # the KB
    assert len([d for d in docs if d.is_distractor]) >= 15      # the haystack


def test_chunking_carries_doc_metadata():
    doc = next(d for d in load_docs(False) if d.kind == "runbook")
    chunks = chunk(doc)
    assert chunks and all(c.doc_id == doc.doc_id and c.kind == "runbook" for c in chunks)


def test_retriever_returns_ranked_doc_hits(retriever):
    hits = retriever.hybrid("payments timing out at checkout", k=5)
    assert hits and all(isinstance(h.doc_id, str) for h in hits)
    assert hits == sorted(hits, key=lambda h: -h.score)  # ranked


def test_metadata_filter_restricts_kind(retriever):
    hits = retriever.dense("service dependencies and blast radius", k=5, kinds=("architecture",))
    assert hits and all(h.kind == "architecture" for h in hits)


def test_hybrid_beats_or_matches_dense_baseline(scores):
    """The Phase 4 proof point: hybrid is never worse than vector-only, and better on a metric."""
    d, h = scores["dense"], scores["hybrid"]
    assert h["MRR"] >= d["MRR"] - 1e-9, f"hybrid regressed MRR: {h} vs {d}"
    improved = h["MRR"] > d["MRR"] + 1e-9 or h["P@5"] > d["P@5"] + 1e-9
    assert improved, f"hybrid did not improve over baseline on any metric: {h} vs {d}"


def test_retrieval_hits_a_reasonable_bar(scores):
    """Advisory floor (target is MRR>0.80, reached with rerank + BGE-M3 in 4d; advisory for now)."""
    assert scores["hybrid"]["MRR"] >= 0.65, scores
