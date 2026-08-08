# ADR — Async dispatch: durable outbox → queue, with ownership fencing (G-34)

**Status:** accepted — **resolves former open decision §13.2 (D)** · **Stage:** 5f · **Closes:**
[G-34](./status.md#g-34) · **Companion to** `workflow-design.md` §8 and `decisions.md` §13.1 ("Durable
dispatch", "Ownership fencing").

Records the *async-dispatch* decision that code-guidelines §19 requires an ADR for. The pause/resume
protocol lives in `workflow-design.md` §8; this ADR is the *why the working-default recovery was
unsound*, and the *dispatch + fencing decision that replaced it*.

---

## Context

`POST /investigations` returned `202` and ran the graph as **post-response background work** — not an
honest `202` behind an HTTP scaler, which counts active requests and can reclaim a scale-to-zero
replica mid-round with nothing to re-drive the run. The full failure analysis — why the two
working-default recovery mechanisms (startup sweep, resume-on-poll) are each unsound under
scale-to-zero, and why a bare lease races its replacement — lives in
[`workflow-design.md` §8](./workflow-design.md#sec-8) (*Dispatch is durable*) and is not restated
here.

## Decision

**Durable dispatch, in v1** (Service Bus is not deferred to v2):

```
POST /investigations
   └─ Cosmos transaction (one logical partition): investigation record + dispatch-outbox record
   └─ 202
change feed → Service Bus message
queue-triggered worker (KEDA queue scaler) → checkpointed graph
```

The transactional outbox makes accept + dispatch atomic; the **queue scaler wakes a worker on a queued
message**, which the HTTP scaler structurally cannot do for a post-response thread — so this composes
*with* scale-to-zero rather than fighting it.

**Ownership fencing.** A lease answers *is the worker gone*; a monotonic **fencing epoch** answers
*am I still the owner* — only the second is safe to write against, so every state transition writes
conditionally on ETag + epoch and a lapsed-but-alive worker fails closed. `awaiting_approval` is
exempt from lease expiry. Mechanism detail: [`workflow-design.md` §8](./workflow-design.md#sec-8).

## Consequences

- Service Bus is a **v1** dependency; external-source *ingestion* (Event Grid ← monitoring/ITSM) stays
  the v2 add.
- The queue messages are versioned Pydantic (operation + investigation id + workflow version +
  correlation), idempotent consumers, tested lock renewal, classified
  abandon/defer/dead-letter/complete.
- The outbox is one of the Cosmos containers ([`adr-checkpointer-cosmos.md`](./adr-checkpointer-cosmos.md));
  cross-container non-atomicity is exactly why the decision leg is record-then-resume (§8).
