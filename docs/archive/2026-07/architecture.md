# OpsPilot — Architecture

**Target architecture for an agentic AI incident-investigation assistant on Azure.**

OpsPilot ingests a cloud incident alert, investigates it like an on-call engineer, and produces an
evidence-backed root-cause report — grounded in runbooks, past incidents, and live telemetry, with a
human approval gate before anything consequential, and full observability, evaluation, guardrails,
and cost controls around it.

---

> **Document map.** This architecture was split from one file into a set. Section numbers (`§N`) are
> preserved across the set — follow the map to the file that holds each:
>
> | § | Topic | File |
> |---|---|---|
> | [§1](architecture.md#sec-1)–[§3](architecture.md#sec-3), [§9](architecture.md#sec-9), [§14](architecture.md#sec-14) | Problem, context, strategy, A2A, risk themes | [`architecture.md`](./architecture.md) |
> | [§4](data-and-evidence.md#sec-4), [§6](data-and-evidence.md#sec-6) (tool contracts + retrieval), §11 retrieval | Evidence models, citation grammar, tool/retrieval contracts | [`data-and-evidence.md`](./data-and-evidence.md) |
> | [§5](workflow-design.md#sec-5), [§7](workflow-design.md#sec-7), [§8](workflow-design.md#sec-8) | Control flow, subagents, HITL protocol | [`workflow-design.md`](./workflow-design.md) |
> | [§6](data-and-evidence.md#sec-6) (MCP security), §10 (observability/reliability/cost/admission), §11 (models/provider), [§12](deployment.md#sec-12) | Azure topology, identity, reliability, scale/DR | [`deployment.md`](./deployment.md) |
> | §10 evaluation, §11 data | Scorecards, cassettes, corpus, current numbers | [`evaluation.md`](./evaluation.md) |
> | [§13](decisions.md#sec-13) | Architecture decisions (register) | [`decisions.md`](./decisions.md) |
> | — | Glossary | [`glossary.md`](./glossary.md) |
> | — | Build status + gap register | [`status.md`](./status.md) |
> | — | Execution plan | [`execution-plan.md`](./execution-plan.md) |

---

### How to read this set

This file is the **entry point** to the OpsPilot target architecture, which is split across the set in
the document map above. This file holds the problem framing ([§1](architecture.md#sec-1)), context and constraints ([§2](architecture.md#sec-2)), the
solution strategy ([§3](architecture.md#sec-3)), the service boundary ([§9](architecture.md#sec-9)), and the standing risk *themes* ([§14](architecture.md#sec-14)). The control
flow, data/evidence contracts, deployment, decisions, and evaluation each have their own file; **§N
references resolve via the map** — a "[§5](workflow-design.md#sec-5)" points at `## 5.` in `workflow-design.md`, and so on.

> **Design, status, and numbers are deliberately separated — across files.** Every file in this set is
> *target design* plus a one-line **Status** header per section that cites gap ids; none re-describes a
> defect in prose. **What exists / doesn't / is wrong** lives in **[`status.md`](./status.md)** (the gap
> register, stable ids `G-01 …`); **current scores and the corpus** live in
> **[`evaluation.md`](./evaluation.md)**; **decisions and their rationale** live in
> **[`decisions.md`](./decisions.md)**. A design file cites the gap id or the eval *axis*, never a
> filename, a constant, or a measured value — one description, one place, no drift. The two tables below
> (lifecycle vocabulary and the absent-properties index) are shared front-matter for the whole set.

#### Lifecycle vocabulary

Every **Status** header uses these states and no others. Each implies the ones above it; a section
may carry more than one, scoped to a part.

| State | Means |
|---|---|
| `proposed` | Designed here. No implementation, no branch. |
| `in review` | Implemented and open as a pull request against `main`. |
| `on branch` | Code exists on a named branch and is **not** in `main` — therefore **not part of the built system**, and not citable as a capability. |
| `merged` | In `main`, behind the required CI checks. |
| `deployed` | Running in the live Azure demo deployment ([§12](deployment.md#sec-12)). |
| `verified` | Deployed *and* demonstrated by something that could have failed — an eval axis, the smoke gate, or a test whose producer is on the production path. |

`merged` ≠ `verified` is the distinction that matters most here: several capabilities are in `main`
and running while the property they claim is unmeasured — see the theme *Claims outrunning
enforcement* ([§14](architecture.md#sec-14)).

#### What this document describes but the running system does not do

Target-vs-built is tracked in exactly two places, not re-tabulated here: each section's **Status**
header names its own absent properties, and the **gap register** ([`status.md`](./status.md)) holds
the full set with severity, kind, and target stage. Two gaps deserve singling out because they
falsify *headline* claims rather than roadmap items: retrieval reasoning
([G-04](./status.md#g-04) — "grounded in runbooks and past incidents" is not yet a property of the
running system) and coherence ([G-07](./status.md#g-07) — the effective stop rule is coverage-only).
Nothing in the register is merely pending polish.

The current single-region, demo-tier deployment is called out as such in [§12](deployment.md#sec-12) — a **demo deployment**,
not a highly-available production one.

---

<a id="sec-1"></a>
## 1. Problem, goals & non-goals

Detection and alerting are solved; **investigation** is where incident response is slow. Engineers
arrive cold and burn the bulk of MTTR on log-diving and context-gathering before the root cause is
even named. OpsPilot compresses that gap: it gathers evidence, forms a grounded hypothesis, and hands
the engineer a cited report to approve.

The framing is **regulated ops** — nothing consequential happens without an approval gate, everything
is traced and audited, and the system degrades gracefully rather than going silent. The domain *is*
the AgentOps / AI-SRE discipline.

**Goals.**

| | |
|---|---|
| **G1 — Compress time-to-hypothesis** | Gather the evidence an on-call engineer would gather, and name a root cause, without a human driving the search. |
| **G2 — Every claim is grounded** | A published conclusion cites only evidence a tool actually produced. Fabricated or self-certified citations are structurally impossible, not merely discouraged. |
| **G3 — Code decides when to stop** | Sufficiency is a deterministic gate over gathered evidence, never model confidence. |
| **G4 — Nothing publishes without a human** | An approval gate binds a verified reviewer to exact report bytes. |
| **G5 — Never silent** | Every degradation and escalation carries a machine-readable reason. |
| **G6 — Measurably better than a deterministic floor** | A retained non-LLM baseline the agent must beat on a versioned scorecard. |

**Non-goals (v1).**

- **Remediation.** External production systems are read-only. Fixing is v2, behind a separate
  allowlisted action server.
- **Alerting or detection.** OpsPilot consumes incidents; it does not produce them.
- **Chat.** `info_only` is a scoped deterministic service-question path, not a general assistant
  ([G-10](./status.md#g-10) tracks the current over-broad behavior).
- **High availability.** Demo-tier deployment; HA is documented as a target in [§12](deployment.md#sec-12), not claimed.
- **Fine-tuning.** Considered and deferred — Appendix C.

---

<a id="sec-2"></a>
## 2. Context, scope & constraints

### System context

```
        ┌──────────────┐     incident alert      ┌───────────────────┐
        │  Monitoring  │ ──────────────────────► │                   │
        │  / ITSM      │                         │     OpsPilot      │
        └──────────────┘                         │                   │
                                                 │  investigate →    │
   ┌───────────────────────┐   read-only         │  cited report     │
   │ Telemetry & platform  │ ◄────────────────── │                   │
   │ logs · metrics ·      │                     │                   │
   │ deploys · deps        │                     └─────┬────────┬────┘
   └───────────────────────┘                           │        │
                                                       │        │ report
   ┌───────────────────────┐   read + verified write   │        ▼
   │ Knowledge base        │ ◄─────────────────────────┘   ┌──────────┐
   │ runbooks · postmortems│                               │  Human   │
   └───────────────────────┘                               │ reviewer │
                                                           └──────────┘
```

**Actors.** An *incident source* (monitoring/ITSM) triggers an investigation. A *human reviewer*
approves, edits, or rejects the report — the only actor who can cause publication. An optional
*upstream orchestrator* may invoke OpsPilot as an A2A service ([§9](architecture.md#sec-9)).

**Trust boundaries.** Everything crossing into the reasoning core is **untrusted data**: telemetry
rows, retrieved passages, and incident free-text can all carry injected instructions. The agent's
identity (managed identity, inference + reads) is deliberately distinct from the *publisher* identity
that writes verified postmortems ([§12](deployment.md#sec-12)), and from the *reviewer* identity that authorizes publication
([§8](workflow-design.md#sec-8)).

### Scope

| In v1 | Out of v1 |
|---|---|
| Read-only investigation over telemetry, platform and KB | Any mutating action on an external system |
| Cited root-cause report + human approval | Autonomous publication |
| Preliminary postmortem memory, admitted only after closure + reconciliation | Direct writeback of predicted RCA into the retrieval corpus |
| Async job API (202 + poll + decision) **over a durable dispatch queue** (Cosmos outbox → Service Bus → queue-triggered worker, [§8](workflow-design.md#sec-8)) | External-source **ingestion** queue (Event Grid ← monitoring/ITSM) — v2 |
| Single-region demo deployment | Multi-region / HA |

### Constraints

- **Provider-agnostic core.** No vendor type crosses into graph nodes; LLM, retrieval, and
  checkpointer are adapter seams (§11, [§12](deployment.md#sec-12)). Prod is mostly adapter swaps.
- **Cost.** Scale-to-zero (`minReplicas = 0`) is a deliberate cost choice, which makes durability of
  paused work a hard requirement rather than a nicety ([§8](workflow-design.md#sec-8)).
- **Reproducible evaluation.** The LLM scorecard must gate CI without an API call — satisfied by
  cassette replay (§10).
- **Self-authored corpus.** Ground truth must be exact and provenance clean, so the primary corpus is
  synthetic; real datasets calibrate *distributions* only (§11).

### Quality attributes

Ranked — where they conflict, the higher one wins.

| Priority | Attribute | Concretely |
|---|---|---|
| 1 | **Groundedness** | Zero unsupported citations. A published claim resolves to tool-produced evidence. |
| 2 | **Auditability** | Every run reconstructible: prompt version, model version, tool calls, evidence, guardrail decisions, approval identity + hash. |
| 3 | **Correctness** | `rca_correctness` and `red_herring_avoidance` against a versioned baseline; correlation must not be reported as causation. |
| 4 | **Bounded cost** | Every run terminates inside a call/token/cost/deadline budget ([G-08](./status.md#g-08)). |
| 5 | **Graceful degradation** | Partial evidence yields a disclosed-degraded result, never a normal-looking one. |
| 6 | **Latency** | Meaningful, but explicitly traded away for the four above — batching ([§3](architecture.md#sec-3)) is the one place latency won. |

---

<a id="sec-3"></a>
## 3. Solution strategy

> **Status:** `deployed` — deterministic floor + `single_agent` · gaps: [G-22](./status.md#g-22)

A **hybrid**: a deterministic LangGraph skeleton (an orchestrator-worker + routing *workflow*)
wrapping a genuinely agentic **plan→act→observe core**. Stage order is fixed code — auditable and
testable. Autonomy is concentrated in exactly two places: **which evidence to gather** (the loop) and
**what it means** (one synthesis node). It is *not* in the stop rule, not in the validation, and not
in the rendering.

> **One reasoning authority.** The evidence loop does not conclude; `synthesize_claims` does, once,
> and nothing downstream re-interprets its output. The failure this rules out is two LLM calls
> reaching different root causes — one steering the gathering and the stop decision, the other
> steering the report and the coherence checks — with no mechanism to notice they disagree. [§5](workflow-design.md#sec-5) states
> the rule and what the built system does instead ([G-40](./status.md#g-40)).

```
POST /investigations → 202 → ingest → triage_router → [route] → retrieve
                                                                    │
   ┌───────────────────────────────────────────────────────────┐    ▼
   │                                                           └─ (plan → act → observe)⟲
   │                                                                       │
   │   GATHERING GATE ── evidence + plan state only ──────────► gathering_sufficiency
   │                                                                       │ gathered
   │                                                                       ▼
   │   ONE CONCLUSION ── produced once, never revised ────────► synthesize_claims
   │                                                                       │
   │   CONCLUSION GATE ── typed claim + citation roles ───────► coherence_check
   │                                                                    │   │ coherent
   └── not coherent: re-reason → re-gather → escalate (ladder, §5) ◄────┘   ▼
       DETERMINISTIC ── formatting only, no new claims ────────► render_report
                                                                           │
                                                   safety_validate ◄───────┘
                                                          └──► hitl_gate ⏸ run ends here,
                                                                status = awaiting_approval

POST /investigations/{id}/decision ──► [approve / edit→revalidate / reject]
   → finalize_report → publish → END          ← the investigation graph is DONE here

              ┄┄┄ separate, closure-event-driven (§5) ┄┄┄
   incident closed (ITSM/Event Grid) → reconcile predicted vs confirmed RCA
                                     → admission gate → verified_postmortem → index
```

The pause is **not** a blocked thread inside one long request. The run terminates at `hitl_gate`'s
`interrupt()`, the checkpoint holds the state, and a *later, separate* request re-enters the graph on
the same `thread_id`. This is the shape the async job API and the HITL gate must agree on, and it is
why both halves must be durable before scale-to-zero is safe ([§8](workflow-design.md#sec-8), [§12](deployment.md#sec-12)).

### The agentic core is unrolled to the graph level

Rather than hidden inside one node. Unrolling was justified by three concrete benefits:
checkpointing *between individual actions*, per-action cost accounting, and clean cancellation.

**Built coarser than that:** `diagnose` executes a *batch* per round, not one tool — the deterministic
floor's `run_cycle` runs every not-yet-answered plan question in one call (up to 4), and `LLMPlanner`
batches up to `_MAX_BATCH = 6` tool calls per round.

**Batching is a deliberate latency call, but its cost is paid explicitly.** The three benefits are
**re-derived at round granularity as requirements**, not left as incidental losses:

1. **Checkpoint between rounds** — LangGraph gives this for free, since `diagnose` re-enters as a
   node. Retained by construction.
2. **Cost accounting per round** — the `IterationBudget` attributes tokens/calls/cost to a round, and
   a round is the smallest unit at which the breaker can fire. A runaway batch of up to
   `_MAX_BATCH = 6` calls is the minimum overshoot the budget must tolerate.
3. **Cancellation at round boundaries** — a checkpoint/cost cancel signal is honored between rounds,
   never mid-batch, so re-entry is always from a clean node boundary.

The contradiction detector ([§5](workflow-design.md#sec-5)) is likewise a *per-round* check for the same reason: batching removed
the per-action seam where it would otherwise have run.

> **Round-only cancellation is not a hard wall-clock deadline — and the deadline is a quality
> attribute ([§2](architecture.md#sec-2)).** A batch of up to `_MAX_BATCH = 6` network calls can exceed any reserve estimated
> from "a full batch's latency after the last check," so "every run terminates inside a deadline"
> cannot be guaranteed by checking only between rounds. The deadline must be enforced **inside** the
> batch, not merely accounted for around it ([G-47](./status.md#g-47)). The rule, before dispatching
> a batch:
>
> 1. **Reserve** the remaining call/cost budget for the batch (the `IterationBudget` split, [§5](workflow-design.md#sec-5)).
> 2. **Derive a per-call deadline** from the investigation deadline and the time already spent —
>    every model and tool/MCP call carries its own timeout beneath the run-level one ([§5](workflow-design.md#sec-5)'s per-call
>    bounds).
> 3. **Propagate cancellation** into each concurrent tool/MCP request (a shared cancel token /
>    deadline context), so a call in flight when the deadline passes is actually aborted.
> 4. **On deadline expiry, cancel outstanding calls** and **return partial envelopes** for the ones
>    that completed — a timed-out call yields a `timeout` `ToolResult` ([§6](data-and-evidence.md#sec-6)) whose rows are a prefix,
>    not a silent hang.
>
> The run then finalizes **disclosed-degraded** on whatever landed, rather than blowing the deadline
> waiting on the slowest call in the batch. Checkpointing at round granularity is fine; *cancellation*
> at round granularity is not.

**Corollary — advancement is a contract, not an optimization.** Because `diagnose` re-enters, each
invocation must *advance*: the plan tracks which questions are answered and state reducers deduplicate.
Otherwise re-entry repeats identical work and appends duplicate evidence until the budget burns out —
an observed failure, not a hypothetical one (see R-04 in `status.md`).

### Layering

The **operational layer** (observability, guardrails, reliability, cost, evaluation) wraps every node
as cross-cutting middleware (§10). External-system access goes through an **outbound MCP adapter
boundary** — MCP is that boundary, *not* a layer that wraps report synthesis, routing, validation, or
state transitions ([§6](data-and-evidence.md#sec-6)). At the service boundary, OpsPilot publishes an **A2A Agent Card** so the whole
assistant is composable as a network service ([§9](architecture.md#sec-9)).

---

<a id="sec-9"></a>
## 9. Service boundary — A2A *(stretch)*

> **Status:** `proposed` — Stage 12 stretch

OpsPilot publishes an Agent Card at `/.well-known/agent-card.json` so a higher-level incident
orchestrator can discover and invoke it over HTTP. A2A is used **only here**, at the boundary — not
between internal subagents, which are co-located in one graph and would gain only latency and failure
surface from a network protocol. Demonstrating *when not to* use a network protocol is the point as
much as the card itself.

The card is generated against a **pinned protocol version**, not hand-maintained as an approximate
example, and advertises only capabilities the endpoint implements: since the core exposes async job
semantics (202 + poll) rather than task streaming, `streaming` is **not** claimed.

```json
{
  "protocolVersion": "<pinned>",
  "name": "opspilot",
  "description": "Agentic incident investigation — returns an evidence-backed root-cause report",
  "url": "https://<app>/a2a/opspilot",
  "capabilities": { "streaming": false },
  "skills": [{ "id": "investigate_incident", "name": "Incident Investigation",
               "tags": ["sre", "incident", "rca", "agentops"] }]
}
```

---

<a id="sec-10"></a>
## 10. Security & guardrails

Security is not one section — it spans the set. The **trust boundaries** are in [§2](architecture.md#sec-2) (everything crossing
into the reasoning core is untrusted data; the agent, publisher, and reviewer identities are distinct).
The **input/output guardrail pipeline** is here. The rest lives with its owner: **system-level admission
control** (auth, roles, quotas, global limits), **MCP per-server least-privilege**, and the **three-identity
model** are in [`deployment.md`](./deployment.md) ([§6](data-and-evidence.md#sec-6) MCP contract, §10 admission, [§12](deployment.md#sec-12) identities);
**grounding provenance** (the tool-gateway ledger) and the **evidence-manifest hash** are in
[`data-and-evidence.md`](./data-and-evidence.md) ([§4](data-and-evidence.md#sec-4)) and [`workflow-design.md`](./workflow-design.md) ([§8](workflow-design.md#sec-8));
the **HITL publication control** is in `workflow-design.md` ([§8](workflow-design.md#sec-8)). This section is the guardrail pipeline.

### Guardrails

**The guardrail pipeline is an explicit sequence, not an ambient property of the model host.** Every
untrusted input — the alert free-text, and *all* retrieved/telemetry content — passes the same ordered
stages before and after the provider call:

```
untrusted input
   → PII policy (Presidio; redact/route per the fail-closed table)
   → prompt-shield / document-attack scan (direct + XPIA/indirect)
   → delimit + mark as untrusted data (content transformation)
   → provider call
   → output safety (content classification)
   → schema + citation + coherence validation (§5)
```

The first three stages guard *what reaches the model*; the last two guard *what leaves it*. Retrieved
content is treated as **untrusted data** at the same standard as the alert text — runbooks,
postmortems, incident notes, and telemetry (log messages in particular are attacker-influenceable) are
delimited, and instructions embedded inside evidence are never followed.

> **Content Safety is application-level configuration on the Claude path, not automatic at model
> deployment.** Selecting Content Safety in [§12](deployment.md#sec-12) does *not* silently wrap the model — for Claude on
> Foundry, filtering must be configured at the application layer; it is not provided by default at the
> deployment. **Prompt Shields** covers both direct user-prompt attacks and document/indirect (XPIA)
> attacks, which is exactly the alert-text + retrieved-content threat model above — so it is a
> pipeline stage OpsPilot wires in, drawn as such, not a checkbox on the LLM resource
> ([G-46](./status.md#g-46)).

**Output.** Schema validation; citation requirement + unsupported-claim detector on grounded RCA
reports. `info_only` is *not* a general chat escape hatch — it is restricted to deterministic
**service** questions ("what is the status of investigation X?", "what evidence sources exist?"). Any
claim about the incident, infra, deployment, runbook, or past resolution stays grounded and cited, via
a scoped `service_answer` node rather than a blanket exemption ([G-10](./status.md#g-10)).

**Policy is risk-specific, never blanket fail-open:**

| Component unavailable | Behavior |
|---|---|
| Injection classifier / Prompt Shields | **Restricted deterministic mode** — see below |
| PII detector | Do not send data to an external model |
| Citation validator | Do not publish a grounded RCA |
| Telemetry tool | Continue **degraded**, explicitly disclose the gap |
| Cost tracker | Fall back to a conservative hard call limit |
| **Model provider, mid-run** | **Undefined today — see below** |

> **What "restricted deterministic mode" actually permits.** With no injection/attack scan available,
> the run may not feed untrusted free-text to the model at all. It falls back to the **deterministic
> planner/triager** over the *structured* evidence (typed telemetry facts, [§4](data-and-evidence.md#sec-4)) — which carries no
> attacker-authored instructions — and **suppresses the free-text surfaces** the scan would have
> guarded: retrieved passage text is withheld from the prompt (refs only), and `info_only`/service
> answers are limited to their fixed deterministic set. The run completes **disclosed-degraded** or
> escalates; it does not silently proceed with unscanned input, and it never publishes a grounded RCA
> built on text the classifier never saw.

**Action guardrail:** the v2 allowlist. Enforced today: the read-only tool registry — the loop cannot
execute a tool outside `READ_ONLY_TOOLS`.

<a id="sec-14"></a>
## 14. Risks, gaps & technical debt

**The register lives in [`status.md`](./status.md)** — build status by component, every gap with a
stable id, severity, kind, and target stage, plus a resolved log. This section records only the
*standing risk themes* that outlive any individual gap.

| Theme | Why it recurs | Current instances |
|---|---|---|
| **Claims outrunning enforcement** | A property described in this document can be true of the *design* and false of the *system*, with nothing to detect the difference. The defense is an eval axis or a test per architectural claim — not prose. | [G-04](./status.md#g-04), [G-06](./status.md#g-06), [G-07](./status.md#g-07), [G-26](./status.md#g-26) |
| **Controls as conventions** | A guardrail enforced by *where code happens to write* rather than by *what the type system permits* degrades with every new node. The defense is a single trusted writer (the tool gateway), not a shared channel — and never a mere field, which validates shape but not provenance. | [G-05](./status.md#g-05) |
| **Deterministic in form only** | A code-owned check whose *input* the model controls inherits the model's discretion — the determinism is in the comparison, not in the outcome. The defense is to derive the input from typed facts where possible, to admit rather than trust what the model asserts, and to make every relabeling itself a detectable event. | [G-43](./status.md#g-43), [G-44](./status.md#g-44) · *related: model-flagged contradictions ([§5](workflow-design.md#sec-5))* |
| **Two components owning one decision** | When two nodes can each produce a conclusion, they will eventually produce different ones, and the system has no place to notice. The defense is a single authority per decision, stated structurally rather than by convention. | [G-40](./status.md#g-40), [G-30](./status.md#g-30) |
| **Checks specified against data that does not exist** | A rule can be precise, falsifiable, and still unimplementable because the pipeline never carried the fields it compares. The defense is to land the fact and the check together, across the tool seam. | [G-42](./status.md#g-42), [G-29](./status.md#g-29) |
| **Technology named, architecture assumed** | Naming a service ("Cosmos", "Foundry", "Content Safety") reads as a design, but a managed product is several workloads, several surfaces, or an opt-in — and the gap hides in what the name papered over. The defense is to model the workloads/adapters/stages explicitly, never treat the vendor name as the design. | [G-45](./status.md#g-45), [G-46](./status.md#g-46), [G-48](./status.md#g-48) |
| **Guarantees weakened by the granularity they're enforced at** | A property asserted at run/round granularity (a deadline, a result contract) can be silently violated inside a coarser unit — a batch overruns a per-run deadline, a degraded rung ships under the RCA type. The defense is to enforce the guarantee at the granularity it's promised, and to type the thing being promised. | [G-47](./status.md#g-47), [G-49](./status.md#g-49) |
| **Fields that exist without an enforcement path** | A budget field, a hash, or a dimension can be computed and never read — reading as enforced while enforcing nothing. The defense is landing the field and its check in the same change. | [G-07](./status.md#g-07), [G-08](./status.md#g-08), [G-36](./status.md#g-36) · *closed: R-07* |
| **Cost choices that become correctness choices** | Scale-to-zero, severity tiering, and batching are all economy measures that silently cap rigor or durability. The defense is naming the coupling and bounding it. | [G-02](./status.md#g-02), [G-12](./status.md#g-12), [G-22](./status.md#g-22), [G-34](./status.md#g-34) |
| **The prose says more than the structure enforces** | A human-readable field that "is never parsed," or a report whose secondary claims are free text, lets the model assert what no check validates — the audit trail then attests to prose the gate never saw. The defense is to render prose from validated structure, and to type *every* claim the guarantee names, not just the headline one. | [G-50](./status.md#g-50), [G-51](./status.md#g-51) |
| **Open surface, agentic backend** | An unauthenticated endpoint in front of an LLM is a spend exposure; in front of an *approval gate* it is an integrity exposure. The integrity half is closed — the decision endpoint now authenticates ([G-01](./status.md#g-01), #36); the spend half (general ingress) is still open. | [G-01](./status.md#g-01) *(closed)*, [G-03](./status.md#g-03) |
| **Evaluation scoring itself** | A metric that can read the answer key, or a component measured only in isolation, certifies nothing. | [G-06](./status.md#g-06), [G-11](./status.md#g-11), [G-19](./status.md#g-19), [G-52](./status.md#g-52), [G-54](./status.md#g-54), [G-55](./status.md#g-55) |
| **Time is a hidden input** | Retrieval, topology, and the corpus all have a version and an as-of; leaving them implicit lets an investigation see documents that did not exist when it began. The defense is to make the temporal bounds mandatory arguments and pin the snapshot. | [G-52](./status.md#g-52), [G-56](./status.md#g-56) |
| **Per-run bound ≠ system bound** | A control that bounds one investigation (cost, budget) says nothing about N of them at once — the exhaustion is at the system layer. The defense is admission control (auth, roles, quotas, global concurrency, rate ceilings) above the per-run budget. | [G-57](./status.md#g-57), [G-03](./status.md#g-03) |

---

## Appendices — moved out

The former appendices are no longer part of the core architecture:

- **Appendix A — Technology coverage** (every technique considered, in/substituted/out) → **[`technology-coverage.md`](./technology-coverage.md)** *(showcase)*
- **Appendix B — Traceability** (component → dimension → capability) → **[`traceability.md`](./traceability.md)** *(showcase)*
- **Appendix C — Fine-tuning: considered and deferred** → **[`decisions.md`](./decisions.md)** (a deferred decision)
- **Appendix D — Glossary** (ref grammar + shared vocabulary) → **[`glossary.md`](./glossary.md)**

---
