# OpsPilot — Code Guidelines (Authoritative)

**Status:** Authoritative. Supersedes the two prior drafts (the repo-grounded working doc and the review-driven standards doc); this is their reconciliation.
**Applies to:** all application, graph, tool, MCP, retrieval, evaluation, persistence, infrastructure, and deployment code.
**Baseline:** reconciled against repository `main` through commit `f13ff04a8143cdc77bb6880f3ea489bacaaab508`.
**Precedence:** when a guideline and expedience conflict, the guideline wins unless the PR description records an explicit, justified exception. These guidelines are part of the definition of done (§21).

**Normative language.** **MUST** = required for merge. **SHOULD** = expected unless the PR documents a justified exception. **MAY** = optional. Keywords are used only where a rule is a genuine merge gate; unmarked prose is still binding convention.

**No rule below is currently blocked on an unresolved architecture decision.** The three that once were are all **resolved**: checkpointer backend → Cosmos DB ([§13](decisions.md#sec-13) below), tool-envelope status set → seven-state set ([§5](workflow-design.md#sec-5) below), and async dispatch → durable Cosmos-outbox → Service Bus queue in v1 ([§13](decisions.md#sec-13) below). The guideline follows the architecture ADR — do not re-open a settled decision in code.

> Remaining open decisions (none of which gate a rule here) are enumerated in **[§13.2](decisions.md#sec-13)** (A provider-outage, B subagent-promotion timing, C severity re-tiering, E memory-admission gate). [§13.1](decisions.md#sec-13) is the settled set; anything cited as architecture must come from there.

---

## 1. Toolchain

- `uv` is the only entry point. `uv sync` to install, `uv run pytest -q` to test, `uv run ruff check .` to lint, `uv run mypy` to type-check. Never bare `pip` / `python`.
- Python is pinned (`requires-python`); `uv.lock` is committed and authoritative.
- Ruff (`E,F,I,UP,B`, line length 100) and mypy MUST run clean. New lint suppressions require an inline reason — the existing `# noqa: BLE001 — no exception may cross the tool boundary` is the model.
- Dependency groups stay honest and separated by purpose (runtime / dev / data-generation / local-ML / eval). The heavy dense/rerank ML stack (`sentence-transformers`, embedding + cross-encoder models) lives in the `eval` group and **MUST NOT become a runtime dependency** — production retrieval is the lexical BM25 backend (or Azure AI Search) behind the `SearchRetriever` seam. `rank-bm25` is a lightweight pure-Python lexical index and **is** a runtime dependency (it backs `BM25Retriever`, the deterministic image default); it is not part of the "ML stack" this rule fences off.
- A capability required in the deployed runtime MUST NOT live only in an optional test/eval group.
- Import-time network calls or model downloads are forbidden. Heavy dependencies (ML stack, MCP) stay lazy — inside functions or `TYPE_CHECKING` — so the core imports fast and degrades cleanly when extras are absent. Missing extras return an error envelope; they never raise at import time.
- New dependencies MUST be justified in the PR: purpose, license, security impact, image-size impact, and removal criteria if experimental. Base/tool images SHOULD be version-pinned; release images SHOULD be digest-pinned.

## 2. CI is the gate, not the deploy

- Every PR and every push to `main` runs lint + type-check + the full test suite **before** anything deploys. `deploy.yml` depends on the CI job. A green deploy of red code is a process failure.
- ML-gated tests (`pytest.importorskip`) MUST actually run in at least one CI lane (cache the `bge-small` model on the runner). A permanently-skipped gate is not a gate; a skip must be visible and MUST NOT satisfy a release gate.
- Use explicit CI lanes: **core** (minimal runtime install), **full** (retrieval/eval install), and **Azure integration** (when credentials/environment are available). Both the minimal-runtime install and the full install MUST be exercised.
- The scenario regression gate (`test_scenario_gate.py`) runs in CI. A PR that regresses the versioned baseline is blocked.
- Deployment MUST fail when the real investigation smoke test fails. A successful health endpoint is never a release gate on its own.

## 3. Eval-driven development and baselines

The governing principle: **quality is proven by the answer-key scenario scorecard, not by unit-test count.** The test taxonomy in §18 is a menu of what kinds of tests exist — it is not a coverage mandate, and chasing categories instead of scenarios is the anti-pattern this section exists to prevent.

- Traditional tests are limited to the five silent-failure categories: state-contract validation, loop termination, interrupt-resume + Store round-trip, guardrail block-fixtures + fault injection, and post-deploy smoke checks.
- Baselines (`eval/baselines/*.json`) are committed and versioned. Re-baselining is a deliberate, reviewed commit with old/new diff, per-scenario diff, and a one-line rationale — never a side effect of a normal test run. Numbers are expected to move **up**; a downward re-baseline requires explicit justification.
- **New capability ⇒ new metric first.** Before a capability lands, the scorecard grows the metric that would catch it being wrong. (The inc-004 lesson: a grounded-but-wrong RCA was invisible until `rca_correctness` existed. Grounding and correctness are separate axes and are scored separately.)
- Deterministic implementations are **kept, not deleted**, when an LLM replaces them. They are the fallback tier and the floor every model-driven implementation must beat (`evaluate(implementation=...)`).
- Aggregate success is insufficient. Critical scenarios MUST carry explicit per-scenario minimums for route, critical evidence, citation resolution, RCA correctness, and safety.
- Judges: pinned model, temperature 0, at least as strong as the system under test; SEV1 uses a two-judge panel. Judge scores never gate alone where a deterministic metric can exist. Judges are calibrated against human labels.
- Every production or evaluation defect gets a regression test (or a new scored scenario) before the fix merges.

## 4. Contracts first, always

- Every boundary speaks Pydantic: API requests/responses, durable state, tool requests/results, model structured outputs, reports and claims, approval records, errors and degradation, queue messages, persisted documents. Free `dict`s MAY exist only *inside* a function; never as a durable or cross-node contract.
- Contracts are **frozen before intelligence is placed inside them.** An LLM plugs into existing types and transitions (`diagnosis/contracts.py` is the model); it never gets a bespoke ad-hoc interface.
- The **evidence-ref grammar is frozen**: `logs:<service>:<event_id>`, `metrics:<service>:<metric>@<ts>`, `deploys:<service>:<deploy_id>`, `deps:<from>-><to>`, `runbook:<id>`, `architecture:<id>`, `postmortem:<incident_id>`. Any change is a cross-phase breaking change: update the answer key, the tools, and the closure gate in one commit.
- Persisted models carry a `schema_version`. Breaking changes require a migration or compatibility reader, old-and-new fixtures, and workflow-version routing when an in-flight graph may resume old code.
- **Identifiers are distinct types or clearly named fields and never conflated:** `incident_id` (business), `investigation_id` (one attempt, UUID), `thread_id` (derived from `investigation_id`), `workflow_version`, `idempotency_key`. Never reuse incident id as thread id, investigation id as idempotency key, a human-readable incident number as a DB primary key, or a report hash as a report id.
- Time: all persisted timestamps are tz-aware UTC via `to_utc`; parse with Pydantic datetime coercion, not hand-rolled `strptime` (one strict-format parser already caused recency-weighting brittleness — don't add more). Source time and retrieval time are separate fields. "A preceded B" MUST be derived from timestamps, never wording, and MUST be tested.
- Hashes MUST specify canonical serializer + version, algorithm, the exact bytes hashed, and content type. Never hash an incidental Python dict representation.

## 5. The tool boundary

- Every tool goes through `run_tool`: validate kwargs into the request model → run pure logic returning `(records, evidence_refs)` → cap → stamp metadata. **No exception, stack trace, or filesystem path ever crosses the boundary**; failures are sanitized error envelopes.
- Tools are single-purpose, read-only (v1), and deterministic: results sorted by stable keys with explicit tie-breakers, malformed corpus rows handled per the status rule below (not silently dropped under a clean success), caps (`MAX_RESULTS`, `MAX_WINDOW_DAYS`) enforced tool-locally. Every request model bounds text length, result count, time window, entity count, and enum values.
- All dispatch goes through `ToolService.call()` against the allowlist registry. An unknown name is a sanitized error, never an exception. Mutating tools are structurally absent from `READ_ONLY_TOOLS` — enforcement is code, not convention.
- Signal-vs-noise separation is the **agent's** job, not the tool's: tools return the honest window, noise floor included.
- Tool docstrings are the agent's selection signal. Write them for the model: purpose, when to use, required inputs, limits, **what the tool does not prove**, and result semantics. "OpsPilot read-only tool" is not enough. Keep them accurate when behavior changes.
- Broad catches are permitted at the boundary but MUST NOT be silent: `except Exception: return generic_error()` is insufficient. The catch MUST log with correlation, classify retryability, return a stable external code, and increment a failure metric.

✅ **RESOLVED — envelope status set (was PENDING).** [§13.1](decisions.md#sec-13) (*Tool status set*, resolving former open decision [§13.2](decisions.md#sec-13) F) settles it in favor of the richer set: **seven states plus completeness metadata**, defined once in [`data-and-evidence.md` §6](./data-and-evidence.md#sec-6) (five states now; `unavailable`/`timeout` at the async/MCP phase). The binding rules: a malformed subset produces `partial` + `rows_invalid`, never a silent `ok`; source unavailability is **not** a valid empty result; and changing the status set is a frozen-contract change ([§4](data-and-evidence.md#sec-4)) — one commit updating the tool contract, parity tests, and routers together.

- Evidence descriptors correspond one-to-one to returned records. Truncating records truncates evidence consistently; a continuation token is returned when more trusted data exists; the agent never receives a reference to a record omitted from the result. Evidence IDs are stable within an investigation.
- Retries belong in an adapter/reliability policy, not scattered through tool logic. Network-backed tools (when they exist) MUST be async and accept a deadline, cancellation, and trace context.

## 6. Seams, dependency injection, and domain purity

- Every external dependency sits behind a declared seam: corpus → `Repository`; vectors → `VectorIndex` protocol; embeddings → `Embedder`; tools → `ToolService`; transport → MCP fronting the same `ToolService`; checkpointer → the persistence seam ([§13](decisions.md#sec-13)). Swapping a backend (Azure Monitor, AI Search, the checkpointer) touches the adapter, never the consumer.
- **Domain purity:** provider-neutral domain models and policies MUST NOT import FastAPI, Azure SDKs, LangChain provider classes, MCP SDKs, or database clients. Provider and Azure code implements ports defined closer to the domain. Dependency direction is `api / adapters / mcp / persistence → application / graph → domain`. (Take the direction as binding; migrate the folder layout incrementally — new code follows the target direction.)
- No module-level mutable singletons in graph code. Nodes receive `ToolService` (and later the model client) via LangGraph `configurable` / factory injection so tests inject edge-case repositories and the checkpointer era doesn't fight globals. The `_tools` global is grandfathered until Step 7 removes it.
- The composition root constructs concrete services and loads config once. Constructors construct: prefer optional parameters with defaults over `cls.__new__` back doors (`Repository.from_records` is scheduled for normalization). A transport adapter MUST NOT contain a second implementation.

## 7. Graph state

- State is typed and versioned (`schema_version`); nodes return partial updates only for fields they own and never silently mutate input state.
- **No blind-append reducers.** Collections that survive loop re-entry or parallel branches are keyed dicts with dedup-by-content-hash reducers, preserving the earliest `retrieved_at` and never collapsing contradictory observations. (`list + operator.add` produced observed 5× evidence duplication under loop re-entry — this is a banned pattern.) Reducers are associative and deterministic, reject conflicting reuse of an id, and are tested across merge orders.
- One source of truth per fact. Never mirror a value in both a scalar and a nested structure; derive, don't duplicate.
- State carries excerpts and pointers, never raw payloads: full bodies and full reports go to Blob, the checkpoint carries references and bounded excerpts.
- Loops MUST advance: any re-entrant node tracks what it has already done (answered questions, exhausted plans), and a router branch exists for "cannot advance" → reasoned escalation. Burning budget on repeated identical work is a bug, not a retry strategy.

## 8. Routing and stopping

- **Code decides when the agent may stop.** Stop rules are deterministic sufficiency computations over typed state; model confidence is one recorded input and never the trigger.
- Routers are deterministic functions over typed state and **fail closed** by default. Missing state defaults to the safe branch:

  ```python
  # bad — fails open (missing safety state routes to review)
  return "review" if safety.get("passed", True) else "escalate"
  # preferred — fails closed
  return "review" if safety is not None and safety.passed else "escalate"
  ```

- Every escalation carries a machine-readable reason (exhausted budget dimension, unresolved contradictions, plan exhausted, guardrail block). Silent termination is forbidden.
- Human `edit` decisions **re-enter validation** — nothing edited reaches finalize without passing `safety_validate` again and re-binding the approval hash.
- A diagnosis graph turn executes at most one evidence action.

## 9. Interrupt and HITL rules

- The HITL gate is a checkpoint-backed `interrupt()`: LangGraph persists state and waits; a human decides out-of-band; the graph resumes from the exact checkpoint.
- Code before `interrupt()` may run again on resume, so all side effects before an interrupt MUST be idempotent. A node performs at most one interrupt per invocation; interrupt payloads are minimal and JSON-serializable.
- Resume MUST use the same unique `thread_id` (derived from `investigation_id`, never reused across reopen/rerun). Reviewer decisions are validated outside model logic. Stale report versions/hashes MUST be rejected (optimistic concurrency / ETag).
- Approval binds to an immutable `report_hash`; the published bytes are byte-for-byte the approved bytes (`approved_report_hash`).

## 10. Guardrails as code

- Guardrail policies live in `guardrails/` as pure, unit-testable functions wired into graph nodes — never as prompt-text-only promises. Each policy ships fixtures for both the block and the pass case, including a deliberately-violating input.
- All retrieved content and tool output is **untrusted data**: delimited, never executed as instructions. Any code path that feeds retrieval output to a model goes through the input-guardrail wrapper. Screen both direct user/alert text and retrieved documents/excerpts; prompt-attack detection is defense in depth, not the only boundary.
- Fail-open/closed is risk-specific, chosen per component, and asserted in tests — the
  per-component policy table is [`architecture.md` §10](./architecture.md#sec-10); never blanket
  fail-open.

## 11. MCP

- `ToolService` is the single implementation; MCP is transport. A server never adds logic, validation, or error shaping beyond serializing the existing envelope (`validate_input=False` on the server so validation is byte-identical to in-process).
- Every exposed tool has a parity test (in-memory client/server vs direct call: status, results, evidence_refs, error), including empty-result and validation-error cases. Exposure without parity coverage does not merge.
- Server grouping follows system ownership (telemetry vs platform), not convenience. RAG tools are OpsPilot-owned and stay in-process; any temporary exception (the parity scaffold) is documented as such in the server module docstring. Production transport is authenticated; trace ids and deadlines cross the boundary; errors use MCP-native signaling plus the standard payload.
- Do not put workflow nodes behind MCP to increase protocol usage. Do not use A2A between co-located subgraphs.

## 12. LLM integration

- Model IDs are config, not architecture (`config.py` tier maps); code references capability tiers, never model strings. Production model choice and judge strength are two independent decisions and stay decoupled.
- Prompts are versioned artifacts in the repo, each with id, version, purpose, expected output schema, allowed evidence/tools, injection-handling instructions, and eval coverage. The active `prompt_version` is stamped into audit logs and eval records. A behavior-affecting prompt change is a reviewed diff with its scorecard delta stated in the PR.
- LLM output crossing into state is schema-validated into the frozen Pydantic contracts. A parse failure is a degradation event (retry within a bounded policy, then degrade/escalate), not a crash. Free-text/regex parsing never controls a state transition.
- Iteration/token/cost/deadline budgets wrap every model loop from the first commit that introduces it — never added later. Use provider-reported usage as the primary cost record; fallback estimates are labeled estimates.

## 13. Persistence and durability

- Blob holds raw payloads, normalized evidence snapshots, and report versions — not the checkpoint. Blob names avoid sensitive raw values; each artifact stores content type, hash, schema version, and investigation metadata; approved artifacts are immutable/versioned; signed access is short-lived and authorized.
- Checkpoints never inline full logs, transcripts, or reports — references and bounded excerpts only. Add checkpoint retention and size metrics; test resume from older supported workflow versions.
- **Transactional outbox (provider-neutral):** any state change that must trigger indexing writes an outbox record in the same transaction as the state change; the indexer is idempotent and records source id, schema version, content hash, target index version, attempt count, and final status. This pattern holds whether the backend is Postgres (outbox table) or Cosmos (change-feed-driven equivalent).

✅ **RESOLVED — checkpointer backend: Cosmos DB** (first-party `langchain-azure-cosmosdb` saver, keyless via `DefaultAzureCredential`). Selected behind a `build_checkpointer()` seam (`none` / `memory` / `sqlite` dev / `cosmos` prod, unknown → `ValueError`). Rules: application data is separate from saver-owned containers; ETags for optimistic concurrency on approvals (never last-write-wins); TTL on stale checkpoints; the verified-memory sync is driven by the Cosmos **change feed**. Dev/CI runs the SQLite saver behind the same seam; the resume gate is `write → fresh saver on the same store → checkpoint recovered`.

✅ **RESOLVED — async dispatch: durable, in v1** ([§13.1](decisions.md#sec-13) *Durable dispatch* + *Ownership fencing*, resolving former open decision [§13.2](decisions.md#sec-13) D). A `202 Accepted` MUST correspond to a durable, recoverable accepted record — a 202 that vanishes on pod restart is dishonest, and post-response execution behind an HTTP scaler is exactly that. **Rule:** `POST /investigations` writes the investigation record **and** a dispatch-outbox record in **one Cosmos transaction** (one logical partition) before returning 202; the change feed relays the outbox event onto **Service Bus**; a **queue-triggered worker** (KEDA queue scaler — scales on queued work, not HTTP activity) drives the checkpointed graph. Service Bus is v1, not v2. Messages: versioned Pydantic carrying operation + investigation id + workflow version + correlation metadata; idempotent consumers; tested lock renewal; classified abandon/defer/dead-letter/complete; observable, replayable poison messages. **Fencing:** a non-terminal, non-paused run holds a lease *and* a monotonic **fencing epoch** — claiming bumps the epoch, every state transition writes conditionally on still owning it (ETag + epoch), so a lapsed-but-alive worker fails closed instead of racing its replacement. `awaiting_approval` is exempt from lease expiry.

## 14. Observability and audit

- Every investigation carries correlated trace id, incident id, investigation id, thread id, and workflow version. OpenTelemetry spans cover API, queue, graph node, model, retrieval, tool/MCP, database, Blob, validation, human decision, and indexing. LangSmith is a dev-local tracing adapter and never gates the Azure deploy.
- Metrics include: request/job counts by status, queue depth and age, graph turns, tool calls and failures, retrieval latency + quality sampling, model latency/tokens/cost, guardrail decisions, review wait time, checkpoint size, dead letters, and memory-indexing lag.
- Logs are structured. Raw prompts and evidence are not dumped by default; audit events carry evidence ids, not raw content, plus report hash and approval hash.

## 15. Security

- Separate managed identities per component (API, worker, telemetry MCP, platform MCP, closure publisher, search indexer, deployment pipeline), each least-privilege. Reviewer identity is a human Entra identity, not a workload identity. The diagnosis worker cannot mutate external systems, write verified memory, write the search index directly, or approve its own report.
- Prefer managed identity; Key Vault only for secrets that cannot be eliminated. Never log tokens, keys, connection strings, or full authorization headers.
- PII: before sending data to an external model, detect/redact per policy, record redaction status, and fail closed when policy requires screening and the detector is unavailable. Prompt-attack (Prompt Shields / injection classifier) and PII (Azure AI Language PII or Presidio) are **separate controls** — one is not a substitute for the other.
- The v1 tool catalog contains no mutating operation, and a test attempts a plausible mutating call and proves it is blocked before execution.

## 16. Azure, Bicep, and GitHub Actions

- Bicep is the desired-state source of truth; environment values live in parameter files; resources are tagged; identity and role assignments are explicit. Run `what-if` for material infra changes. The deploy workflow MUST NOT permanently mutate registry, ingress, identity, or scaling config outside Bicep.
- Container Apps carry liveness, readiness, and startup probes; images use immutable tags; deployment supports revision rollback. Public ingress is limited to the API; MCP and workers use internal ingress. Document demo-tier vs HA-tier parameters and never claim HA (≥2 replicas, zone strategy, DB backup/restore, RTO/RPO) before it is tested.
- GitHub Actions: least-privilege permissions, OIDC, pinned/reviewed actions, concurrency groups, environment protection for deploy, no long-lived cloud credentials. The PR workflow runs before deploy; artifacts (eval + smoke results) are published.

## 17. Determinism and reproducibility

- Synthetic generation is content-hash seeded; regeneration is idempotent. Golden JSON is **projected** from the answer key by `build_goldens.py` — never hand-edited.
- Anything the scorecard consumes is reproducible run-to-run: sorted outputs, pinned models, temperature 0 for judges, seeds recorded.
- The closure gate (`test_closure.py`) is sacred: any corpus change that breaks referential closure is a blocked merge, because every downstream eval scores against that key.
- Corpus loading fails loudly for malformed required documents; a required doc is never silently dropped because frontmatter is malformed. Past-incident retrieval accepts an `as_of` time and excludes future information, the current incident's own postmortem, and unverified or superseded memory — all proven by test.

## 18. Test taxonomy (menu, governed by [§3](architecture.md#sec-3))

Categories that may exist — used as needed, not as a coverage target: pure unit; state/reducer/property; tool contract; adapter; direct/MCP parity; graph scenario; API/persistence/queue integration; safety adversarial; evaluation suites; deployed smoke. Mock providers at ports, not deep SDK internals; use deterministic fake models for state-machine tests; keep live-model evaluation in a small, separately controlled job; never make ordinary unit tests depend on a network model.

## 19. Style, docs, and ADRs

- Module docstrings state purpose + current phase/status honestly. When a stub becomes real, the docstring changes in the same commit. Stale claims ("nodes are stubbed") in code or README are treated as bugs.
- Docs follow working code: architecture and plan documents update **after** code merges, in a commit referencing what changed. No speculative documents; do not describe a future component in present tense. Documentation labels each item current / target / deferred / rejected.
- Comments explain **why** (design intent, failure mode avoided), not what. The `# noqa` + reason pattern is mandatory for suppressions.
- Create an ADR for: persistence backend, async dispatch, model provider/routing, retrieval backend/index schema, MCP trust boundaries, multi-agent promotion, memory-admission policy, security failure behavior, and the observability/tracing emission seam (span primitives, attribute schema, sink/exporter split). (An ADR records a decision being made — this is consistent with docs-follow-code, not speculative.)

## 20. Pull requests

A PR implements one coherent vertical outcome tied to one step-gate; it names the gate test that proves it; it does not mix unrelated refactors or lower a threshold without explanation. PR description sections: (1) outcome, (2) architecture impact, (3) code changes, (4) guardrails, (5) tests/evaluation, (6) Azure/deployment, (7) metrics, (8) rollback, (9) deferred work.

## 21. Prohibited patterns (pre-merge checklist)

Do not merge code that:

- equates incident id and graph thread id;
- uses model confidence as a stop trigger;
- executes several evidence actions inside one checkpoint turn;
- retrieves an incident's own postmortem as proof it is a known issue;
- ranks future incidents for a past investigation;
- describes post-onset change as causal pre-onset evidence;
- defaults missing safety/guardrail state to pass (fails open);
- sends human edits directly to finalize;
- auto-approves a target HITL path;
- writes predicted RCA into retrieval memory;
- returns evidence references for truncated-away results;
- silently skips malformed evidence under a clean success;
- catches every exception without internal logging/correlation;
- lets an exception, stack trace, or filesystem path cross the tool boundary;
- adds a blind-append (`list + operator.add`) reducer to a re-entrant/parallel collection;
- mirrors the same fact in a scalar and a nested structure;
- hard-codes rollback (or any mutating action) as the recommendation for every incident;
- depends on repository-relative files absent from the runtime image;
- calls a health endpoint the deployment smoke test;
- claims a CI gate without a CI workflow enforcing it;
- updates a weak baseline to make tests green;
- creates a second tool implementation inside an MCP server;
- hard-codes transient model IDs into domain logic;
- returns `202` without a durable, recoverable accepted record;
- adds an agent or protocol without a measurable use case;
- adds a node, tool, subagent, or cross-service boundary that emits no span under the parent trace_id;
- hand-instruments tracing per node instead of at the shared primitive wrapper, or emits a span/usage record outside the §23 schema.

## 22. Definition of done (per step)

A step is done when:

1. its gate test exists and passes in CI;
2. contracts are typed and versioned; error and degradation behavior are defined;
3. the scorecard is re-run and any baseline change is committed with rationale (release thresholds pass; no critical per-scenario regression);
4. required tests are not skipped; security tests cover the new surface;
5. traces and metrics exist for the new capability — a span under the parent trace_id carrying the [§23](#23-observability-and-tracing-the-emission-seam) attribute set, proven by the in-memory exporter fixture (not merely present in prose);
6. Azure configuration is represented in Bicep, and the deployed smoke test exercises the capability (not just `/health`);
7. rollback is possible;
8. no locked decision is newly violated — or the violation is recorded in the architecture doc's build status with its scheduled fix;
9. docstrings and README reflect reality;
10. `ruff` + `mypy` are clean;
11. no current-state claim exceeds what was tested.

## 23. Observability and tracing (the emission seam)

Tracing is a cross-cutting concern instrumented **once at the primitives**, not per node. A
new node, tool, subagent, or cross-service boundary inherits a span for free; hand-instrumenting
an individual node is prohibited (it drifts).

- Emission lives in **one span-emitting wrapper each** for: the node dispatch path, `run_tool` /
  `gateway.execute`, the `ChatModel` client, and the MCP client. New code built on these MUST NOT
  add its own bespoke tracing.
- Every span carries the **standard attribute set** under the parent `trace_id`: `trace_id`,
  `investigation_id`, `incident_id`, `workflow_version`, `prompt_version`, `model_deployment`,
  `tool_name` + `canonical_args_hash` + `result_hash`, retrieved doc ids, `latency_ms`, tokens
  (in/out), cost, and tool `status`. A span outside this schema is a defect, not a variant.
- **Hierarchy is mandatory.** A subagent subgraph (§7 / [§13.2](decisions.md#sec-13) B) and any MCP
  or A2A boundary crossing MUST emit spans that **nest under the parent `trace_id`** — quarantine
  removes noise from the parent *context*, never from the *trace*. `trace_id` propagates across
  every boundary.
- **Usage is captured on every model call**, from the `ChatModel` client, into the normalized usage
  record ([`adr-model-provider.md`](./adr-model-provider.md)). This is **capture, not enforcement** —
  the iteration/cost budget is [G-08](status.md#g-08) at Stage 6b.
- Emission adds **zero cassette churn**: `trace_id`, span attributes, and the usage record are **not**
  behavior-affecting inputs, so they are outside the replay manifest ([§10](evaluation.md), G-54).
  Instrumentation may be added at any stage without a re-record.
- **Emission is standing; aggregation is deferred.** In scope from Stage 5g: OTLP-shaped span
  emission + usage capture, with the exporter chosen by config (`none`/`memory`/`stdout` shipped).
  **Sinks land on a schedule, one stage each:** the local **LangSmith Developer** sink at **Stage 8**
  (dev-local, synthetic-or-scrubbed, never a deploy gate — [G-57](status.md#g-57)); the App Insights
  export target, dashboards, drift monitoring, the live canary, and arming the hard gate at **Stage
  11**. Do **not** build the aggregation stack early, and do **not** add an exporter without the stage
  that owns it — an unscheduled sink is how observability work goes missing.
- Posture: **advisory now**; the hierarchy check is a **hard gate at the §7 and 6c boundaries** that
  already require it; it hardens into a standing review gate once the seam is proven — the same
  "advisory until it gates" shape as [§3](architecture.md#sec-3)'s eval discipline.
- **Tested, not asserted.** A reusable in-memory span exporter fixture proves "emitted a span under
  the parent `trace_id` with the required attributes." A missing or broken trace is a silent failure
  exactly when it is needed, so this fixture rides the existing state-contract and smoke lanes rather
  than being left to prose.
