# ADR — Persistence backend: Cosmos DB, several containers (G-02, G-48)

**Status:** accepted · **Stage:** 5b (seam + SQLite dev saver) / 5f (Cosmos activation on Azure) / 8 (container split completes) · **Relates:**
[G-02](./status.md#g-02), [G-48](./status.md#g-48) · **Companion to** `deployment.md` §12 and
`decisions.md` §13.1 ("State store").

Records the *persistence-backend* decision that code-guidelines §19 requires an ADR for. The high-level
choice (Cosmos over Postgres) and the storage design live in `deployment.md` §12; this ADR is the *why
the earlier lean flipped*, and the *container architecture the one-line "Cosmos DB" hides*.

---

## Context

An interrupt-driven, scale-to-zero design makes durable state non-negotiable: a paused
(`awaiting_approval`) run and an in-flight run must both survive a replica being reclaimed. An earlier
ADR leaned **Postgres** for one reason only — a Cosmos LangGraph saver would have been bespoke code on
the critical path. That premise is gone: LangChain now ships the first-party
`langchain-azure-cosmosdb` saver (`CosmosDBSaver`), MS-endorsed and keyless via
`DefaultAzureCredential`.

"Checkpointer + Store = Cosmos DB" is then a *technology* pick that stops short of the *storage
architecture*. Treated as one container it hides real structure.

## Decision

**Cosmos DB**, keyless, behind a `build_checkpointer()` seam (`none` / `memory` / `sqlite` dev /
`cosmos` prod; unknown → `ValueError`), modeled as **several workloads, not one container**. The
per-workload container table (partition key / TTL / ACL), the two load-bearing properties that
follow from the split (least-privilege across containers; cross-container writes are not atomic —
hence the §8 record-then-resume ordering), and the at-least-once change-feed rules live in
[`deployment.md` §12](./deployment.md#sec-12) and are not restated here.

## Consequences

- Serverless Cosmos suits `minReplicas = 0` (no always-on ~$15–20/mo Postgres, no connection pool for
  bursty scale) and is keyless like the LLM and store paths.
- Dev/CI runs the SQLite saver behind the same seam; the resume gate is
  `write → fresh saver on the same store → checkpoint recovered`.
- One backend serves checkpointer **and** Store; the verified-postmortem sync needs no outbox table
  beyond the change feed.
