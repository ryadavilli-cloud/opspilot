# ADR — Memory-admission policy: two-phase, verified, out-of-graph (G-27, G-33)

**Status:** accepted (placement) — the *gate type* is **open decision §13.2 (E)** · **Stage:** 8 ·
**Relates:** [G-27](./status.md#g-27), [G-33](./status.md#g-33) · **Companion to**
`workflow-design.md` §5 ("Memory admission") and `decisions.md` §13.1 ("Memory writeback"), §13.2 (E).

Records the *memory-admission-policy* decision that code-guidelines §19 requires an ADR for. The
lifecycle lives in `workflow-design.md` §5; this ADR is the *why admission is out of the graph*, and the
*open question of what the gate is*.

---

## Context

Predicted RCA must never enter the retrieval corpus — an unverified conclusion written back as
"knowledge" poisons every future investigation. Verification requires **incident closure**, which
arrives days later from an external system, and parking a LangGraph thread across that interval
breaks three things at once (Cosmos TTL, the async resource's terminal state, and the identity
separation) — the full argument is [`workflow-design.md` §5](./workflow-design.md#sec-5) (*Memory
admission is a separate component*), not restated here.

## Decision

**The investigation graph terminates at `publish`.** Memory admission is a **separate,
closure-event-driven component**: an incident-closed event triggers reconciliation of predicted vs.
confirmed RCA, an admission gate, and only then the write + index — running under the **privileged
publisher identity**, against the preliminary record the investigation left behind.

**The admission gate itself is open decision §13.2 (E):** "policy/human gate" names two controls with
different failure modes — a policy gate admits silently-wrong reconciliations; a human gate does not
scale and stalls the corpus. Working default (c): policy admits exact predicted-vs-confirmed matches,
human reviews divergences — unimplemented, and blocked on the typed reconciliation output
([G-29](./status.md#g-29)). Decide *with* the admission component, not before.

## Consequences

- The anti-poisoning property becomes **testable in isolation**: admission can be exercised without
  running an investigation, and an investigation cannot reach the index even in principle.
- The publisher identity is separate from the diagnosis identity, enforced at the `verified-memory`
  container ACL ([`adr-checkpointer-cosmos.md`](./adr-checkpointer-cosmos.md)).
- The graph gets a terminal state, so the async resource contract and Cosmos TTL both stay honest.
