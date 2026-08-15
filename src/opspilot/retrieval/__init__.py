"""Retrieval over the `knowledge` container: dense Cosmos vector search + in-process lexical
scoring, fused by reciprocal rank fusion (D-003). `corpus.py` is the offline chunker corpus
preparation uses to build that container; nothing at runtime loads the corpus from disk.
"""
