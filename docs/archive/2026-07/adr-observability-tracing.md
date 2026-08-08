# ADR — Observability & tracing: an emission seam at the primitives, sinks split from spans (G-61, G-08)

**Status:** accepted — emission built (#46/#48) · **Stage:** 5g (emission) / 7 (MCP span) / 8
(LangSmith sink) / 11 (aggregation) · **Relates:**
[G-61](./status.md#g-61), [G-08](./status.md#g-08), [G-25](./status.md#g-25) · **Companion to**
[`code-guidelines.md` §23](./code-guidelines.md#23-observability-and-tracing-the-emission-seam),
`execution-plan.md` (Stage 5g), and `evaluation.md` §10.

Records the *observability/tracing emission seam* decision that code-guidelines §19 requires an ADR
for. The rule set lives in §23; this ADR is *where emission lives*, *what a span carries*, and *why
emission is split from aggregation*.

---

## Context

The system is an incident-investigation assistant whose whole premise is telemetry-driven diagnosis,
yet its own runs emit no spans: `trace_id` is not propagated, no usage is captured, and the
"Observability layer" is unbuilt ([G-61](./status.md#g-61)). This bit hard in practice — a deploy
failure escalated with a reason that was only visible in the API response, not in any log, because
nothing traced the run. Two failure modes must be avoided: (1) per-node hand-instrumentation, which
drifts as nodes are added and produces inconsistent spans; and (2) building the *aggregation* stack
(App Insights, dashboards, drift canary, hard gate) early, which is Stage 11 work and would couple a
cross-cutting seam to a heavy backend before the seam is even proven.

## Decision

**Emission is instrumented once, at four shared primitives — never per node.** One span-emitting
wrapper each at: the **node dispatch path**, **`run_tool` / `gateway.execute`**, the **`ChatModel`
client**, and the **MCP client**. A new node, tool, subagent, or boundary inherits a span with no
per-site code; hand-instrumenting a node, or emitting a span/usage record outside the schema, is a
prohibited pattern (§21).

**Every span carries the standard attribute set** under the parent `trace_id`: `trace_id`,
`investigation_id`, `incident_id`, `workflow_version`, `prompt_version`, `model_deployment`,
`tool_name` + `canonical_args_hash` + `result_hash`, retrieved doc ids, `latency_ms`, tokens
(in/out), cost, and tool `status`. A span outside this schema is a defect, not a variant. Subagent /
MCP / A2A boundary spans **nest under the parent `trace_id`** — quarantine removes noise from the
parent *context*, never from the *trace* ([G-25](./status.md#g-25)).

**Spans are OTLP-shaped; the sink is chosen by config, split from emission.** Emission (Stage 5g)
ships `none` / `memory` / `stdout` exporters plus per-model **usage capture** into the normalized usage
record ([`adr-model-provider.md`](./adr-model-provider.md)) — **capture, not enforcement** (the budget
is [G-08](./status.md#g-08) at Stage 6b). The **local LangSmith Developer** sink is the same
config-selected exporter seam pointed at a real backend, and lands at **Stage 8**, with the dev-local /
synthetic-or-scrubbed and PII-aware retention rules it must obey ([G-57](./status.md#g-57)). The **App
Insights** export target, dashboards, drift monitoring, the live canary, and arming the hard gate are
**Stage 11** and MUST NOT be built early.

Each sink is a stage, not a wish: **5g** local exporters → **8** LangSmith Developer → **11** App
Insights. A deferred sink with no stage is how the seam quietly ends up write-only.

**Emission adds zero cassette churn.** `trace_id`, span attributes, and the usage record are **not**
behaviour-affecting inputs, so they sit outside the replay manifest ([G-54](./status.md#g-54)) —
instrumentation may land at any stage with no re-record.

**Tested, not asserted.** A reusable **in-memory span-exporter** fixture proves "emitted a span under
the parent `trace_id` with the required attributes", riding the state-contract + smoke lanes.

## Consequences

- A single seam means the already-merged loop, HITL, and 8 tools become traceable in one pass, and
  every later stage (6a's widened call sites, 6c/Stage-7 hierarchical traces) inherits spans for free.
- Because emission is manifest-neutral, 5g lands independently of 5e/5f — no frozen-contract churn,
  no re-record — so it parallelizes.
- The sink/exporter split lets the backend change (stdout → LangSmith → App Insights) without touching
  a single emission site; only the exporter config moves. That is also why the sink can be scheduled
  independently of the seam — 5g's spans are usable via `stdout` while the LangSmith exporter waits
  for Stage 8.
- Posture is **advisory now**, a **hard gate at the §7 / 6c hierarchy boundaries** that already
  require nested traces, hardening into a standing review gate once the seam is proven — the same
  "advisory until it gates" shape as the eval discipline.
