# OpsPilot — Architecture Decisions

**Part of the OpsPilot architecture set.** The decision register — settled (§13.1) and open (§13.2), plus the fine-tuning deferral. Each row is a compressed ADR: the choice and why, including what it costs.

> **Document map & `§N` resolver:** the map in [`architecture.md`](./architecture.md).

---

## ADRs — the decisions with their own record

The register below is the compressed overview; the categories that **code-guidelines §19 mandates an
ADR for** have a standalone document (Context / Decision / Consequences, and an operational runbook
where one exists). Each ADR is the *why* and *what-it-costs*; it points back to the design section for
the *how*, and does not restate it.

| Category (§19) | ADR | Closes |
|---|---|---|
| Security-failure behaviour | [`adr-reviewer-identity.md`](./adr-reviewer-identity.md) | [G-01](./status.md#g-01) |
| Persistence backend | [`adr-checkpointer-cosmos.md`](./adr-checkpointer-cosmos.md) | [G-02](./status.md#g-02), [G-48](./status.md#g-48) |
| Async dispatch | [`adr-async-dispatch.md`](./adr-async-dispatch.md) | [G-34](./status.md#g-34) |
| Model provider / routing | [`adr-model-provider.md`](./adr-model-provider.md) | [G-45](./status.md#g-45) |
| Retrieval backend / index schema | [`adr-retrieval-backend.md`](./adr-retrieval-backend.md) | [G-56](./status.md#g-56), [G-52](./status.md#g-52) |
| MCP trust boundaries | [`adr-mcp-boundary.md`](./adr-mcp-boundary.md) | [G-53](./status.md#g-53) |
| Multi-agent promotion | [`adr-subagent-promotion.md`](./adr-subagent-promotion.md) | [G-25](./status.md#g-25) |
| Memory-admission policy | [`adr-memory-admission.md`](./adr-memory-admission.md) | [G-27](./status.md#g-27), [G-33](./status.md#g-33) |
| Observability / tracing emission seam | [`adr-observability-tracing.md`](./adr-observability-tracing.md) | [G-61](./status.md#g-61), [G-08](./status.md#g-08) |

The remaining register rows are design choices §19 does not mandate an ADR for; a standalone file for
each would only restate its design section. They stay compressed here.

<a id="sec-13"></a>
## 13. Architecture decisions

Two tables, and the difference between them is load-bearing. **§13.1 is settled** — decided, not
re-opened by ordinary work, safe to build against. **§13.2 is `proposed`** — genuinely open, with a
stated default where one is needed to keep building. A decision in §13.2 must not be cited as
architecture, and code that depends on one must say which way it assumed. Rows marked **📄 ADR** have a
standalone record (indexed above).

### 13.1 Settled

Each is a compressed ADR: the choice and *why*, including what it costs.

| Decision | Choice | Rationale |
|---|---|---|
| Framework | **LangGraph** (Python) | First-class graph orchestration with durable state; provider-agnostic core; deploys to Azure unchanged. |
| Orchestration topology | **Subagents-as-tools when promoted; promotion is conditional** | The *form* is settled (subgraph-as-tool, not handoff); *whether* to promote is threshold-gated, default not promoted. [§7](workflow-design.md#sec-7) · [G-25](./status.md#g-25) · **📄** [`adr-subagent-promotion`](./adr-subagent-promotion.md) |
| Retrieval model | **Hybrid: dense + sparse + reranker** | Local and AI Search hybrid are different engines; parity is outcome compatibility, not ranking equality; embedder swaps are index rebuilds. [G-56](./status.md#g-56) · **📄** [`adr-retrieval-backend`](./adr-retrieval-backend.md) |
| **Knowledge delivery** | **Retrieval returns passages, not pointers** | Retrieval that contributes only citable refs is a *ranker*, not RAG — the model cannot reason over a `doc_id`. The seam carries the matched chunk, and an eval axis joins retrieval to the conclusion so the property is falsifiable. See [§6](data-and-evidence.md#sec-6), [G-04](./status.md#g-04), [G-06](./status.md#g-06). |
| External-system tools | **MCP servers** *(promotion, not day-one)* | Standardized out-of-process access to telemetry/platform systems. All tools stay plain in-process functions behind `ToolService`; MCP fronts that same boundary — a transport swap, not a rewrite, proven by the parity suite before the split. |
| Inter-agent protocol | **A2A at the boundary only** *(stretch)* | Published as an A2A service; *not* used between co-located internal subagents, which would gain only latency and failure surface. |
| v1 scope | **Read-only investigation** | Investigate → cited report + postmortem memory. External systems are read-only; OpsPilot writes only its own investigation records and verified learning artifacts. Remediation is v2. |
| Identifiers | **Separated** (`incident_id` ≠ `thread_id`) | `incident_id` (business), `investigation_id` (one attempt, UUID), `thread_id` (derived), `workflow_version`, `idempotency_key`. A duplicate/reopened/rerun incident must not overwrite or resume the wrong graph state — and a paused thread must resume by the id the client polled ([§8](workflow-design.md#sec-8)). |
| State store | **Cosmos DB — several containers, not one** | Per-workload partition key / TTL / ACL; cross-container writes non-atomic; change-feed idempotent. [§12](deployment.md#sec-12) · [G-48](./status.md#g-48) · **📄** [`adr-checkpointer-cosmos`](./adr-checkpointer-cosmos.md) |
| **LLM provider adapter** | **`anthropic_foundry` (Messages API) ≠ `azure_openai`** | `AzureOpenAI` cannot front Claude-on-Foundry; `ChatModel` normalizes both surfaces; hosting location declared per tier. [G-45](./status.md#g-45) · **📄** [`adr-model-provider`](./adr-model-provider.md) |
| **Degradation result type** | **Discriminated `InvestigationResult`, not a flagged `IncidentReport`** | A retrieval-only summary or cached runbook is not an RCA; shipping every ladder rung under one report type makes "degraded RCA" mean "here is a runbook." `GroundedRcaReport` \| `PartialInvestigationReport` \| `KnowledgeBriefing` \| `EscalationNotice`, each with its own fields and UI, variant tag on the API. See §10, [G-49](./status.md#g-49). |
| **Guardrail placement** | **Application-level pipeline, not ambient at the model host** | Content Safety / Prompt Shields is not automatic on the Claude-on-Foundry deployment; the ordered pipeline (PII → prompt-shield/XPIA scan → delimit → call → output safety → schema/citation/coherence) is OpsPilot code. Classifier-unavailable = "restricted deterministic mode" (structured evidence only, free-text suppressed, never publish an unscanned RCA). See §10, [§12](deployment.md#sec-12), [G-46](./status.md#g-46). |
| **Hard deadline enforcement** | **Inside the batch, not just between rounds** | Round-boundary cancellation cannot bound a batch of up to 6 concurrent calls; the wall-clock deadline is a quality attribute ([§2](architecture.md#sec-2)). Per-call deadlines derived from the run deadline, cancellation propagated into each tool/MCP call, outstanding calls cancelled on expiry, partial `timeout` envelopes returned. See [§3](architecture.md#sec-3), [§5](workflow-design.md#sec-5), [G-47](./status.md#g-47). |
| **Durable dispatch** | **Cosmos outbox → Service Bus → queue-triggered worker, in v1** | Post-response execution behind an HTTP scaler is not an honest `202`; the queue scaler composes with scale-to-zero. Resolves §13.2 (D). [§8](workflow-design.md#sec-8) · [G-34](./status.md#g-34) · **📄** [`adr-async-dispatch`](./adr-async-dispatch.md) |
| **Ownership fencing** | **Monotonic lease epoch, checked on every write** | A lease says "worker gone"; the epoch says "still the owner" — the stale owner fails closed. [§8](workflow-design.md#sec-8) · [G-34](./status.md#g-34) · **📄** [`adr-async-dispatch`](./adr-async-dispatch.md) |
| **Temporal isolation** | **`as_of` / cutoff / topology_version / snapshot are mandatory retrieval args** | An investigation sees only what existed when it began; retrieval bounds are required arguments, not optional filters, or eval retrieves future postmortems and prod uses corrected knowledge. `corpus_snapshot_id` pins the index generation for reproducibility. See [§4](data-and-evidence.md#sec-4), [§6](data-and-evidence.md#sec-6), §11, [G-52](./status.md#g-52). |
| **MCP boundary contract** | **A security/operational contract, not just a transport** | Least-privilege per-server identity is the real read-only enforcement (not the client allowlist); incident source behind an ITSM adapter. [§6](data-and-evidence.md#sec-6) · [G-53](./status.md#g-53) · **📄** [`adr-mcp-boundary`](./adr-mcp-boundary.md) |
| **Cassette identity** | **Full behavior-affecting manifest + a drift canary** | Keying on `(model_id, messages, temperature)` passes CI green when the prompt/schema/effort/provider changed behavior but not the key. The key hashes every behavior-affecting input; a scheduled live-canary watches provider drift that deterministic replay is blind to. See §10, [G-54](./status.md#g-54). |
| **Retrieval parity** | **Outcome compatibility, not ranking equality** | The local pipeline and AI Search hybrid are different engines; the contract pins result schema, filtering, as-of, a shared Precision@K/MRR floor, and required-target recall — not near-identical order. Embedder swaps are versioned embedding profiles → index rebuilds, not config flips. See §11, [G-56](./status.md#g-56). |
| **System admission control** | **A layer above the per-run budget** | The `IterationBudget` bounds one run; 500 cheap runs at once need auth + `submit`/`read`/`decide`/`admin` roles + per-user/service quotas + global concurrency + model RPM/TPM admission + queue-depth + max-pending-approvals + PII-aware retention. LangSmith traces stay dev-local/scrubbed; the exporter ([G-61](./status.md#g-61)'s sink half) lands with those rules ([`adr-observability-tracing.md`](./adr-observability-tracing.md)). See §10, [G-57](./status.md#g-57). |
| **Synthesis authority** | **Exactly one node concludes** | `diagnose` gathers and holds candidates; `synthesize_claims` produces the one conclusion; `coherence_check` validates it; `render_report` formats it. Two model calls that can each name a root cause will eventually name different ones, and nothing in the run would detect it — the stop decision and the published claim would rest on different reasoning. See [§5](workflow-design.md#sec-5), [G-40](./status.md#g-40). |
| Diagnosis stop rule | **Two deterministic gates, split at the conclusion** | *Gathering sufficiency* (evidence classes, independent observations, critical questions, plan advancement, funded reserve) runs before synthesis; *conclusion validation* (ref resolution, role admissibility, causal order, entity support) runs after. Grading a conclusion's citations before it exists is circular — the earlier single gate did exactly that. Never model confidence, at either gate. See [G-07](./status.md#g-07), [G-41](./status.md#g-41). |
| **Evidence model** | **Discriminated union of typed facts** | Metric windows, deployment intervals, and versioned dependency edges are the *inputs* to every deterministic check; a generic envelope with one `observed_at` and an `excerpt` forces prose-parsing and fails silently. Prose is for the model, typed fields are for the gate. See [§4](data-and-evidence.md#sec-4), [G-42](./status.md#g-42). |
| **Contradiction acknowledgment** | **Admitted by policy or a human, never by the model** | `acknowledged` is the state that stops a contradiction blocking, so model-controlled acknowledgment is a one-sentence bypass of the deterministic gate. Only `value_direction` is policy-admissible, and only with both sides cited, below SEV1, with code-capped confidence and a degraded `disposition`; everything else needs a named human accepting *that* contradiction. See [§5](workflow-design.md#sec-5), [G-44](./status.md#g-44). |
| **Citation roles** | **Model proposes, code admits** | The conclusion checks key off `role`, so a model-controlled role makes a "deterministic" gate gameable by relabeling. Each role is admissible only for evidence types that can support it, and derived by code where the fact determines it. See [§5](workflow-design.md#sec-5), [G-43](./status.md#g-43). |
| **Budget partitioning** | **Gathering allocation + three non-fungible reserves** | Gathering expands to fill any budget it is given; a single pool means a run runs out of money exactly when it needs to conclude, validate, and safety-check. Synthesis / coherence / safety are reserved up front. See [§5](workflow-design.md#sec-5), [G-08](./status.md#g-08). |
| **Grounding provenance** | **Attested by a tool gateway, not by a field** | The trusted set is derived from an **append-only ledger only the `ToolGateway` may write**; nodes hold opaque result handles, and the evidence reducer admits an item only if its handle resolves to a ledger `result_hash`. A `tool_call_id` *field* proves nothing about who set it — Pydantic validates shape, not provenance — so the control is separating the writer, not typing the value. See [§4](data-and-evidence.md#sec-4), [G-05](./status.md#g-05). |
| **Approval binds evidence too** | **`report_hash` *and* `evidence_manifest_hash`** | The report hash freezes the conclusion's bytes; the manifest hash freezes the map from each cited ref to the ledger `result_hash` behind it. Without the second, exact approved bytes can cite evidence that later changed or vanished. `finalize_report` re-checks both. See [§8](workflow-design.md#sec-8). |
| **Tool status set** | **Seven states + completeness metadata** | `ok \| error` cannot express the degradation the reliability and sufficiency stories depend on: `empty` ≠ `unavailable`, `partial`/`timeout` carry a prefix not a set, `blocked` is a policy refusal. Metadata (`rows_invalid`, `has_more`, `query_window`, `source_snapshot`, `retryable`, …) makes completeness explicit. Resolves former open decision §13.2 (F). See [§6](data-and-evidence.md#sec-6), [G-17](./status.md#g-17). |
| **Severity** | **Re-evaluated mid-run, monotonic upward — for the sufficiency bar** | Blast radius is *discovered*, not known at triage, and a frozen severity caps rigor exactly where mistakes are most expensive. The trigger is evidential (anomaly on a reached critical service), never topological. See [§5](workflow-design.md#sec-5), [G-12](./status.md#g-12). *(Whether the **model tier** follows the revision is open — §13.2.)* |
| **Human approval** | **Bound to a verified identity and exact bytes** | An authenticated Entra principal bound to `report_hash`, not a self-declared string. [§8](workflow-design.md#sec-8) · [G-01](./status.md#g-01) · **📄** [`adr-reviewer-identity`](./adr-reviewer-identity.md) |
| Memory writeback | **Two-phase, verified — and out-of-graph** | Predicted RCA never enters the corpus; admission is a closure-driven component under the publisher identity; gate type open (§13.2 E). [§5](workflow-design.md#sec-5) · [G-27](./status.md#g-27) · **📄** [`adr-memory-admission`](./adr-memory-admission.md) |
| Known-issue matching | **Candidate + verification, never score alone** | Triage surfaces a *candidate*; a downstream node checks current signals against the stored issue's `required_signals` / `disqualifying_signals` / `affected_versions` before its resolution is trusted. See [G-09](./status.md#g-09). |
| API lifecycle | **Async job semantics, pause as a first-class state** | `202 + poll`, plus `awaiting_approval` as a non-terminal status and a decision endpoint that re-enters the graph. A HITL interrupt makes synchronous request-response wrong; a run-to-terminal worker makes an indefinite pause impossible. Both halves are one design ([§8](workflow-design.md#sec-8)). *(The dispatch mechanism behind the 202 is now settled — see **Durable dispatch** above.)* |
| Batching | **Per-round, not per-action** *(accepted trade)* | Latency win, paid for by re-deriving checkpoint/cost/cancellation guarantees at round granularity rather than losing them silently ([§3](architecture.md#sec-3), [G-22](./status.md#g-22)). |
| Fine-tuning | **Deferred (documented)** | Base model + RAG suffice; see Appendix C. |
| Availability | **Demo-tier now; HA is a documented target** | Single-region, scale-to-zero for cost — explicitly a demo deployment. The always-on flip is parked until a real warm workload justifies it. |
| Regression baseline | **Versioned scorecard, deliberate ratchet** | Baselines move only via an explicit reviewed re-baseline commit — never silently — and are expected to move *up* as capabilities land. |

### 13.2 Open — `proposed`, not settled

Each of these was discovered by writing the section above it and left unresolved. The **working
default** is what the code assumes today so that building can continue; it is not the decision.
`docs/code-guidelines.md` marks the rules contingent on these ⚠ **PENDING** and follows this table —
they are not to be resolved independently in code.

| # | Open question | Options | Working default | What settles it |
|---|---|---|---|---|
| **A** | **Provider outage mid-run** (§10, [G-38](./status.md#g-38)) — the degradation ladder covers telemetry sources; the model itself is not in it, and the deterministic floor is a *composition-time* fallback that does nothing at round 3 of 5. | (a) fail the run to `escalate` with a distinct reason; (b) degrade remaining rounds to the deterministic planner and disclose a **mixed-implementation** run. | (a) — but unstamped, so it currently surfaces as a generic failure. | (b) requires the report's runtime metadata to stop claiming one `implementation` per run, and the scorecard to accept a mixed row. Decide when either is cheap, or when a real outage forces it. |
| **B** | **Subagent promotion timing** ([§7](workflow-design.md#sec-7), [G-25](./status.md#g-25)) — the topology is settled; nothing forces the promotion to actually deliver knowledge, so it could land, measure "no regression", and change nothing. | (a) promote after the retrieval seam widens; (b) promote only after a metric can fail. | (b) — blocked on `knowledge_grounding` ([G-06](./status.md#g-06)). | The `knowledge_grounding` axis existing **and** a scenario that can fail it ([G-35](./status.md#g-35)). Until then promotion is unfalsifiable and stays parked. |
| **C** | **Does a severity upgrade re-tier the model?** ([§5](workflow-design.md#sec-5), §11, [G-21](./status.md#g-21)) — [§5](workflow-design.md#sec-5) pins the tier for replay determinism; the tiering rationale wants the revised severity. Both cannot hold. | (a) tier fixes at the first LLM call, bar-only revision; (b) tier follows the revision mid-run. | (a). Nothing selects a tier at all today, so neither is implemented. | (b) needs cassette replay keyed per-round rather than per-run (`request_key(model_id, …)`), and scorecard rows that can describe more than one model. Revisit if the cheap tier is shown to miss upgraded SEV1 root causes. |
| **E** | **What is the memory-admission gate?** ([§5](workflow-design.md#sec-5), [G-33](./status.md#g-33)) — "policy/human gate" names two different controls with different failure modes: a policy gate admits silently-wrong reconciliations, a human gate does not scale and stalls the corpus. | (a) policy only; (b) human only; (c) policy admits exact predicted-vs-confirmed matches, human reviews divergences. | (c), unimplemented — no Store exists ([G-27](./status.md#g-27)). | Requires the reconciliation output to be structured enough to classify "exact match" mechanically — which depends on the typed hypothesis ([G-29](./status.md#g-29)). Decide with the admission component, not before. |

**Resolved out of this table:**

- **~~D — Async dispatch mechanism~~ → settled** (now §13.1, *Durable dispatch* + *Ownership fencing*).
  The working default was resume-on-poll + a lease; the reliability review showed both offered recovery
  mechanisms are unsound under scale-to-zero (startup-sweep needs a running replica; resume-on-poll
  turns reads into spend, races pollers, and strands abandoned runs) and that a bare lease has no
  fencing. The resolution takes option (c) — the Cosmos transactional outbox → change feed → Service
  Bus → queue-triggered worker — **into v1**, because the queue scaler is what composes *with*
  scale-to-zero. "A service the demo does not otherwise need" was the wrong frame: an honest durable
  `202` needs it.
- **~~F — Tool-envelope status set~~ → settled** (now §13.1, *Tool status set*). The third-review
  argument supplied the consumers the decision was waiting on: the degradation ladder needs
  `unavailable` distinct from `empty`, and the sufficiency gate must not treat a `timeout` prefix as a
  complete set. That tipped it past "not worth the parity-suite churn" — the churn is the point. The
  envelope now carries seven states plus completeness metadata.

---

## Appendix C — Fine-tuning: considered and deferred

Per the golden rule (Prompt → RAG → Fine-Tuning), fine-tuning is justified only with measured evidence
that prompting + RAG fall short. Here the base model handles triage and grounding comes from
retrieval, not weights. A QLoRA severity/category classifier on a small local base model was scoped but
**deferred** — it adds cost, an irreversible artifact, and regression risk for no demonstrated gain.
Revisit only if post-deployment eval shows the supervisor mis-routing on a measurable slice.
Documenting the decision *not to* is itself the judgment that matters.

---
