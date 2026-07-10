"""Retrieval over the KB corpus — dense baseline + hybrid (dense + BM25).

Local dev uses a small sentence-transformers model + an in-memory index; production swaps in Azure
AI Search hybrid behind the same `Retriever` interface (the retrieval analogue of the repository
seam). `search_runbooks` / `search_past_incidents` graduate onto this in the next slice.
"""
