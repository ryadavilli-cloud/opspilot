# ADR — Retrieval backend & index: outcome parity, versioned profiles, temporal bounds (G-56, G-52)

**Status:** accepted — AI Search adapter unbuilt · **Stage:** 8 (backend) / 6a (temporal bounds) ·
**Relates:** [G-56](./status.md#g-56), [G-52](./status.md#g-52) · **Companion to** `data-and-evidence.md`
§6/§11 (retrieval), `deployment.md` §11 and `decisions.md` §13.1 ("Retrieval model", "Knowledge
delivery").

Records the *retrieval-backend/index-schema* decision that code-guidelines §19 requires an ADR for. The
retrieval design lives in `data-and-evidence.md` §11; this ADR is the *parity contract*, the
*embedding-profile migration*, and the *temporal-isolation bounds*.

---

## Context

The dev pipeline (a local dense embedder + BM25 fused with RRF + a cross-encoder reranker) and Azure AI
Search hybrid (vector + full-text combined with RRF, then a semantic reranker over a candidate set) are
**different retrieval systems**. Framing prod parity as "near-identical ranking within a declared
tolerance" tests an algorithm equivalence that was never the goal and can *fail on a better prod
ranking*. Separately, swapping `bge-small-en-v1.5` → BGE-M3 was drawn as a config flip, but it changes
embedding **dimensionality and index contents**. And nothing today bounds retrieval by time, so a
replayed historical scenario can retrieve a postmortem written *after* the incident resolved.

## Decision

1. **Parity is outcome compatibility, not ranking equality.** Ranking may differ; the conclusion
   the agent can reach must not. The contract table (result schema, filtering, as-of, a shared
   Precision@K/MRR floor, required-target recall) is
   [`data-and-evidence.md` §11](./data-and-evidence.md).
2. **The embedder is a versioned embedding profile** (part of `corpus_snapshot_id`); a profile
   change is an **index-rebuild/migration** with its own re-embed → re-run-floor → re-baseline
   gate. "Config-swappable" describes the *seam*, not the *operation*.
3. **Temporal isolation is mandatory** ([G-52](./status.md#g-52)): the temporal fields are
   **required arguments** and a call missing them fails closed; the bounds table is
   [`data-and-evidence.md` §4](./data-and-evidence.md#sec-4).

## Consequences

- Contract tests pin *outcomes*, so the local and prod backends can evolve independently within the floor.
- An embedder swap is an operational migration, not a flag toggle — reversible only by rebuild.
- `corpus_snapshot_id` pins the index generation, which is also what makes cassette replay and the
  answer-key closure gate reproducible.
- The AI Search adapter must honor the same `as_of`/snapshot filters as the local retriever, or the two
  disagree on what is visible.
