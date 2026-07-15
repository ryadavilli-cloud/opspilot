"""Retrieval backend factory — maps config to a SearchRetriever, or errors on an unknown backend."""

from __future__ import annotations

import pytest

from opspilot.retrieval.bm25 import BM25Retriever
from opspilot.retrieval.factory import build_retriever


def test_bm25_backend_builds_bm25_retriever():
    retriever = build_retriever("bm25")
    assert isinstance(retriever, BM25Retriever)
    assert retriever.backend_name == "bm25"


def test_unknown_backend_is_a_configuration_error():
    with pytest.raises(ValueError, match="unknown retrieval backend"):
        build_retriever("faiss-someday")


def test_hybrid_backend_builds_the_hybrid_adapter():
    pytest.importorskip("sentence_transformers")
    from opspilot.retrieval.adapters import HybridRetrieverAdapter

    retriever = build_retriever("hybrid")
    assert isinstance(retriever, HybridRetrieverAdapter)
    assert retriever.backend_name == "hybrid"
