# OpsPilot — Deployment

**Part of the OpsPilot architecture set.** Azure topology, the LLM provider seam and model routing, storage/identity, reliability and scale, observability, cost, and system-level admission control.

> **Document map & `§N` resolver:** the map in [`architecture.md`](./architecture.md).

---

## 6 (infra). MCP boundary — security & incident source

*The tool-boundary bulk ([§6](data-and-evidence.md#sec-6): tool contracts, knowledge/telemetry passages, envelope, MCP exposure) is
in [`data-and-evidence.md`](./data-and-evidence.md). This is the infrastructure half — how the servers
authenticate, isolate, and where the incident source sits.*

### MCP is a boundary with a security and operational contract, not just a transport

> **Status:** `proposed` — the parity scaffold proves the transport; none of the contract below exists · gaps: [G-24](./status.md#g-24), [G-53](./status.md#g-53)

Proving envelope parity across the seam (the built scaffold) shows the *shape* survives the network. It
says nothing about the properties a production network boundary must carry. The target server contract:

| Concern | Requirement |
|---|---|
| **Transport + protocol version** | Pinned MCP protocol version, negotiated at connect; a client/server version mismatch fails the handshake, it does not silently degrade |
| **Authentication** | The agent authenticates to each server with its **managed identity** (Entra token), keyless — the same posture as the LLM and store paths ([§12](deployment.md#sec-12)) |
| **Per-tool authorization** | Each server authorizes *per tool*, not per connection — a caller cleared for `query_logs` is not thereby cleared for a future tool on the same server |
| **Least-privilege data plane** | **Each server's managed identity holds only the underlying read permissions its own tools need** — the telemetry server can read logs/metrics and nothing else; the platform server reads deploys/deps and nothing else. This is the real read-only enforcement; the client-side `READ_ONLY_TOOLS` list is a convenience, not a control |
| **Server-side read-only enforcement** | Read-only is enforced **at the server and at the identity's RBAC**, not only in the client loop — a compromised or buggy client cannot obtain a write it was never granted |
| **Network isolation** | Servers reachable only from the app's subnet/private endpoint, not the public internet |
| **Timeout + retry** | Per-call timeout (beneath the run deadline, [§5](workflow-design.md#sec-5)) and bounded, idempotent-safe retry with backoff |
| **Rate limits** | Per-server request limits, so one runaway investigation cannot exhaust a shared telemetry backend |
| **Schema version negotiation** | Tool input/output schemas are versioned; the client negotiates a compatible version rather than assuming today's shape |
| **Distributed trace propagation** | The `trace_id` (§10) propagates across the boundary so an MCP tool call appears in the same hierarchical trace as the node that made it |
| **Tenant / service scope** | Every call carries the investigation's scope so a server can enforce tenant/service-level access, not just tool-level |

The **client-side `READ_ONLY_TOOLS` allowlist is not enough**: it stops *this* loop from *selecting* a
write tool, but the guarantee production needs is that the identity behind each server *cannot perform*
a write it was not granted — enforced at Entra RBAC on the underlying telemetry/platform resources. The
two layers compose (allowlist + least-privilege identity); only the second survives a client bug.

### Incident-source tools sit behind an ITSM-owned boundary

> **Status:** `proposed` — `get_incident` / `get_correlated_alerts` read local synthetic data · gap: [G-53](./status.md#g-53)

`get_incident` and `get_correlated_alerts` are drawn in-process, but the system context ([§2](architecture.md#sec-2)) says they
*originate from monitoring/ITSM* — the incident source is an external actor, not local storage. In
production they belong behind an **incident-source adapter** (an ITSM-owned boundary or its own MCP
server), the same seam pattern as telemetry/platform, so the ITSM integration's ownership, auth, and
rate limits are the ITSM team's to hold. In-process is the *dev* substitution over synthetic RetailEase
data, exactly as the local retriever substitutes for AI Search — the adapter seam is what keeps that a
swap rather than a rewrite.

## 10 (ops). Cross-cutting operations

*§10 (originally "Cross-cutting concerns") is split by owner: the **guardrail pipeline** is
[`architecture.md`](./architecture.md) § 10 (Security & guardrails); **evaluation** is
[`evaluation.md`](./evaluation.md) § 10; the **operational** concerns — observability, reliability,
cost, admission control — are here.*

### Observability

OpenTelemetry spans on every node and tool; LangSmith traces in dev; structured JSON audit logs
(`trace_id`, `incident_id`, `prompt_version`, `model_version`, `tool_calls`, `retrieved_docs`,
`latency`, `tokens`, `cost`, `guardrail_decision`, `approval_status`). Drift monitoring on retrieval
quality and groundedness over time.

> **Sink schedule.** Span *emission* is built (Stage 5g, #46/#48) behind a config-selected exporter;
> only the sink is staged. `none`/`memory`/`stdout` ship now; the **LangSmith dev sink lands at Stage
> 8** ([G-61](./status.md#g-61)) with the trace-handling rules below; **App Insights** at Stage 11.
> Changing sink touches exporter config only — never an emission site.

### Reliability

Retries + exponential backoff, timeouts, circuit breakers (diagnosis iterations, total tool calls),
and a four-tier graceful-degradation ladder: full agent → retrieval-only summary → cached runbook →
escalate. **Silence is never an acceptable outcome** — every escalation carries a machine-readable
reason (budget dimension exhausted, unresolved contradictions, plan exhausted, guardrail block), and
that reason reaches API consumers via `InvestigationResponse.reason`, not just internal state.

> **A degraded rung changes the product contract, so it must change the result *type* — not just a
> flag on `IncidentReport`.** A retrieval-only summary or a cached runbook is **not a root-cause
> report**: it cites no diagnosed cause, it wasn't gated by coherence, and a consumer must not render
> it as an RCA. Returning all four rungs under one apparent `IncidentReport` makes "degraded RCA" a
> euphemism for "we could not investigate, so here is a runbook." The result is therefore a
> **discriminated union**, each variant with its own required fields and its own UI treatment
> ([G-49](./status.md#g-49)):
>
> ```python
> InvestigationResult = (
>     GroundedRcaReport          # full agent: CausalClaim + citations, coherence-passed (§5)
>     | PartialInvestigationReport  # some evidence gathered, no gated conclusion — discloses what's missing
>     | KnowledgeBriefing        # retrieval/cached-runbook only: relevant docs, explicitly NOT a diagnosis
>     | EscalationNotice         # handed to a human, machine-readable reason, no claim at all
> )
> ```
>
> Only `render_report` ([§5](workflow-design.md#sec-5)) emits `GroundedRcaReport`; each lower rung emits its own type, and the API
> surfaces the variant tag so a poller can tell a diagnosis from a briefing without inspecting prose.
> The `degraded` vs `escalated` glossary distinction (Appendix D) is exactly this union's `Partial*`
> vs `EscalationNotice` split, made typed.

> **The escalation reason must be *stamped*, not inferred.** A node that blocks the run states why, on
> state, at the moment it blocks. Inferring the cause afterwards by probing state — "was the budget
> exhausted? was the plan stuck?" — produces a confidently wrong answer whenever a cause exists that
> the probe does not test for, which is exactly what happens today for guardrail failures
> ([G-36](./status.md#g-36)). Now that the reason is API surface, a misattributed reason is a
> published falsehood, not an internal wart.

> **Provider outage mid-run is undefined, and the deterministic floor does not cover it.** The floor
> is a **composition-time** fallback: if the `ChatModel` cannot be built at startup, the process runs
> deterministically and says so in `/version`. It does nothing for a provider that fails at round 3 of
> 5. The degradation ladder above covers *telemetry sources*; the *model itself* is not in it. Options,
> to decide: fail the run to `escalate` with a distinct reason (simplest, honest); or degrade the
> remaining rounds to the deterministic planner and disclose a **mixed-implementation** run — which
> requires the report's runtime metadata to stop claiming one `implementation` per run. **This is
> open decision [§13.2](decisions.md#sec-13) (A)**; until it is taken, a mid-run outage surfaces as a generic failure
> ([G-38](./status.md#g-38)).

### Cost

Per-run cost estimate, max-LLM-calls-per-investigation, exact + semantic caching on runbook retrieval,
a `CostTracker` with budget caps and a per-run JSON report. Enforcement path is the `IterationBudget`
([§5](workflow-design.md#sec-5)).

> **`tiktoken` is not a provider-neutral cost layer.** It is the OpenAI tokenizer; it does not match
> Claude's tokenization (nor Qwen's), so a `tiktoken` estimate on the Claude tiers is wrong — and cost
> caps computed from a wrong count silently mis-enforce the budget. The count layer must be
> **provider-specific**: use the model's own token counter for a *pre-call* estimate (Anthropic
> `count_tokens` for the Claude path, the tokenizer estimate for OpenAI), and prefer the
> **provider-reported actual usage** returned *after* each call as the source of truth. Both flow into
> one **normalized usage record** in the core (§11 provider seam), so `CostTracker` and the
> `IterationBudget` account in one shape regardless of vendor ([G-45](./status.md#g-45)).

### Admission control is system-level, not just per-run

> **Status:** `proposed` — only a per-run call cap exists; no auth, roles, quotas, or global limits · gaps: [G-03](./status.md#g-03), [G-57](./status.md#g-57)

The `IterationBudget` bounds **one** investigation. It does nothing against **500 cheap investigations
submitted at once** — each is individually within budget, and together they exhaust the model's RPM/TPM,
the queue, and the approval backlog. Per-run cost control and system admission control are different
layers, and the target needs the second:

| Control | What it bounds |
|---|---|
| **Entra authentication** | Every request carries a verified principal — the same token that gives the `decide` role its reviewer identity ([G-01](./status.md#g-01)) gates `submit`/`read` too |
| **Authorization roles** | `submit` / `read` / `decide` / `admin` — distinct scopes, not one open endpoint (the decision endpoint is `decide`, [§8](workflow-design.md#sec-8)) |
| **Per-user / per-service quotas** | A caller's share of submissions over a window, so one identity cannot monopolize the system |
| **Global concurrency limit** | A cap on *in-flight* investigations, independent of who submitted them |
| **Model RPM/TPM admission** | Reject or queue at the provider's rate ceiling rather than discovering it as 429 storms mid-run |
| **Queue-depth limit** | A bound on pending dispatch ([§8](workflow-design.md#sec-8)) — shed or reject when the backlog exceeds it, don't accept unboundedly |
| **Max pending approvals** | A cap on `awaiting_approval` records, so an unattended reviewer queue cannot grow without bound |
| **Incident-level access control** | Read/decide authorized per incident, not blanket — a reviewer sees the incidents they own |
| **Audit + PII-aware retention** | Approval/audit records retained to policy; Blob payloads and traces retained with PII handling, not indefinitely |

This is the layer [G-03](./status.md#g-03) (unauthenticated, uncapped ingress) is the first missing
piece of — auth is necessary but not sufficient; the quotas and global limits sit above it.

> **LangSmith traces are a data-exfiltration surface.** Dev traces can contain **prompts, telemetry
> rows, and retrieved passages** — real incident data. LangSmith stays a **dev-local** adapter that
> never gates the Azure deploy (§11), and its traces must be **restricted to synthetic/development data
> or scrubbed before export** — a trace exported with live PII is a leak the eval convenience never
> justified. Production tracing goes to App Insights under the same PII-aware retention as Blob
> ([G-57](./status.md#g-57)). The LangSmith exporter ([G-61](./status.md#g-61)'s sink half) lands
> with these rules ([`adr-observability-tracing.md`](./adr-observability-tracing.md)).

## 11. Models & data

> **Status:** `deployed` — dev + Azure OpenAI providers, keyless · `merged` — the tier→model map as
> configuration, read by nothing · `proposed` — severity-driven tier selection, AI Search backend ·
> gaps: [G-21](./status.md#g-21)

### Models

**The architecture names tiers and the policy that selects them; it never names a model.** Model
generations churn faster than this document, and a hardcoded id here becomes a second, stale source of
truth beside the config that actually resolves it ([§12](deployment.md#sec-12): *model ids are config, not architecture*).

| Role | Selection policy | Bound in |
|---|---|---|
| Embeddings (dense) + BM25 (sparse) | A small local embedder in dev, swappable to a stronger multilingual one; the managed hybrid index in prod. A swap is a versioned **embedding profile** (model + dimensions + index schema) → index rebuild, not a flag toggle (§11) | `EMBEDDING_MODEL` (embedding profile) |
| Reranker | Cross-encoder in dev; the managed semantic reranker in prod. Layered on **after** the hybrid baseline is proven | `RERANKER_MODEL` |
| LLM — **cheap tier** | SEV3/SEV4 — the low-severity tail, chosen on cost per investigation | `PROD_MODELS[CHEAP]` (+ hosting location) |
| LLM — **standard tier** | SEV2, and the **default ceiling for SEV1**. The tier the system is evaluated at | `PROD_MODELS[STANDARD]` (+ hosting location) |
| LLM — **premium escalation tier** | SEV1 only, behind an explicit flag, **off by default**. Enabled on demonstrated cost/benefit for the SEV1 tail, never as a default | `PROD_MODELS[PREMIUM]`, gated by `OPSPILOT_ENABLE_OPUS_SEV1` (+ hosting location) |
| LLM — **judge tier** (eval) | Pinned, cross-vendor, temperature 0, **at least as strong as the system under test**; SEV1 → two-judge panel | `JUDGE_MODEL` |
| Guardrails | PII detector + injection classifier in dev; the managed content-safety service in prod | provider config |

**Deployment profile.** The tier→model binding lives in `src/opspilot/config.py` (`PROD_MODELS`,
`DEV_MODEL`, `JUDGE_MODEL`), overridable per environment, and `/version` surfaces the resolved
`provider` + `model_id` the running process actually holds. Each production tier also carries its
**provider adapter** (`azure_openai` vs `anthropic_foundry`, §11 provider seam) and its **hosting
location** (Azure-hosted vs Anthropic-through-Foundry) — both are part of the binding, because a Claude
tier cannot be served by the Azure OpenAI adapter and its data-residency posture is not implied by the
model id. Changing a generation is a configuration change and a re-baseline;
it is not an architecture change and does not touch this document. In dev, one local model stands in
for all three production tiers — tiering is exercised as *policy*, not as three separate downloads.

**Two independent decisions, deliberately decoupled.** *Production tier choice* is made on incident
quality, latency, privacy, availability, and cost. *Judge strength* is a separate eval-integrity
constraint. The system is never weakened to keep the judge convenient; if a stronger production tier is
justified, the evaluation strategy adapts rather than the model being capped.

**Which severity the tier reads is an open decision** — the revised one or the triage-time one. [§5](workflow-design.md#sec-5)
pins the tier at the first LLM call so cassette replay stays keyed to one `model_id` per run; reading
the revised severity would mean an upgraded incident no longer keeps the cheap model, at the cost of
that determinism. Nothing selects a tier today ([G-21](./status.md#g-21)), so the conflict is
unresolved rather than latent — see [§13.2](decisions.md#sec-13) (C).

### The provider seam

> **Status:** `deployed` — `azure_openai` (gpt-class) + `openai`/`replay`/`fake` · `proposed` — the
> `anthropic_foundry` adapter the Claude tiers actually require · gap: [G-45](./status.md#g-45)

Diagnosis and triage nodes talk only to a provider-agnostic `ChatModel` (`llm/base.py`); vendors
resolve via `build_chat_model(provider)`, all lazy so the lean runtime image and the CI core lane
import them without the optional `llm` dependency group:

- **`openai`** — an OpenAI-compatible client fronting a small hosted model, and (pointed at a local
  base URL) the local dev model via Ollama, the free floor. Which models: the profile above.
- **`azure_openai`** — `AzureOpenAI` (chat-completions) against an Azure-hosted OpenAI deployment.
  Keyless: with no API key configured the client authenticates with an Entra bearer token from the
  environment's managed identity (`DefaultAzureCredential`), and the provisioned account has local-auth
  disabled, so there is no key to leak. **This is what the demo deployment runs today** (a gpt-class
  model), and it is *not* a path to the Claude tiers — see below.
- **`anthropic_foundry`** — the adapter the **production Claude tiers require**, and the one not yet
  built. Claude on Microsoft Foundry is served through Anthropic's **Messages API** (`/v1/messages`,
  the `AnthropicFoundry` client / Entra-auth Anthropic SDK), *not* the Azure OpenAI chat-completions
  surface. `AzureOpenAI` cannot call it. The two are different request/response shapes, so the
  provider is a separate adapter, not a base-URL swap.
- **`replay`** — plays back a recorded **cassette** (request → response keyed by a stable content
  hash). This is what lets a non-deterministic LLM scorecard gate CI for free, and keeps the LLM eval
  reproducible.
- **`fake`** — deterministic canned responses for driving the LLM nodes in tests/demos with no
  provider at all.

> **`AzureOpenAI` is not the Claude adapter — this was a documentation error, now a tracked gap.** §11's
> model table names Claude tiers on Foundry while the seam claimed `AzureOpenAI` as the production path;
> those do not compose. The `ChatModel` contract is what makes the seam real, and it must **normalize
> across the OpenAI and Anthropic surfaces** rather than assume one — they differ in every dimension the
> nodes depend on:
>
> | Contract concern | OpenAI (chat-completions) | Anthropic Messages (Foundry Claude) |
> |---|---|---|
> | Tool-call format | `tool_calls` array on the message | `tool_use` **content blocks** |
> | Structured output | JSON mode / response-format | tool-call or output-format shape |
> | Usage metadata | `usage.prompt_tokens` / `completion_tokens` | `usage.input_tokens` / `output_tokens` (+ cache fields) |
> | Refusal | absent / content-filtered | first-class `stop_reason: "refusal"` |
> | Reasoning control | n/a | `effort` / adaptive thinking |
> | Token counting | tokenizer estimate | provider `count_tokens`, not `tiktoken` (see §Cost) |
> | Prompt caching | n/a on this path | `cache_control` breakpoints |
> | Content model | single string | typed content blocks |
>
> The seam's job is to hide these behind `ChatModel`, so the graph sees one shape and a **normalized
> usage record** regardless of vendor. A seam that only ever saw OpenAI shapes has not been exercised
> against the surface production actually uses ([G-45](./status.md#g-45)).
>
> **Hosting location is a separate, explicit choice — "available through Foundry" ≠ "runs on Azure."**
> Some Claude tiers are Azure-hosted; others are served on Anthropic infrastructure *through* Foundry.
> For a system framed as regulated Azure ops, processing location, data-residency, and contractual
> boundary differ between the two, so §11's deployment profile must state, per tier, **Azure-hosted** or
> **Anthropic-through-Foundry** — it is not derivable from the model id.

**Model output is never trusted raw.** It is parsed through strict Pydantic schemas (`PlannerResponse`
/ `SynthesisResponse` / `TriageResponse`) — wrong types or an unknown intent raise `ValidationError`
and the caller falls back closed. The graph, not the model, owns looping, budgets, and termination.

<a id="sec-12"></a>
## 12. Deployment

> **Status:** `deployed` — single-region demo tier, Azure OpenAI keyless, smoke-gated ·
> `proposed` — Cosmos activation, AI Search, Blob, Key Vault, publisher identity, ingress auth ·
> gaps: [G-02](./status.md#g-02), [G-03](./status.md#g-03)

| Concern | Service |
|---|---|
| Agent runtime | **Container Apps** — `minReplicas = 0` (demo); ≥2 + zone strategy for the HA target. `GET /health/live` and `GET /health/ready` (503 until corpus + repository + logs + retrieval all pass) wired as liveness/readiness probes in `infra/main.bicep`; the deploy gate (`scripts/smoke_deployment.py`) exercises readiness, `/version`, and a real investigation before a deploy counts as successful. **The current broad gate contradicts the settled degradation semantics** ([G-59](./status.md#g-59)); Stage 8's readiness split narrows `/health/ready` to "can accept and track work" and moves dependency health to `/health/dependencies` feeding run-level degradation |
| Trigger | Async job API — `POST /investigations` → **Cosmos transactional write (record + dispatch-outbox)** → `202 + investigation_id`, polled via `GET /investigations/{id}`, decided via `POST /investigations/{id}/decision`; `thread_id` == `investigation_id`. **Dispatch is durable in v1:** change feed → **Service Bus** → **queue-triggered worker** (KEDA queue scaler) drives the checkpointed graph — an honest `202`, not post-response background work ([§8](workflow-design.md#sec-8), [G-34](./status.md#g-34)). Event Grid *ingestion* (external systems → OpsPilot) is the v2 add; the internal dispatch queue is not. A same-origin operator console at `GET /console` is a browser client of this same trigger — no separate frontend deployment |
| Checkpointer + Store | **Cosmos DB is the technology, not the storage architecture** — it holds **several workloads with different schemas, partition keys, TTLs, throughput shapes, and access policies** (table below), not one container. `build_checkpointer()` selects `none`/`memory`/`sqlite`/`cosmos`; the `cosmos` backend uses the first-party `langchain-azure-cosmosdb` saver, **keyless** via `DefaultAzureCredential`. **TTL is per-workload, not global** — the checkpoint's bound is the longest legitimate pause (`awaiting_approval`, [§5](workflow-design.md#sec-5)), which is *not* the same as the investigations record's or verified-memory's (no TTL at all); a single global default silently collects live work. See [G-48](./status.md#g-48) |
| Retrieval | **Azure AI Search** (dense + BM25 combined with RRF, then semantic rerank over a candidate set) — a *different* retrieval system from the local pipeline, so parity is **outcome compatibility** (result schema, filtering, as-of, a shared Precision@K/MRR floor, required-target recall), **not** ranking equality (§11). Embedder changes are index rebuilds, not config flips. See [G-56](./status.md#g-56) |
| LLM | **Foundry Models.** Two distinct data planes, not one: **Azure OpenAI** (chat-completions, `AzureOpenAI` client — what the demo runs today) and **Claude on Foundry** (Anthropic **Messages API**, `anthropic_foundry` adapter — the target Claude tiers). Both keyless via managed identity; `infra/main.bicep` provisions the Azure OpenAI account (`disableLocalAuth`, custom subdomain) with *Cognitive Services OpenAI User*, and Claude-on-Foundry needs its own resource + role grant. Per-tier **hosting location** (Azure-hosted vs Anthropic-through-Foundry) is declared in the §11 profile, not inferred from the id. `OPSPILOT_IMPLEMENTATION` selects the deployed diagnosis pair; the deterministic floor is the explicit `/version`-surfaced fallback. See [G-45](./status.md#g-45) |
| Observability | OpenTelemetry → App Insights |
| Guardrails | Content Safety + **Prompt Shields** (direct + XPIA/indirect), wired as **application-level** pipeline stages (§10) — **not** automatic at the Claude-on-Foundry model deployment, which ships without built-in filtering. See [G-46](./status.md#g-46) |
| Storage / secrets / identity | Blob · Key Vault · Entra. **Three distinct identities:** the agent's managed identity (inference + reads), a **separate privileged identity** that publishes verified postmortems — the diagnosis runtime cannot write into long-term memory — and the **human reviewer's** Entra principal, which authorizes publication ([§8](workflow-design.md#sec-8)) |
| IaC / CI-CD | Bicep · GitHub Actions — ruff + mypy + `core`/`full` lanes as required checks before deploy; the LLM scorecard gated by cassette replay |

### Cosmos is several workloads, not one container

> **Status:** `proposed` — the seam exists; the container split, per-workload TTL, and idempotent
> change-feed indexer do not · gap: [G-48](./status.md#g-48)

"Checkpointer + Store = Cosmos DB" names a technology and stops short of the storage design. These are
distinct workloads that must be separated — different partition keys, TTLs, throughput, and **access
policies**:

| Workload | Owner identity | Partition key (shape) | TTL | Notes |
|---|---|---|---|---|
| `investigations` (resource records) | app managed identity | `investigation_id` | none | what the poll endpoint reads ([§8](workflow-design.md#sec-8)) |
| `workflow-checkpoints` (LangGraph state) | saver | `thread_id` | longest pause | **saver-internal** — no other component reads or writes it |
| `workflow-writes` / outbox | app | `investigation_id` | short | the decision-before-resume commit point ([§8](workflow-design.md#sec-8)) |
| `approval-decisions` | app | `investigation_id` | none (audit) | reviewer identity + hashes |
| `evidence-manifests` | app | `investigation_id` | none | ref → `result_hash` ([§8](workflow-design.md#sec-8)) |
| `verified-memory` | **privileged publisher identity** | `incident_id` | none | the anti-poisoning boundary ([§5](workflow-design.md#sec-5)) |
| `change-feed leases` | indexer | lease-owner | managed | powers the memory→AI Search sync |

Two properties fall out and are load-bearing:

1. **Least-privilege across containers.** The privileged publisher must **not** be able to write the
   saver's checkpoint container, and the diagnosis identity must **not** have write on `verified-memory`
   — the same separation [§5](workflow-design.md#sec-5) and [§12](deployment.md#sec-12) already draw between identities, now enforced at the container ACL,
   not just at the code path.
2. **Cross-container writes are not atomic.** Cosmos transactions are scoped to **one logical partition
   in one container**, so the repository record and the checkpoint (separate containers) cannot be
   updated in one transaction. This is *why* the decision protocol is ordered record-then-resume with an
   idempotent replay ([§8](workflow-design.md#sec-8)) rather than assuming a two-store atomic commit — the durability design already
   depends on this Cosmos limit, and stating it here keeps the two sections honest.

**The change-feed indexer needs at-least-once handling and idempotent AI Search writes.** Cosmos change
feed delivers **at least once**, with ordering guaranteed only **within a partition-key value** — so
the memory→AI Search sync must upsert by a stable document key (idempotent), tolerate re-delivery, and
not assume global ordering. A naive "append on each change" indexer double-indexes on redelivery.

**Demo-tier is a stated position, not an oversight.** Single-region, scale-to-zero, for cost. A
credible HA claim additionally requires ≥2 replicas, queue-based scaling, a zone strategy, DB
backup/recovery, deployment revisions and traffic-shifting, and stated RTO/RPO. **The checkpointer
reduces restart damage; it does not by itself provide any of these.**

The provider-agnostic core means production is mostly adapter swaps (retrieval, checkpointer) — **with
one exception the seam has to actually pay for: the LLM.** The Claude tiers are not an
`AzureOpenAI` base-URL swap; they are a separate Messages-API adapter the `ChatModel` contract must
normalize (§11, [G-45](./status.md#g-45)). "Mostly adapter swaps" holds only once that adapter exists.
The durable per-incident checkpointer is what makes this read as a distributed, event-driven system
that happens to be agentic.

---
