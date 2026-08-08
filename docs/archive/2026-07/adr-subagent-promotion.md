# ADR — Multi-agent promotion: conditional, threshold-gated, observable (G-25)

**Status:** accepted (topology form) — promotion *timing* is **open decision §13.2 (B)** · **Stage:** 6c
· **Relates:** [G-25](./status.md#g-25) · **Companion to** `workflow-design.md` §7 and `decisions.md`
§13.1 ("Orchestration topology"), §13.2 (B).

Records the *multi-agent-promotion* decision that code-guidelines §19 requires an ADR for. The subagent
design lives in `workflow-design.md` §7; this ADR separates the *settled form* from the *conditional
trigger*, and fixes the *observability rule*.

---

## Context

An earlier draft declared "supervisor + subagents-as-tools" a settled decision, while §7 itself notes
**nothing currently forces the promotion**. Declaring the promotion settled is premature: a subgraph is
not free — it adds a planning boundary, a prompt, model calls, schemas, failure handling, and an eval
surface. A promotion could land, be measured "no regression", and still deliver nothing.

## Decision

**The topology *form* is settled; *whether* to promote a given step is conditional and defaults to
not promoted.** If promoted, a gathering step is a LangGraph **subgraph wrapped as a tool**, never a
handoff — and promotion happens only when a **declared scorecard threshold** is cleared (the
knowledge subagent's bar is the `knowledge_grounding` axis; a telemetry subagent needs its own).
This is open decision §13.2 (B): the shape is settled, the trigger is not. **Quarantine hides noise
from the parent context, not from observability** — a subagent still emits a hierarchical trace
under the parent `trace_id` and an audit record. Both rules in full:
[`workflow-design.md` §7](./workflow-design.md#sec-7).

## Consequences

- The default is a single diagnosis loop; promotion is a deliberate, measured step, not scaffolding.
- The `knowledge_grounding` axis must exist **before** the knowledge-subagent refactor, or the promotion
  is unfalsifiable.
- "Clean context" and "clean trace" are different requirements; the eval surface sees the parent's
  structured result *and* can drill into the child thread.
