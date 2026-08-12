# OpsPilot - Status

**Purpose:** record what is actually built, verified, missing, misaligned, reusable, replaceable, and removable against the accepted OpsPilot design. This document does not sequence work. `vertical-execution-plan.md` owns the implementation sequence.

This version merges the corrected repository reconciliation draft with the earlier, more granular status inventory. Where the two documents conflicted, the corrected Phase 3A target and the newer live repository/Azure inspection were used. Older detail was retained only when it still describes the inspected repository or exposes an implementation consequence.

## 1. Document Status

- Title: Repository reconciliation status against the accepted OpsPilot design.
- Original inspection date: 2026-08-05.
- Prior draft correction date: 2026-08-06. The corrections changed classification wording and planning
  references only; repository evidence was not re-collected.
- Repository inspected: branch `stage-5f-durable-dispatch` at `0c3c175` (WIP durable-dispatch
  skeleton), one unpushed commit ahead of `origin/main` at `e567adf`. The working tree, including
  the WIP commit, was inspected; differences from `main` are called out where they matter.
- Documentation baseline: the nine authoritative documents as accepted at Phase 3A
  (2026-08-05), plus the seven audit records.
- Inspection scope: all source (`src/opspilot`, 9,429 lines), tests (47 files, 5,749 lines),
  eval assets (`eval/`, 5,300 lines), data corpus (`data/`, ~2.9 MB committed), infrastructure
  (`infra/main.bicep`), CI (`.github/workflows/deploy.yml`), scripts, Dockerfile, dependency
  manifests, repository documentation, and the course source material at
  `..\Source Material\`.
- Commands executed: `ruff check` (pass), `ruff format --check` (66 files would reformat; CI runs
  check only, so formatting is unenforced), `mypy src` (2 errors, both in the WIP dispatch wiring,
  `api.py:862` and `api.py:866`), `az bicep build` (compiles), full pytest with CI's marker filter
  (31 failed, 351 passed, 5 deselected in 11m28s; every failure in
  `tests/test_investigations_api.py`, the surface the WIP dispatch commit broke).
- Azure inspected live (read-only): yes, resource group `rg-opspilot` under the authenticated
  subscription. No live resource was modified.
- Nothing in the repository, its data, or its infrastructure was modified by this inspection.
- Source merge completed: 2026-08-06.
- This merge did not re-run repository commands or re-inspect Azure. Verification timestamps remain those of the underlying inspection.
- Repository reset landed 2026-08-08: branch `s0-repository-reset`, cut from `main` at `e567adf`,
  merged to `main` via PR #54 as squash commit `4c8f706`. The WIP commit `0c3c175` inspected above
  is confirmed abandoned, not an ancestor of `main`. Re-run on `main` at `4c8f706`: `ruff check`
  (pass), `mypy src` (0 errors, was 2), full pytest with CI's marker filter (382 passed, 5
  deselected, 0 failed, was 31 failed/351 passed). `az bicep build` and the Azure inventory were
  not re-run; nothing under `infra/` or in the live subscription changed.
- Streaming turn skeleton landed 2026-08-09: PR #59 (turn identity, the normalized
  incident-context contract as `decisions.md` D-007, the stream envelope and activity-projection
  contracts, `turn_id` on the telemetry seam), PR #60 (the streaming endpoint, plus `ruff format`
  enforcement scoped to touched files), PR #61 (the one-screen client and client-disconnect
  detection). Verified live in a browser and against the real corpus: identities first, close
  marker last, no answer-key content on the stream, independent identities across concurrent
  turns. Two gaps left deliberately: the accepted explicit cancellation-request mechanism does not
  exist (only client-disconnect detection), and `InteractionKind` exists as a type with no
  classifier producing it.
- Evidence reference model and two-axis capability results landed 2026-08-11: PR #66 (one parser,
  one resolver, one prefix-to-type map; `past_incident:` retired for `postmortem:`; `decisions.md`
  D-008 and D-009), PR #67 (execution outcome and completeness as separate axes with the legal
  pairing enforced on construction, evidence admission as the only door into the evidence set, the
  operation ledger held separately, one capability inventory replacing the duplicate allowlist,
  and the protocol boundary carrying both axes with parity asserted on each). Full suite 515
  passed, 1 xfailed; `ruff`, `ruff format`, and `mypy src` clean.
- Operational capabilities moved onto the container 2026-08-11. The five operational capabilities,
  the incident lookup behind predefined intake, and reference resolution read
  `operational-records` through `data/operational_records.py`; `data/repository.py` is deleted and
  the image no longer ships the operational corpus. Each capability takes an explicit deadline and
  hands it to the source, a request naming its own is refused at dispatch, and a container that
  cannot answer reports `unavailable` rather than `failed`. Readiness now counts every record kind
  and fails closed. Preparation was found to be overwriting each dependency edge's own relationship
  kind with the partition value, since `/kind` is both a partition path and a field the edges carry;
  the edge's kind is now carried as `dependency_kind` and mapped back at the adapter, which means
  the live container holds clobbered edges until it is reseeded. Repository inspected at
  `f5c2b42`. Full suite 600 passed, 11 skipped, 1 xfailed across 59 test files (606 collected);
  `ruff check`, `ruff format`, and `mypy src` clean. The container was reseeded on 2026-08-11 and
  read back: all 14,013 documents match the shaping, and the twelve edges now carry their own
  relationship kind.
- A partial observation now stays marked partial where a claim rests on it, 2026-08-11. An element
  citing a `partial` observation produces a limitation in the assessment naming what the source did
  not return, deduplicated per producing operation and rendered by the brief. Carried as a
  limitation rather than on the citation, which is authored as a reference and a role and nothing
  else; the execution outcome separates an incomplete answer from an operation that did not answer,
  so no vocabulary was extended. Measured with the fuller lane's own command,
  `pytest -q -m "not reranker and not llm"` against the `eval` group: 642 passed, 5 deselected,
  1 xfailed; `ruff check`, `ruff format`, and `mypy src` clean.
- Cosmos data-plane permissions inspected live, 2026-08-11 (read-only, nothing modified). The
  application identity holds two differently scoped grants and no account-wide one: Data
  Contributor on `opspilot/investigations`, and Data Reader on the whole `retailease` database. The
  reader definition's data actions are `readMetadata`, `executeQuery`, `readChangeFeed`, and
  `items/read`, so no write action exists for the application to attempt. Corpus preparation's
  Contributor grant on `retailease` belongs to a different principal. Nothing asserts this yet; the
  check that will is named in `runtime-and-deployment.md` §16.
- One incident to a rendered assessment landed 2026-08-12: PR #69 (assessment contracts), PR #70
  (Investigation Record port, commit semantics, and commit-before-delivery ordering), PR #71
  (synthesis admission and deterministic brief projection), and the branch that wires the streamed
  turn to gather, admit, synthesize, and render. Correlation identities now propagate through the
  tracing seam so every span emitted inside a turn carries `investigation_id` and `turn_id` rather
  than the root alone, and admission emits its own span. `decisions.md` D-008 was amended with the
  `absence:` evidence prefix, so an authoritative empty result is citable instead of being
  identified only by the operation that produced it. The synthesis path is deterministic in CI
  through `eval/cassettes/turn_synthesis.json`, recorded once against `gpt-5-mini` on `inc-005`;
  replay needs no provider SDK, so it runs in the lane that installs none. Two CI-equivalent lanes
  run with their own dependency groups, re-measured after merging the partial-observation work
  above: dev+data+eval 675 passed, 5 deselected, 1 xfailed; dev+data 639 passed, 8 skipped,
  3 deselected, 1 xfailed. `ruff check` and `mypy src` (81 files) clean.

## 2. Executive State

**The repository implements the previous OpsPilot architecture, not the accepted one.** It is a
working, well-tested, deployed single-agent LangGraph application built around a human-in-the-loop
approval gate, per-step durable checkpointing, an asynchronous 202-and-poll job API, and (in the
WIP commit) an outbox, queue seam, and dispatch worker. Every one of those load-bearing choices is
explicitly rejected by the accepted design: no approval gate exists between synthesis and delivery,
active-turn state is ephemeral, one live streaming request owns one turn, and queues, workers,
durable orchestration, and replay are named deliberate absences.

- **Strongest existing foundations:** the read-only tool layer (8 tools, one canonical result
  envelope, static registry, sanitized errors), the authored corpus and answer-key machinery
  (7 incidents, closure-verified references, KB with frontmatter and recurrence signatures), the
  MCP parity approach (same `ToolService`, byte-identical result model), the LLM client seam
  (provider factory, structured-output validation, prompt registry, cassette replay), the tracing
  seam, and the OIDC CI/Bicep deployment skeleton.
- **Largest contradictions:** turn lifecycle (async jobs + polling + HITL pause versus one
  streaming request with no approval stage), agent topology (2 model roles versus 3 agents and 6
  boundaries), outcome vocabulary (`grounded_rca`/`partial`/`knowledge_briefing`/`escalation` plus
  a 7-value job status versus complete/partial/inconclusive), orchestration technology (LangGraph
  + checkpointers versus D-001's explicit in-process state machine with no graph runtime), and
  persistence layout (`checkpoints`/`investigations`/`investigation-index` versus
  `investigations`/`knowledge`/`operational-records`).
- **Largest deletion opportunities:** the entire durable-dispatch WIP (`dispatch.py`, `worker.py`,
  lease/epoch fields, Service Bus config), the HITL decision surface (endpoints, `hitl_gate`,
  `apply_edit`, decision records, console approval UI), the checkpointer stack and its
  dependencies, the unreachable model reranker, and the unused severity-tier model-routing table.
- **Largest missing capabilities:** streaming turn execution and the activity projection, the
  three-agent split, the four-check grounding gate and grounded-element assessment, follow-up
  answers and handoff, cancellation, governed structured query, deterministic
  identifier-priority reranking, Cosmos-backed knowledge and operational-records containers,
  model routing (a second deployment), the offline judge, and the fixed-script baseline.
- **Key verification risks:** Cosmos vector-index viability (no vector configuration exists
  anywhere yet), the MCP library questions (D-004), and corpus defects that would undermine the
  accepted demonstrations (physically contradictory telemetry in 4 of 7 incidents,
  effect-before-cause orderings, answer leakage in the recurrence scenario).
- **Simpler or more complicated than the target?** More complicated where it matters most (durable
  workflow machinery, approval protocol, three-container job persistence, hand-rolled three-role
  JWT authorization) and simpler than required elsewhere (no streaming, no multi-agent split, no
  structured query, BM25-only runtime retrieval, no App Insights).

## 3. Reconciliation Basis

The repository classifications and findings recorded below were evaluated against the accepted
target as expressed by:

- the nine authoritative OpsPilot documents;
- the accepted Phase 3A documentation baseline;
- the frozen three-agent and six-boundary model;
- the one-application, one-streaming-request runtime;
- the required grounding, retrieval, structured-query, MCP, activity, evaluation, and Azure
  contracts;
- the deliberate absence of queues, workers, checkpoints, replay, approval stages, and other
  rejected production machinery.

See the authoritative documents for the complete target design and
`vertical-execution-plan.md` for the capability sequence and implementation path.

## 4. Repository Inventory

| Area | Contents | Size |
| --- | --- | --- |
| `src/opspilot/` | FastAPI app (`api.py` 1,153 ln), LangGraph orchestration (`graph.py`, `nodes/investigation.py` 12 nodes, `router.py`), state/contracts, async-job repositories (`investigations.py`, `cosmos_investigations.py`), WIP dispatch (`dispatch.py`, `worker.py`), auth (`auth.py`), config, diagnosis (planner/sufficiency/admission/render), guardrails (2 policies), llm (client/prompts/cassettes/manifest), mcp (stdio server), obs (hand-rolled tracing), retrieval (BM25 + dense + RRF + unreachable CrossEncoder), tools (8 read-only), static console (870 ln polling client) | 9,429 lines |
| `tests/` | 59 files, 606 collected (re-measured 2026-08-11); strongest on HITL/decision protocol, auth, capabilities, corpus integrity; zero tests for dispatch/worker, cancellation, follow-up, handoff, structured query | 5,749 lines |
| `eval/` | scenario/retrieval/wild evaluators, 4 recorded baselines, 2 cassettes, 2 goldens, stub harness | 5,300 lines |
| `data/` | answer key (7 scenarios YAML + topology), synthetic telemetry (13,780 logs, 175 metric series, 16 alerts, 9 deploys, 7 incidents, 12 edges), KB (12 docs), distractors (16), profiles; 5.2 GB gitignored third-party caches | ~2.9 MB committed |
| `infra/` | one `main.bicep` (469 ln): Log Analytics, ACR, Azure OpenAI (one `gpt-5-mini` deployment), Cosmos serverless (3 containers: `checkpoints`, `investigations`, `investigation-index`), managed environment, one Container App (0-3 replicas), role assignments | 469 lines |
| `.github/` | one workflow `deploy.yml`: lint/type/test lanes, ACR build, Bicep deploy, smoke | 119 lines |
| `scripts/` | one file: `smoke_deployment.py` (hosted smoke incl. HITL durability check via revision restart) | 479 lines |
| Repo docs | `README.md` (34 ln, five stages stale, claims "no LLM in the loop yet"), `.env.example` (drifted), untracked `docs/` and `.githooks/`, stray `out.txt`/`raw.txt` (third-party slide dumps) | - |


### 4.1 Detailed file-level inventory

### Application source (`src/opspilot/`)

| Module | What it does |
| --- | --- |
| `__init__.py` | Package version string |
| `api.py` | FastAPI surface: liveness/readiness/version, synchronous `/investigate`, async job API (`POST /investigations` 202 + poll + `POST .../decision`), operator console routes, lazy singletons for graph/tools/repository/authenticator/dispatch, outbox relay, publication sink, per-user and global concurrency caps |
| `auth.py` | Entra JWT validation (JWKS, issuer, audience, expiry) producing a `ReviewerPrincipal`; role authorization (`Approver`/`Submitter`/`Reader`); human vs service-principal labelling |
| `checkpoint.py` | LangGraph checkpointer factory: `none`/`memory`/`sqlite`/`cosmos` backends |
| `composition.py` | Composition root selecting `deterministic` vs `single_agent` diagnosis (planner + triager), with explicit fallback and reason surfaced in `/version` |
| `config.py` | Env-driven settings: KB and distractor paths, the source-call deadline ceiling, retrieval backend, severity→model-tier map (Claude tiers), LLM provider seam, reasoning effort, sampling seed, checkpointer/repository/dispatch backends, Entra roles, concurrency caps, loop bounds, up-front numeric eval targets (`EvalTargets`) |
| `contracts.py` | Frozen `IncidentReport` with content hash; discriminated result union `GroundedRcaReport` / `PartialInvestigationReport` / `KnowledgeBriefing` / `EscalationNotice` |
| `cosmos_investigations.py` | Cosmos-backed `InvestigationRepository`: two containers (records + idempotency index), ETag optimistic concurrency, atomic decision commit, publication sink, lease/fencing epoch |
| `dispatch.py` | Durable dispatch queue seam: `DispatchMessage`, classified settlement (`complete`/`abandon`/`dead_letter`), `inline`/`memory`/`servicebus` backends, outbox relay (`relay_pending`) |
| `graph.py` | LangGraph build: ingest → triage_router → retrieve → diagnose(loop) → synthesize_report → safety_validate → hitl_gate → apply_edit/finalize_report → postmortem, escalate; checkpointer wiring, msgpack allowlist, `invoke_auto_approving` |
| `investigations.py` | Async investigation resource: status machine (`queued/running/awaiting_approval/completed/degraded/escalated/failed`), `DispatchEntry` outbox-on-record, `CommittedDecision` idempotency, lease/fencing, in-memory repository |
| `repository.py` | Factory selecting memory vs cosmos investigation repository |
| `router.py` | Graph conditional edges: intent routing, diagnose stop rule, safety→gate, approval decisions |
| `state.py` | Pydantic `InvestigationState`: identifiers, evidence-by-hash with merge reducers, hypothesis, causal claim, report/report_hash/publication_id, safety/approval dicts |
| `triage.py` | Triager seam: deterministic self-match floor + LLM triager (recurrence detection) |
| `worker.py` | Queue-triggered worker: claim with lease/fencing epoch, drive the checkpointed graph, classified message settlement |
| `data/operational_records.py` | Read-only, partition-scoped queries over the `operational-records` container; per-kind counts for the preparation check; the lazy process-wide reader. Replaced `data/repository.py`, the file-backed corpus repository, deleted 2026-08-11 |
| `diagnosis/admission.py` | Deterministic admission of proposed causal/report claims: entity resolution against touched entities, support-ref grounding, fail-closed refusal |
| `diagnosis/contracts.py` | Diagnosis contracts: `EvidenceCitation` (with proposed role), `Hypothesis`, `CausalClaim`, `ReportClaim`, `Acknowledgement`, `SufficiencyState`, `StopReason`, plans/questions |
| `diagnosis/cycle.py` | One deterministic diagnostic cycle: fixed deploy-regression plan + counter-evidence, onset clamp, citation assembly |
| `diagnosis/llm_planner.py` | LLM planner: batched tool-call planning, JSON extraction, param coercion, grounded synthesis via admission |
| `diagnosis/observe.py` | Tool-result summarizers (`signal [ref]` compaction for the model) |
| `diagnosis/planner.py` | Planner protocol + deterministic planner + factory |
| `diagnosis/render.py` | Template rendering of causal/report-claim statements from structured fields |
| `diagnosis/sufficiency.py` | Severity-scaled deterministic stop-rule inputs (evidence classes, coverage) |
| `llm/base.py` | Provider-agnostic `ChatModel` protocol, `ChatMessage`/`ChatResult` |
| `llm/client.py` | OpenAI-compatible + Azure OpenAI clients (keyless via managed identity), reasoning-model handling, factory, `TracedChatModel` |
| `llm/cassette.py` | Record/replay cassettes keyed by content hash + behaviour manifest, drift detection |
| `llm/fake.py` | Deterministic fake `ChatModel` for tests |
| `llm/manifest.py` | Behaviour manifest (model, reasoning effort, API version, seed, prompt versions) for cassette validity |
| `llm/prompts.py` | Versioned prompt registry (`<name>.v<N>.md`, append-only) |
| `llm/prompts/*.md` | Prompt texts: `diagnose_planner.v1-v3`, `diagnose_synthesize.v1-v2`, `triage.v1` |
| `llm/schema.py` | Typed model-response schemas: `PlannerResponse`, `SynthesisResponse`, `CausalClaimResponse`, `ReportClaimResponse`, `TriageResponse` |
| `mcp/server.py` | MCP server fronting `ToolService.call()`; exposes `get_incident`, `query_logs`, `search_runbooks` |
| `nodes/investigation.py` | Graph node bodies: ingest, triage_router, known_issue_fast_path, retrieve, diagnose, synthesize_report, safety_validate, hitl_gate (interrupt), apply_edit, finalize_report (derived publication_id), postmortem, escalate |
| `obs/tracing.py` | Span seam: OTLP-shaped spans, contextvar nesting, `none`/`memory`/`stdout` exporters, `traced_node` wrapper |
| `guardrails/policies.py` | Read-only tool allowlist; citation-grounding check (`hypothesis_supported`) |
| `retrieval/base.py` | `SearchRetriever` protocol, tokenizer, `Hit`, filter/aggregate helpers |
| `retrieval/bm25.py` | Lexical BM25 runtime backend over chunked KB |
| `retrieval/adapters.py` | Adapter presenting the hybrid `Retriever` through the `SearchRetriever` seam |
| `retrieval/corpus.py` | KB + distractor loading and section-level chunking |
| `retrieval/embeddings.py` | sentence-transformers embedder wrapper (bge family) |
| `retrieval/index.py` | `VectorIndex` protocol + in-memory cosine index |
| `retrieval/reranker.py` | Cross-encoder reranker wrapper (bge-reranker) |
| `retrieval/retriever.py` | Dense/hybrid(RRF)/rerank evaluation retriever |
| `retrieval/factory.py` | Backend factory: `bm25` / `hybrid` / `rerank` |
| `tools/contracts.py` | Tool request models + uniform `ToolResult` envelope (`status: ok\|error`, evidence refs, metadata) |
| `tools/errors.py` | `run_tool` boundary: validate, time, cap, sanitize |
| `tools/service.py` | `ToolService`: eight read-only tools + allowlisted `call()` dispatch, lazy retriever |
| `tools/{alerts,dependencies,deployments,incidents,logs,metrics,search}.py` | The individual read-only tools over the `operational-records` container and the retriever; each takes an explicit deadline and hands it to the source |
| `tools/__init__.py`, `data/__init__.py`, `diagnosis/__init__.py`, `llm/__init__.py`, `mcp/__init__.py`, `nodes/__init__.py`, `obs/__init__.py`, `ops/__init__.py`, `guardrails/__init__.py`, `retrieval/__init__.py`, `eval/__init__.py` | Package markers (`ops/` and `eval/` are empty placeholders) |
| `static/console.html` | 870-line self-contained operator console: submit/poll/review, Entra sign-in, decision buttons (approve/edit/reject/request-more-evidence) |

### Tests (`tests/`)

44 test modules plus `conftest.py` and `fixtures/wild_ob/` (two RCAEval metric fixtures). Individual
classification is in sections 5 and 8; the files are: `test_answer_key`, `test_api`, `test_auth`,
`test_bm25`, `test_cassette`, `test_checkpointer`, `test_closure`, `test_composition`,
`test_conclusion_contracts`, `test_conclusion_wiring`, `test_cycle_onset_clamp`, `test_diagnose`,
`test_evidence_coverage`, `test_guardrails`, `test_incidents_alerts`, `test_investigations`,
`test_investigations_api`, `test_kb`, `test_llm_client`, `test_llm_e2e`, `test_llm_planner`,
`test_mcp_parity`, `test_observe`, `test_planner_seam`, `test_prompts`, `test_report_binding`,
`test_repository_factory`, `test_retrieval`, `test_retrieval_factory`, `test_runtime_assets`,
`test_scaffold`, `test_scenario_gate`, `test_schema`, `test_search_tools`, `test_single_agent_gate`,
`test_state`, `test_state_contract`, `test_sufficiency`, `test_telemetry`, `test_tool_chain`,
`test_tools`, `test_tools_operational`, `test_tracing`, `test_triage`, `test_triager`, `test_wild`.

### Corpus and evaluation data (`data/`, `eval/`)

| Path | What it is |
| --- | --- |
| `data/answer_key/{scenarios.yaml,topology.yaml,build_goldens.py,README.md}` | The authored RetailEase answer key and its deterministic projection into golden files |
| `data/kb/` (12 md + README) | The knowledge corpus: 6 runbooks, 3 architecture docs, 3 postmortems |
| `data/distractors/` (16 md) | Distractor corpus for retrieval evaluation |
| `data/synthetic/` (6 data files + 2 generators + README) | Generated telemetry: incidents, alerts, deployments, logs, metrics, dependencies |
| `data/profiles/` (3 scripts + 2 json) | RCAEval/ITSM-derived signal profiles calibrating the generator |
| `data/provenance.md`, `data/.gitkeep` | Corpus provenance notes |
| `eval/harness.py` | Generic evaluator-runner scaffold |
| `eval/scenario_eval.py` | Runs six scenarios through the graph, scores a scorecard vs committed baseline |
| `eval/retrieval_eval.py` | MRR/P@k/R@k over `golden_retrieval.json` across dense/hybrid/rerank |
| `eval/wild.py`, `eval/record_wild.py` | RCAEval Online-Boutique generalization probe + recorder |
| `eval/record_single_agent.py` | Records the single-agent cassette + scorecard from a live model |
| `eval/golden_incidents.json`, `eval/golden_retrieval.json` | Projected golden sets |
| `eval/baselines/*.json` (4) | Committed scorecards: retrieval, slice, single-agent, wild |
| `eval/cassettes/*.json` (2) | Committed LLM cassettes for replay |

### Infrastructure and operations

| Path | What it is |
| --- | --- |
| `infra/main.bicep` (+ `infra/.gitkeep`) | Azure: Log Analytics, ACR, Container App (min 0 replicas), Azure OpenAI account + `gpt-5-mini` deployment, vector-capable Cosmos account with one `investigations` container (2026-08-09), role assignments, Entra params |
| `Dockerfile` | Multi-stage uv build; installs `llm` + `checkpoint` groups; packages the KB only, the operational corpus having no runtime reader left; BM25 backend |
| `.github/workflows/deploy.yml` | CI (ruff, mypy, pytest lanes) + ACR build + Bicep deploy + post-deploy smoke |
| `scripts/smoke_deployment.py` | Post-deploy smoke: readiness, version, sync investigate, async 202+poll+decision path |
| `.dockerignore`, `.gitignore`, `.env.example`, `.python-version`, `pyproject.toml`, `uv.lock`, `README.md` | Build/config housekeeping |

### Untracked (not part of the inspected commit)

`docs/` (the design set, this file, `docs/archive/`, `docs/audits/`), `.claude/settings.json`,
`.githooks/pre-commit`.

### Coverage check

The inspection's own completeness test: a file that is neither classified nor listed as inventory is
a gap in the inspection, not an absence of finding. Every tracked path at the inspected commit was
matched against this document.

**199 tracked files found; 199 appear.** Each appears either by name, or inside a group above that
states its full member set or gives its full glob (`data/kb/`, `data/distractors/`,
`data/synthetic/`, `eval/baselines/*.json`, `eval/cassettes/*.json`, `tests/fixtures/wild_ob/`).
No tracked file is unaccounted for, so no file required classification on this pass.

Three paths were excluded, each for the same reason: `docs/`, `.claude/settings.json`, and
`.githooks/pre-commit` are untracked and therefore not part of the inspected commit. They are listed
as inventory immediately above rather than classified.

## 5. Verification and Test Results

The inspection recorded both the CI marker lane and a full optional-group run. The repeated CI-lane
runs produced the same counts with different wall times, so duration is treated as environmental
rather than contractual.

| Run | Result |
| --- | --- |
| `ruff check` | Pass |
| `ruff format --check` | 66 files would reformat at inspection, 46 now. Formatting is enforced, scoped to the files a change touches, by CI and by the `pre-commit` hook; the unformatted remainder is the tree no change has touched since |
| `mypy src` | 2 errors, both in the WIP dispatch wiring at `api.py:862` and `api.py:866` |
| `az bicep build` | Pass |
| CI marker lane: `pytest -m "not reranker and not llm"` | 31 failed, 351 passed, 5 deselected. Repeated recorded wall times were 11m28s and 15m36s |
| Full suite with all optional groups and local Ollama available | 31 failed, 356 passed, 0 skipped of 387. Pytest reported 9h19m12s, dominated by CPU-based live-model tests |

**All 31 failures have one root cause and one test module.** Every failure is in
`tests/test_investigations_api.py`. `run_investigation_job` passes `epoch=` to
`_run_investigation_job()`, whose signature does not accept it. The resulting background-task
`TypeError` breaks the async lifecycle, decision, read-authorization, and concurrency tests. The
failure belongs to the unpushed durable-dispatch WIP that the accepted design rejects, but the
inspected branch is still red and its advertised old primary API does not work.

The current suite does not assert the accepted design end to end. Passing tests fall into three
groups:

- **Still meaningful:** read-only tools, request validation, error sanitization, corpus closure,
  answer-key integrity, lexical and hybrid retrieval primitives, evidence deduplication, prompt and
  cassette seams, tracing, and direct-versus-MCP parity.
- **Tests of removed behavior:** HITL approval, reviewer roles, checkpoint recovery, async job
  repositories, escalation statuses, severity-scaled sufficiency, old intent routing, numeric
  scorecard gates, and the deferred RCAEval probe.
- **Environment-dependent live-model tests:** passed on the inspected workstation because a local
  Ollama model was available; they are excluded from the CI gate.

The committed cassettes replayed without manifest-drift failures. That proves the replay mechanism
is internally consistent at the inspected commit, not that the recorded prompts and model choices
match the accepted target.

## 6. Detailed State by Design Area

Classification is at behavior level. Where one module carries an aligned responsibility inside
machinery that is not, both classifications appear. Removal detail is in section 8.

### 6.1 The six components

**Engineer Interaction Interface** (`system-design.md` §4.1) - **MISSING.** No intake normalization
(predefined or free-text), no single-clarification path, no five-kind follow-up classification, no
activity presentation, no handoff-summary rendering exists. `static/console.html` is an
engineer-facing page, but it implements submit-alert → poll-job → review-report → approve/edit/
reject, which is the removed approval interaction over the removed job API; its approval UI is
OBSOLETE and its transport (polling a job resource) is MISALIGNED with the streaming model
(`runtime-and-deployment.md` §2). Nothing in it survives as the designed interface.

**Supervisor** (`system-design.md` §4.2) - **MISSING.** No component owns a turn objective, budgets
as designed, continuation authorization against computable conditions, the correction allowance, the
terminal-shape decision, or completed-turn commits. The LangGraph pipeline (`graph.py`,
`router.py`) sequences fixed stages, but its stop rule is a sufficiency/coverage gate
(`diagnosis/sufficiency.py`) rather than the proposal-authorization split (`workflow-design.md`
§5), and its terminal shapes are completed/degraded/escalated (section 8, obsolete vocabulary).

**Evidence Investigator** (`system-design.md` §4.3) - **PARTIAL, inside a misaligned topology.**
Adaptive, observation-driven evidence-source selection genuinely exists: `LLMPlanner.plan` chooses
the next tool calls from the full observation trail (FR-49, FR-51, FR-86), never repeats a call, and
fails closed on non-allowlisted tools. What is missing: the role is not separated from synthesis
(the same `LLMPlanner` also concludes, which the fixed three-role topology forbids - FR-77 to
FR-79); proposals are not authorized by a Supervisor; there is no working-hypothesis contract.

**Evidence Access Layer** (`system-design.md` §4.4, §8) - **PARTIAL.** Implemented and aligned in
shape: a closed registry (`ToolService._registry`) as the single dispatch surface (§8.1), the five
operational capabilities exactly as §8.2's table names them (incident/alert lookup, log query,
metric query, deployment history, topology), read-only enforcement via allowlist
(`guardrails/policies.py`), request validation at the boundary (`tools/errors.py.run_tool`), and
provider-error sanitization. Missing or misaligned: the two-axis result vocabulary
(`data-and-evidence.md` §4) - `ToolResult.status` is binary `ok|error`, which is precisely the
collapse `code-guidelines.md` §13 prohibits; deterministic evidence *admission* of observations into
an admitted-evidence set with limitations (`data-and-evidence.md` §6) does not exist (admission code
exists only for model-proposed claims, a different thing); and the governed structured-query
capability is absent entirely.

**RCA Analyst** (`system-design.md` §4.5) - **MISSING as designed; the nearest machinery is
MISALIGNED.** Synthesis exists (`LLMPlanner.synthesize` + `diagnosis/admission.py` +
`diagnosis/render.py`), and admission's model-proposes/code-admits split with template rendering is
the same philosophy as the design's deterministic control. But the assessment contract is a
different object: one `CausalClaim` plus report claims, with `Hypothesis.confidence` as a 0-to-1 float
 -  numeric confidence is prohibited anywhere in the assessment (`data-and-evidence.md` §12,
invariant 8). No candidate set, no qualitative labels (Leading/Plausible/Weakly supported), no
supporting-and-weakening structure per candidate, no established/possible markers, no
recommendation horizons, no further-evidence need.

**Investigation Record** (`system-design.md` §4.6, §9) - **MISSING as designed.**
`investigations.py` / `cosmos_investigations.py` persist a job-lifecycle record: status history,
pending interrupts, committed decisions, leases and fencing epochs, an outbox, a publication id.
None of that is the completed-turn artifact (`data-and-evidence.md` §17), and nearly all of it
serves removed machinery (section 8). The two-container Cosmos layout (records + idempotency index) does
not match `runtime-and-deployment.md` §10 (one `investigations` container plus one categorized `knowledge` container and one `operational-records` container, where the latter two do not exist anywhere).

### 6.2 Turn lifecycle (`workflow-design.md` §§2-9)

**MISSING.** No investigation/turn/live-session model, no five stages, no streaming request owning
a turn, no cancellation floor, no correction allowance, no further-evidence cycle, no
complete/partial/inconclusive outcomes, no failed-execution semantics. The implemented lifecycle
(ingest → triage → retrieve → diagnose loop → synthesize → safety → HITL → finalize → postmortem,
with escalate) is the superseded shape end to end; its stages, statuses
(`queued/running/awaiting_approval/...`), and stop reasons are OBSOLETE or misaligned per section 8.

### 6.3 Grounding gate (`data-and-evidence.md` §13; `workflow-design.md` §7)

**MISALIGNED.** `safety_validate` + `guardrails/policies.hypothesis_supported` implement one check:
every citation must be a tool-produced ref. That is a real ancestor of reference resolution /
unsupported-element rejection, but the gate the design fixes has exactly four named checks over a
contract that does not exist yet (grounded elements, citation roles, recommendation provenance,
limitation-set comparison), a one-correction allowance, and failed-execution-on-persistent-failure.
Here a failure routes to `escalate` - a terminal status the design does not have. Tests asserting
this routing are misaligned with it (section 5).

### 6.4 Evidence admission and the ledger (`data-and-evidence.md` §§4-7)

**PARTIAL.** Genuinely aligned behavior exists at the state layer: evidence keyed by content hash
with first-seen-wins merge so contradictory observations survive (NFR-6), an accumulated
tool-operation trail separate from cited evidence (`observation_trail` +
`produced_refs`, the §5 history-vs-evidence split), and stable typed evidence references (the frozen
ref grammar). Missing: the admission step itself (§6) - nothing decides whether a normalized result
becomes evidence, assigns references at admission, or records first-class limitations; the two-axis
outcome vocabulary (section 8); admitted-evidence element structure (§7's table); and `succeeded+empty` as
an admitted positive observation (an empty tool result is currently just an empty list).

### 6.5 Retrieval (`system-design.md` §8.3; `decisions.md` D-003)

**PARTIAL, with misaligned members.** Aligned with D-003: section-level chunking per document
heading, dense + lexical retrieval fused with reciprocal rank fusion, metadata filtering by
kind/service, and a lexical-only backend that maps to the lexical baseline. Misaligned: hits return
`doc_id`/`title`/`score` only - the matched passage itself never reaches reasoning, which
`data-and-evidence.md` §9 rules inadmissible ("an agent cannot reason over a pointer"); embeddings
are local sentence-transformers rather than the Azure OpenAI embedding deployment
(`runtime-and-deployment.md` §9); collection storage is in-process over files rather than the categorized Cosmos `knowledge` container (`runtime-and-deployment.md` §§10-11); and the cross-encoder reranker
(`retrieval/reranker.py`, `rerank` mode) is a model reranker where D-003 settled deterministic identifier and relevant-metadata promotion after fusion, followed by passage-budget truncation (section 8).

### 6.6 Structured-query path (`system-design.md` §8.2; `runtime-and-deployment.md` §11)

**MISSING.** No governed natural-language-to-structured-query capability, no approved schema
context, no query structure, no deterministic validation before execution, no operational-records
container. Nothing in the repository approximates FR-95 to FR-102.

### 6.7 Protocol boundary (`system-design.md` §8.3; `decisions.md` D-004)

**PARTIAL / MISALIGNED.** The parity architecture is right and demonstrated: `mcp/server.py` fronts
the same `ToolService.call()` with the same validation and sanitized errors, and `test_mcp_parity`
asserts equivalence of status, results, and evidence refs across both paths - the design's
"transport, not a second implementation." Misaligned with D-004: three capabilities are exposed
(`get_incident`, `query_logs`, `search_runbooks`) where the design settles exactly one, and the one
it settles (deployment and change history) is not among them. Note for `decisions.md`: the code provides useful evidence for D-004's pending library questions: an in-process asyncio server, in-memory session transport, direct invocation of the same registered implementation, and unchanged envelope passthrough. The explicit library inspection and decision update are still required - reported here, not resolved.

### 6.8 Persistence (`runtime-and-deployment.md` §§3, 10)

**Rebuilt 2026-08-09; the obsolete containers are gone.** The original account could not gain the
`EnableNoSQLVectorSearch` capability, which Cosmos only accepts at account creation and which D-003's
dense-retrieval choice requires, verified by a probe that saw every container vector policy rejected.
The account was deleted and recreated under the same Bicep-derived name with the capability set. Its
contents were inspected first and were entirely rejected-architecture data: 1229 checkpointer
documents, one idempotency-index document, and eight job records carrying `pending_interrupt`,
`publication_id`, and `decisions`.

What exists now: a vector-capable Cosmos account declaring one container, `investigations`
(`/investigation_id`), written through keyless managed identity with scoped data-plane roles (the
identity/keyless posture matches §12's stored-data rule). `checkpoints` and `investigation-index`
are gone from both Bicep and the account. Removing the declarations alone would not have held,
because `cosmos_investigations.py` recreates its containers through create-if-not-exists, so the
`OPSPILOT_CHECKPOINTER` and `OPSPILOT_INVESTIGATION_REPOSITORY` deployment settings were removed
too and the application now takes its own defaults (`none` and `memory`). The hosted smoke's
durable-pause leg was removed in the same change: it asserted that an in-flight pause survives a
replica restart, which the accepted design does not claim.

**Corpus containers added 2026-08-09.** A second database, `retailease`, holds the two containers
the application reads and never writes: `knowledge` (partitioned by `/category`, vector policy
1536/cosine/diskANN, `/embedding` excluded from the normal index) and `operational-records`
(hierarchically partitioned by `/kind` then `/service`). Both are populated by
`scripts/prepare_corpus.py`, which runs as a setup principal rather than as the application.

The permission boundary is now the one the design requires, verified by inspection of the live role
assignments: the application identity holds data-contributor scoped to the `investigations`
container alone and data-reader scoped to the `retailease` database, and the setup principal holds
data-contributor on `retailease` plus the Cognitive Services OpenAI User role it needs to embed. An
account-wide data-contributor assignment left behind by the previous deployment was found and
deleted; Bicep could not reclaim it because narrowing a role assignment changes its generated name,
so the wide grant persisted alongside the narrow one rather than being replaced.

Still misaligned: the `investigations` container is declared but the application no longer writes
to it, since the repository defaults to memory until the completed-turn artifact exists.

The operational-records container acquired its first reader on 2026-08-11: the five operational
capabilities and the incident lookup behind predefined intake read it through
`data/operational_records.py`, and the file-backed repository is deleted. The knowledge container
still has none, since retrieval loads the knowledge corpus from files in the image. Half of corpus
preparation is therefore load-bearing and half is not, which is why "absent preparation is a
deployment-time failure" now holds for operational records and not yet for knowledge.

### 6.9 External interface and streaming (`runtime-and-deployment.md` §2)

**OBSOLETE + MISSING.** The implemented surface is the async job API (202 + poll + decision), the
synchronous `/investigate`, and the operator console - the removed interaction model, including
`awaiting_approval` and the decision endpoint. The designed surface - one streaming request owning a
turn, ordinary requests for normalization/follow-up/handoff/read, a cancellation signal - does not
exist. Health endpoints (`/health/live`, `/health/ready`, `/version`) have a design slot (NFR-19;
verification check 1) and are IMPLEMENTED, though readiness's checks will change with the runtime
around them.

### 6.10 Telemetry (`system-design.md` §10.3; `code-guidelines.md` §10)

**PARTIAL - the most reusable subsystem.** Emission happens once at shared primitives: a node
wrapper (`traced_node`), a tool-boundary span (`tools/errors.run_tool`), and a model wrapper
(`TracedChatModel`), all through one `span()` seam with contextvar-nested parents, correlation ids
on every span, error status reflection, and a swappable exporter with an in-memory test fixture  - 
exactly the §23/§10 emission-seam discipline. Missing: turn identity (no turn model exists),
MCP-operation spans, evidence-admission and grounding-result events, cost attribution, and a real
sink (App Insights); the exporter set is `none`/`memory`/`stdout`.

### 6.11 Evaluation (`evaluation.md`)

**MISALIGNED overall, with reusable parts.** What exists asserts the superseded design's semantics:
`scenario_eval.py` scores routing/groundedness/evidence-recall against numeric committed baselines,
and `test_scenario_gate` fails CI on regression - evaluation gating merge, which NFR-49 and
`evaluation.md` §2 prohibit; `config.EvalTargets` hard-codes numeric thresholds up front, which §19
prohibits before a measured baseline. No golden-scenario records of the designed shape, no
categorical scoring, no judge, no report. Reusable in place: the answer key + projection
(`data/answer_key/`, closure tests) is a real ground-truth discipline the golden-scenario model can
be authored from; retrieval precision/recall measurement exists; the deterministic planner + cycle
is behaviorally the fixed-script baseline (`evaluation.md` §14: same tools, predetermined order) even
though it currently lives as a runtime fallback tier rather than an evaluation baseline; and the
cassette/replay + fake-model machinery serves `code-guidelines.md` §11's models-replaceable-at-seams
obligation. The RCAEval wild-slice probe implements a capability `requirements.md` §12 explicitly
defers (held-out generalization probe) - see section 8.

### 6.12 Corpus preparation (`system-design.md` §8.4 "Corpus preparation")

**PARTIAL.** The authored corpus exists and is disciplined: seven authored incidents (inc-001 to
inc-007) with answer key, topology, generated telemetry that closure tests tie together, a KB with
runbooks/architecture/postmortems (the three logical knowledge categories, as file sets), and distractors as
corpus material (matching §8.3's "distractor content is corpus material, never a runtime
component"). Missing: the offline load/chunk/embed/index step into the categorized `knowledge` and `operational-records` Cosmos containers with a separate setup identity; provenance/metadata as the design's admission filters
need them; and the operational-records surface.

### 6.13 Infrastructure (`runtime-and-deployment.md` Part II)

**PARTIAL / MISALIGNED.** Aligned: one Container App from one Dockerfile via one Bicep template and one GitHub Actions workflow with post-deploy smoke; ACR; Log Analytics; Azure OpenAI account; Cosmos account; keyless managed identity throughout; scale-to-zero. The repository and live deployment currently allow 0-3 replicas, while the accepted target is 0-1. Other misaligned or obsolete elements include: the model surface is one `gpt-5-mini` chat deployment where the design requires a primary
+ a lower-cost + an embedding deployment (§9); Cosmos containers are the obsolete set (section 6.8); Entra
parameters provision the three-role reviewer machinery §12 does not have; the smoke suite
(`scripts/smoke_deployment.py`) drives the async/decision path and so asserts obsolete behavior; and
the deployed smoke checks do not match Part III's eight-check suite. `LLM_PROVIDER`
severity-tier/Claude routing in `config.py` contradicts D-002's two-deployment task-label routing
and names a different provider's models (section 8).

## 7. Component Reconciliation Matrix

Classifications per the required system: Keep, Keep with changes, Replace, Delete, Missing, Verify.

| Path / component | Current responsibility | Target responsibility | Class | Evidence and required action | Design ref | Plan slice |
| --- | --- | --- | --- | --- | --- | --- |
| `src/opspilot/dispatch.py`, `worker.py`, lease/epoch fields in `investigations.py`, Service Bus config keys | Outbox, queue seam, dispatch worker (WIP, broken: `epoch` kwarg TypeError at `api.py:862/866`; no dependency, no infra, no tests) | None: queues/workers/dispatch are deliberate absences | Delete | Abandon the unpushed WIP commit; delete the modules and config keys | runtime "Azure Services" deliberate absences; architecture trade-offs | S-0 |
| `src/opspilot/api.py` async job surface (`POST /investigations`, `GET /investigations/{id}` polling, `POST .../decision`, `_advance`, `_dispatch_or_run`, background tasks) | 202-accept, poll, HITL decision resume | One streaming request owns one turn; ordinary requests for follow-up/handoff/read; cancel signal | Replace | The transport contract itself conflicts (no reattach/poll model; no decision endpoint exists in the target) | workflow "Turn Model"; runtime "Turn Execution and Activity Streaming" | S-1/S-4 |
| `src/opspilot/graph.py`, `nodes/investigation.py`, `router.py`, `checkpoint.py` | LangGraph StateGraph, 12 nodes incl. `hitl_gate` (real `interrupt()`), `apply_edit`, `postmortem`; Memory/Sqlite/Cosmos checkpointers | Explicit in-process 5-stage state machine, no framework, no checkpointing, no approval stage | Replace / Delete | D-001 explicitly rejects a graph runtime and checkpoint/replay; `hitl_gate` and `apply_edit` realize a forbidden review stage; node logic (ingest normalization, evidence gathering, synthesis call) is salvage material for the new stages | D-001; workflow "Investigation Stages"; system-design constraint "No review, approval..." | S-1/S-4 |
| `src/opspilot/investigations.py`, `cosmos_investigations.py`, `repository.py`, `investigation-index` container | Async job records, decision protocol, publication sink, idempotency index, ETag CAS | Investigation Record: completed-turn artifacts only, Supervisor sole writer, created by first completed-turn commit, no index container | Replace | Job-lifecycle records (`queued`/`running`/`awaiting_approval`...) have no target counterpart; the ETag CAS and publish-idempotency techniques are reusable for the completed-turn commit | system-design "Investigation Record and Persistence Responsibilities"; data-and-evidence "Completed-Turn Artifact" | S-7 |
| `src/opspilot/contracts.py`, `state.py`, `diagnosis/contracts.py` | `IncidentReport`, 4-variant result union, singular `CausalClaim`, unused `EvidenceCitation.role` and `Acknowledgement` | Assessment with grounded elements, established/possible markers, 3 support labels, 3 citation roles, recommendations with 3 provenance categories, complete/partial/inconclusive | Replace | Vocabularies are incompatible (no `knowledge_briefing`/`escalation` outcomes; no candidate set; no support labels); the frozen-report + content-hash technique is reusable | data-and-evidence "Candidate Assessment", "Claims, Citations, and Grounding" | S-2/S-3 |
| `src/opspilot/guardrails/policies.py`, `diagnosis/admission.py` | 2 policies (read-only allowlist, citation-in-produced-refs) + claim admission | Evidence admission (two-axis vocabulary) at the Evidence Access Layer; four-check grounding gate in the Supervisor | Keep with changes | The produced-refs discipline and admit-or-refuse pattern map directly onto the target admission and gate; must be re-cut into the 4 named checks + shared correction allowance | data-and-evidence "Evidence Admission", "The four grounding checks" | S-2/S-3 |
| `src/opspilot/tools/` (8 tools, `service.py`, `errors.py`, `contracts.py`) | Read-only tools, static dict registry, uniform `ToolResult` envelope, sanitized errors, spans | Evidence Access Layer operational capabilities + dispatch validation + normalization | Keep with changes | Closest match in the repo; needs the two-axis execution-outcome/completeness vocabulary (currently `ok`/`error`), evidence admission split, and registry/`READ_ONLY_TOOLS` duplication collapsed | system-design "Evidence Access Layer Design"; data-and-evidence "Capability Request and Result Semantics" | S-2/S-5 |
| `src/opspilot/retrieval/` | BM25 runtime backend; dense (sentence-transformers) + RRF eval path; CrossEncoder reranker unreachable (factory maps `rerank` to hybrid, `adapters.py`) | Azure OpenAI embeddings + Cosmos vector search + in-process lexical scoring + RRF + deterministic identifier/metadata promotion + passage budget | Replace (keep RRF and lexical pieces) | D-003 specifies Azure OpenAI embeddings and Cosmos vector search; no model reranker; the local HF embedding stack and CrossEncoder go; `rank_bm25` fits the "small in-process BM25-style scorer" | D-003; runtime "Retrieval and Structured-Query Realization" | S-8 |
| `src/opspilot/mcp/server.py` | Stdio MCP server, 3 exposed tools, same `ToolService`, byte-identical results | One capability (deployment and change history) via in-process MCP, same implementation, parity tested | Keep with changes | Parity-by-delegation is exactly right; exposed capability set changes to D-004's single capability; hosting is pending library inspection | D-004; system-design "Knowledge retrieval and protocol transport" | S-10 |
| `src/opspilot/llm/` (client, prompts, cassette, manifest, fake) | Provider factory, reasoning-model handling, versioned prompt registry, cassette replay with drift detection | Model-access seam with task labels and routing; prompts behind the seam | Keep with changes | Add task-label routing to two deployments (D-002); prompt set will be rewritten for the three agents; cassette/replay is a legitimate test aid | system-design "Shared Model and Telemetry Seams"; D-002 | S-2/S-5 |
| `src/opspilot/triage.py`, `composition.py`, `diagnosis/planner.py`, `llm_planner.py`, `sufficiency.py`, `cycle.py`, `observe.py`, `render.py` | Deterministic vs single-agent selection; planner/triager; severity-scaled sufficiency | Three-agent split; Supervisor authorization conditions; Analyst synthesis; deterministic rendering projection | Replace (harvest logic) | Planner batching, dedup-against-answered, observation summarizers, and render-from-structure are reusable inside the new roles; `KNOWN_IMPLEMENTATIONS` twin definitions and the deterministic/LLM dual implementation dissolve (the fixed-script baseline replaces the deterministic floor, as an evidence plan in fixtures) | architecture "Trust and Authority Boundaries"; evaluation "Fixed-Script Baseline" | S-5 |
| `src/opspilot/auth.py` + 3 app roles | Hand-rolled Entra JWT validation (RS256, `idtyp` fail-closed), Submitter/Reader/Approver roles | Container Apps built-in authentication, one app registration, no role machinery | Replace with simpler | Delete the Approver and role-authorization surface with the HITL/decision API in S-4; retain only a minimal caller-identity seam until A-1 verifies and enables Container Apps built-in authentication | runtime "Identity, Secrets, and Network Posture" | S-4/A-1 |
| `src/opspilot/static/console.html` | 870-line polling console with PKCE sign-in and approve/edit/reject UI | One screen: intake/follow-up control, compact activity feed, dominant brief, one expandable details area; reads the streaming body | Replace | Polling + decision UI realize the old contract; the same-origin, no-build-step, single-file approach is right and carries over | system-design "Activity projection"; requirements 7.7 | S-1/S-4 |
| `src/opspilot/obs/tracing.py` | Hand-rolled spans, 3 seams instrumented; `configure_exporter()` never called (inert) | Telemetry seam feeding App Insights; activity projection produced at the same instrumentation points | Keep with changes | Wire the exporter at startup, add App Insights export, derive activity events from the same span facts | system-design 10.3/10.4; runtime "Observability" | S-1/A-1 |
| `src/opspilot/config.py` | Env constants incl. dead severity-tier routing (`PROD_MODELS`, `resolve_tier`, `JUDGE_MODEL` unused), unenforced `MAX_TOOL_CALLS`/`CONFIDENCE_THRESHOLD`, dispatch knobs | Configuration for the six bound mechanisms, deployments, containers, capabilities | Keep with changes | Delete dead tables and dispatch keys; add the six bounds and two-deployment routing | runtime "Configuration" | S-3/S-5 |
| ~~`src/opspilot/data/repository.py`~~ + `data/synthetic/` loaders | JSON corpus loader, closure-validated | Corpus preparation is an offline setup task; operational records move to Cosmos; local fixture mode remains for tests | Done (2026-08-11) | `data/repository.py` is deleted and the image no longer ships the operational corpus. `data/synthetic/` survives as the seed script's input, and `scripts/prepare_corpus.py` shapes it into container documents for the fixture the tests read | system-design "Corpus preparation, which no component owns" | S-8/S-9/S-11 |
| `data/answer_key/`, `data/kb/`, `data/distractors/`, `data/synthetic/` | 7 scenarios, closure-verified refs, KB with recurrence signatures, distractors | Same role, plus five-class coverage and demonstration suitability | Keep with changes | Real quality defects to repair (section 11); READMEs stale ("Six scenarios") | evaluation "Scenario Corpus and Coverage Audit"; D-006 | S-8/S-11 |
| `eval/` evaluators + baselines + cassettes | Scorecard metrics (13 numeric), recorded self-baselines, wild RCAEval probe, stub harness | Four layers, categorical judge, lexical + fixed-script baselines, aggregation of tests/smoke | Replace (keep recording/replay technique) | Metric vocabulary and baseline concept differ; `wild.py`/RCAEval probe is a deferred capability in requirements section 12 (held-out probe) and should be parked; judge missing entirely | evaluation (all); D-005 | S-12 |
| `infra/main.bicep` | Old deployed-resource composition: Log Analytics without Application Insights, wrong Cosmos containers, one chat deployment, and 0-3 replicas | Accepted six-service composition including Application Insights; 3 target containers; 3 OpenAI deployments; 0-1 replicas | Keep with changes | Solid OIDC/keyless skeleton; container and deployment set changes; `checkpoints`/`investigation-index` removed after migration | runtime "Azure Services", "Cosmos Layout and Access", "Model Connectivity" | S-7/S-8/A-1 |
| `.github/workflows/deploy.yml` | Lint/type/test lanes, ACR build, Bicep deploy, smoke | Same shape; tests reflect new suite; advisory eval signal; smoke reduced to target checks | Keep with changes | OIDC, vars-only secrets posture is right | runtime "Build and Deployment" | Across slices |
| `scripts/smoke_deployment.py` | Hosted smoke incl. HITL durability via revision restart, decision approval | Eight environment-dependent checks (start, auth, model, Cosmos roles, one streamed turn, citations after restart, telemetry, Bicep repeatability) | Replace | Most of its assertions target deleted behavior (awaiting_approval, decision, report-hash stability across restart) | runtime "Verification Suite" | S-4/A-1 |
| `README.md`, `.env.example`, `out.txt`, `raw.txt`, `infra/.gitkeep`, `data/.gitkeep`, stale remote branches | Stale/stray | Accurate minimal repo docs | Delete / Replace | README is 5 stages stale and self-contradicting; stray files are third-party slide dumps | - | S-0 |
| Untracked `docs/` and `.githooks/` | The authoritative documentation set and the pre-commit hook exist only locally | Committed with the repository | Keep (commit them) | Bicep and smoke comments cite ADRs that are not in the repo | - | S-0 |

## 8. Deletion and Replacement Register

### 8.1 Delete

| Component | Currently does | Why it has no place | Dependencies affected | Replacement | Risk / verification before deletion |
| --- | --- | --- | --- | --- | --- |
| WIP commit `0c3c175` (`dispatch.py` 349 ln, `worker.py` 183 ln, lease/epoch machinery, Service Bus config) | Outbox + queue seam + worker skeleton | Queues, workers, and durable dispatch are deliberate absences; the code is also broken (mypy `call-arg` at `api.py:862/866`) and has zero tests, zero deps, zero infra | None outside itself (unpushed, untested) | None | Deleted: `git merge-base --is-ancestor 0c3c175 HEAD` exits nonzero on `main` (PR #54, squash commit `4c8f706`); the code was never present on the branch cut from `main` at `e567adf` |
| HITL surface: `hitl_gate`, `apply_edit` nodes, `POST /investigations/{id}/decision`, `CommittedDecision`, decision idempotency, console approval UI, `Approver` role usage | Human approval pause/resume with report-hash binding | The accepted design has no approval, review, or publication stage; delivery follows the gate and commit directly | `test_investigations_api.py` (37 tests), `test_report_binding.py`, `test_checkpointer.py` HITL test, smoke steps 4-6 | The grounding gate + commit-before-terminal (different concept, already specified) | Delete together with its tests; keep the report-hash/content-hash technique for the completed-turn artifact |
| Checkpointer stack: `checkpoint.py`, `langgraph-checkpoint-sqlite` dep, `checkpoints` Cosmos container (Bicep + live), msgpack allowlist | Per-super-step durable graph state | In-flight state is ephemeral by design (NFR-57); D-001 forbids checkpoint/replay features | `test_checkpointer.py`, Bicep container loop, `sqlite-vec` transitive | Nothing (completed-turn commit only) | **Container deleted 2026-08-09** (Bicep + live), with the `OPSPILOT_CHECKPOINTER` deployment setting and the hosted smoke's durable-pause leg. Code half (`checkpoint.py`, the dependency, msgpack allowlist, `test_checkpointer.py`) still pending |
| `investigation-index` container + versioned idempotency key machinery | Atomic accept-once index | Target creates the investigation at first completed-turn commit; no accept-time persistence, no index container | `cosmos_investigations.py`, Bicep | None | **Container deleted 2026-08-09** (Bicep + live), with the `OPSPILOT_INVESTIGATION_REPOSITORY` deployment setting that caused it to be recreated at runtime. Idempotency-index code still pending |
| Async job status vocabulary (`queued`/`running`/`awaiting_approval`/`degraded`/`escalated`...) and 202+poll transport | Job lifecycle over background tasks | One live streaming request owns the turn; live status is the 5-value stream vocabulary; completed outcomes are exactly three | `api.py`, console, smoke | Streaming turn endpoint + live statuses | Remove only after the streaming slice is demonstrable |
| Unreachable model reranker: `retrieval/reranker.py`, `Retriever.rerank()`, `RERANK_CANDIDATES`, `reranker` test marker, `bge-reranker` references | CrossEncoder reranking (never reachable via factory) | No model reranker in the baseline (D-003); currently dead by construction anyway | `test_retrieval.py` reranker tests, `retrieval_scorecard.json` rerank mode | Deterministic identifier/metadata promotion | None |
| Dead config: `PROD_MODELS`, `Tier`, `SEVERITY_TIER`, `resolve_tier`, `ENABLE_OPUS_SEV1`, `JUDGE_MODEL` (as-is), `MAX_TOOL_CALLS`, `CONFIDENCE_THRESHOLD`, `LANGSMITH_ENABLED`, dispatch knobs | Unreferenced severity-tier model routing and unenforced limits | Never called; contradicts D-002 (routing is by task label to two deployments, not severity tiers) | None (unreferenced) | D-002 task-label routing | None |
| **Deleted (2026-08-09).** `eval/wild.py`, `record_wild.py`, `wild_scorecard.json`, `wild_single_agent.json` cassette (manifest-less, unreplayable), `tests/fixtures/wild_ob/`, RCAEval profile dependence | Held-out RCAEval generalization probe | Requirements section 12 defers the held-out probe; the cassette is unreplayable by the repo's own drift rules | `test_wild.py`, deleted with it | Golden scenario records (`data/answer_key/golden_scenarios.yaml`), the evaluation input surface that replaces it | Deleted rather than archived: the recorded numbers scored a deferred capability against a corpus the golden records replace, so preserving them would preserve a comparison nothing may draw. `data/profiles/rcaeval_profile.json` is NOT deleted, see the profile-calibration row below |
| `postmortem` node output path | Returns a resolution dict never stored | Cross-thread memory store is a deferred capability; dead output | None | None | None |
| Stray/stale: `out.txt`, `raw.txt`, `infra/.gitkeep`, `data/.gitkeep`, `tests/__pycache__/_scratch_proposed...pyc`, stale remote branches (`add-operator-console`, `stage-5e-*`, `add-durable-checkpointer`, `add-cross-encoder-reranker`, `add-ci-test-gate`, `stage-5f-decision-protocol`) | Debris | Third-party slide dumps and merged-branch leftovers | None | None | Confirm branches are merged before remote deletion |
| Live orphan: `rytesting` (Microsoft.CognitiveServices/accounts, kind AIServices) + `rytesting/proj-default` in `rg-opspilot` | Manual AI Foundry experiment | Not declared in Bicep, unrelated to OpsPilot | None | None | Deleted: user confirmed 2026-08-08; `az resource delete` removed the nested `.../accounts/rytesting/projects/proj-default`, then `az cognitiveservices account delete -g rg-opspilot -n rytesting` removed the account. `az cognitiveservices account show` now returns `ResourceNotFound`; `az cognitiveservices account list-deleted` shows it soft-deleted (recoverable), not yet purged |

### 8.2 Replace

| Component | Required purpose | Why not preserved | Simplest replacement direction | Migration/test notes |
| --- | --- | --- | --- | --- |
| LangGraph orchestration (`graph.py` + nodes + routers) | Turn execution over five stages with one back-edge | D-001: explicit in-process state machine, no graph runtime; the graph also encodes forbidden stages (hitl, apply_edit) | Plain functions per stage driven by a small turn controller inside the Supervisor; salvage ingest/gather/synthesize logic | Stage transitions get direct deterministic tests (D-001 accepted trade-off) |
| Result/report contracts | Assessment, brief, citations, recommendations, limitations | Vocabulary incompatible with grounded-element model | New typed contracts per data-and-evidence sections 12 to 17; content-hash idea retained | Rendering-fidelity test from code-guidelines |
| `api.py` transport + console | Streaming turn, ordinary follow-up/handoff/read, cancel | Polling + decision protocol conflict with one-request-owns-one-turn | One streaming endpoint emitting identities first, activity events, terminal after commit; console rewritten around feed + brief | Preserve same-origin PKCE-less simplicity if built-in auth replaces the token dance |
| Auth machinery | Smallest credible caller authentication | Target names Container Apps built-in auth with no role machinery; repo hand-rolls JWT + three roles for endpoints that disappear | Built-in auth at the ingress; app trusts the platform header; local dev bypass documented | `pyjwt` likely removable; auth tests shrink drastically |
| Evaluation suite | Four layers, categorical results, two baselines, judge | Numeric scorecard vocabulary and self-recorded baselines do not match the accepted model; no judge exists | Golden records per accepted 8-field model; judge on primary deployment; fixed-script evidence plans as fixtures; keep cassette replay for change-time determinism | D-006 selections have natural candidates (section 11) |
| Hosted smoke | Eight environment-dependent checks | Current script asserts the approval protocol and job polling | New script asserting the eight checks; keep the model-import trick and az-CLI restart for the citations-resolve-after-restart check | Runs only after streaming + persistence slices |


### 8.3 Additional classifications from the file-level audit

#### 8.3.1 Misaligned implementations

| Behavior | Current location | Accepted realization |
| --- | --- | --- |
| One planner gathers and concludes | `diagnosis/llm_planner.py`, `composition.py` | Evidence Investigator gathers; RCA Analyst is sole completed-turn synthesis authority |
| Numeric confidence | `diagnosis/contracts.py`, `contracts.py`, `config.py` | Leading, Plausible, and Weakly supported qualitative labels only |
| Severity-scaled sufficiency stop rule | `diagnosis/sufficiency.py`, `router.py` | Investigator proposes continuation; Supervisor authorizes against computable conditions |
| One-check safety gate routing to escalation | `nodes/investigation.py`, `guardrails/policies.py`, `router.py` | Exactly four deterministic checks, one correction allowance, failed execution after persistent failure |
| Retrieval returns pointers without passages | `retrieval/base.py`, `tools/contracts.py`, `tools/search.py` | The matched passage reaches reasoning with provenance |
| CrossEncoder model reranker | `retrieval/reranker.py`, rerank mode and config | RRF, deterministic identifier and metadata promotion, then passage-budget truncation |
| Local sentence-transformers embeddings | `retrieval/embeddings.py`, config | Azure OpenAI embedding deployment, subject to the D-003 viability check |
| MCP exposes three wrong capabilities | `mcp/server.py` | One deployment-and-change-history capability over the same implementation |
| Numeric evaluation ratchets gate CI | `test_scenario_gate.py`, `test_single_agent_gate.py`, old baselines | Offline advisory evaluation with categorical outcomes and measured baselines |
| Old intent taxonomy and known-issue fast path | `triage.py`, graph router, triage prompt | Request-shape interaction kind; history informs but does not short-circuit synthesis |
| Hand-rolled three-role authorization | `auth.py`, API dependencies, console | Remove approval roles with HITL; later use Container Apps built-in authentication |

#### 8.3.2 No accepted slot or explicitly deferred

| Component | Location | Disposition |
| --- | --- | --- |
| RCAEval wild generalization probe | `eval/wild.py`, recorder, fixtures, baseline, profile dependency | Deleted 2026-08-09, with `test_wild.py`. The golden scenario records are the evaluation input surface that replaces it |
| Generic evaluator registry scaffold | `eval/harness.py`, scaffold test | Replace with the concrete four-layer evaluation |
| External ITSM/RCAEval profile-calibration pipeline | `data/profiles/` scripts and external caches | Verified 2026-08-09: `data/profiles/rcaeval_profile.json` IS still a generated-corpus input. `data/synthetic/generate.py` reads it to calibrate noise density, so it is retained, not archived. Only the probe that consumed the held-out raw dataset was deleted; the committed calibration constants the generator depends on are a different artifact and stay. The gitignored raw caches remain absent and are needed only to regenerate the profile |
| Empty package placeholders | `src/opspilot/ops/`, `src/opspilot/eval/` | Deleted (PR #54, merged to `main`; no owner appeared) |
| Deprecated `/health` alias | `api.py` | Delete when probes and docs use the accepted health routes |
| Local transformer vector-index stack | `retrieval/index.py`, local embedding path | Remove with the rejected local embedding and reranker implementation unless D-003 is explicitly revised |

#### 8.3.3 Out-of-scope wrappers around otherwise valid concepts

| Wrapper | Current location | Keep only |
| --- | --- | --- |
| Per-user and role-based concurrency admission | API, repositories, config | One small configured concurrency limit |
| Lease and fencing protocol for multi-replica workers | repositories and worker | Nothing for active turns; one request and one replica own the turn |
| Job-idempotency index and workflow-version salt | API and `investigation-index` | Completed-turn commit behavior only |
| Multi-replica transition machinery | Cosmos repository retry and lease paths | Any minimal retry required by a single-writer completed-turn repository, proven by tests |
| Publication identity and approval-bound report hash | state, finalization, repositories | At most an internal integrity technique if it does not create publication/version semantics |

#### 8.3.4 Duplicated logic to collapse

| Behavior | Occurrences | Target owner |
| --- | --- | --- |
| Citation grounding | `guardrails/policies.py` and `diagnosis/admission.py` | One Supervisor grounding gate over the accepted assessment |
| Runtime implementation selection | `composition.py` and evaluation scripts | One composition root; fixed script exists only as an evaluation plan |
| Embedding/reranker model names | config and evaluation code | One task/config owner, with the model reranker removed |

## 9. Required-Capability Status Summary

Legend: Impl = implementation exists; Align = aligns with accepted design; Test = deterministic
test exists; Demo = demonstrable today.

| Capability | Impl | Align | Test | Demo | Notes |
| --- | --- | --- | --- | --- | --- |
| Three-agent workflow | No (2 model roles: planner, triager) | No | - | No | Missing Supervisor/Investigator/Analyst split and mediation |
| Six logical boundaries | Partial | No | - | No | EAL-like tools layer exists; no Interaction Interface/Record per target semantics |
| Intake (predefined + free text + one clarification) | Partial | Partial | Partial | Partial | Alert-payload intake exists; no free-text normalization task, no clarification |
| Basic brief generation | Yes (report + hypothesis + citations) | No (contract differs) | Yes | Yes (old shape) | `synthesize_report` + render |
| Evidence access (read-only capabilities) | Yes (8 tools) | Mostly | Yes | Yes | Needs two-axis result vocabulary and admission split |
| Model-directed capability use | Yes (LLM planner batches tool calls) | Partial | Yes | Yes | Adaptive selection is real; continuation lacks proposal/authorization split |
| Retrieval (semantic+lexical+RRF) | Partial | No | Partial | Partial | Runtime is BM25-only; dense+RRF is eval-only; D-003 stack (Azure embeddings + Cosmos vectors) absent |
| Deterministic reranking | No (truncation + recency bonus; CrossEncoder unreachable) | No | No (excluded markers) | No | Identifier/metadata promotion missing |
| Retrieval influence | No recorded relationship | No | No | No | Informing-knowledge field absent |
| Structured query (governed) | No | - | No | No | Nothing exists; corpus tables ready |
| MCP | Yes (stdio, 3 tools, parity) | Partial | Yes (4 tests) | Yes | Capability set and hosting to match D-004 |
| Grounding (4 checks) | Partial (2 citation policies + admission) | No | Partial | Partial | No provenance-presence or limitation-disclosure checks; no correction allowance (no retries at all) |
| Further-evidence cycle | No (planner loops internally; `request_more_evidence` escalates to a human) | No | No | No | inc-004 is a natural demonstration candidate |
| Follow-up answers | No | - | No | No | |
| Handoff | No | - | No | No | |
| Cancellation | No | - | No | No | |
| Activity streaming | Yes (predefined intake only) | Yes | Yes | Yes | `POST /turns`: identities first, activity from the same telemetry facts, close marker last; stub assessment only, no accepted outcome yet |
| Completed-turn persistence | Partial (terminal publish exists) | No (job records, per-step checkpoints, index container) | Partial (in-memory only; `cosmos_investigations.py` 447 ln untested) | Partial | Commit-before-terminal idea present at the publish sink |
| Model routing | No (one deployment, one model for everything) | No | No | No | Severity-tier table is dead code; D-002 needs a second deployment |
| Offline evaluation | Partial (scorecards, gates) | No (vocabulary, baselines, no judge) | Partial | Partial | Retrieval rerank numbers never re-verified in CI |
| Azure deployment | Yes (live, green at `main`) | Partial | Smoke (old contract) | Yes (old system) | The deployed old-system footprint is operational but does not match the accepted six-service composition: Application Insights is missing, the Cosmos containers are wrong, and replicas are 0-3 rather than 0-1 |

## 10. Detailed Missing and Partial Implementation Register

This register records what must be added or completed. It does not sequence work. The vertical plan
owns order and PR structure.

### 10.1 Engineer Interaction Interface

| Required behavior | Current standing |
| --- | --- |
| One same-origin screen for intake, follow-up, activity, brief, and details | Partial. `/investigation` exists: predefined intake, activity feed, brief region, one expandable details area. No follow-up control; the old console is unaffected and stays reachable until cutover |
| Predefined and free-text intake normalization | Partial. Predefined intake is normalized through the accepted contract (`decisions.md` D-007) and wired live; free-text normalization does not exist |
| At most one clarification | Missing |
| Request-shape classification of follow-up, redirect, supplied context, handoff, and read | Partial. The five-kind type (`InteractionKind`) exists; the classifier itself is not implemented |
| Compact safe activity projection | Implemented. Exact `system-design.md` §10.4 field set, produced at the same instrumentation point as telemetry, tested for fidelity and sanitization |
| Deterministic handoff rendering | Missing |

### 10.2 Supervisor

| Required behavior | Current standing |
| --- | --- |
| Own the turn objective | Missing |
| Separate deterministic control from model judgments | Missing as an explicit code seam |
| Authorize continuation against computable conditions | Missing; replaced today by sufficiency routing |
| Enforce the six bound mechanisms | Partial config exists, but it is not the accepted set and is not consistently enforced |
| Own the shared correction allowance and terminal shape | Missing |
| Commit completed turns before successful terminal delivery | Missing as the accepted artifact flow |
| Answer follow-ups from retained state with deterministic validation | Missing |

### 10.3 Evidence Investigator

| Required behavior | Current standing |
| --- | --- |
| A distinct investigator role | Missing. Planner and synthesizer are fused |
| Observation-driven capability selection | Partial and genuinely reusable in `LLMPlanner.plan` |
| Question/action/reason proposal contract | Missing |
| Supervisor authorization before continuation | Missing |
| Optional informing-knowledge references | Missing |
| Parallel independent evidence actions inside one authorized cycle | Missing as the accepted behavior |

### 10.4 Evidence Access Layer and admission

| Required behavior | Current standing |
| --- | --- |
| Closed static capability registry | Implemented and reusable |
| Read-only operational capabilities | Implemented and well tested |
| Two-axis result vocabulary | Implemented. Five execution outcomes and four completeness values in `tools/contracts.py`, with the legal-pairing table enforced on construction |
| Deterministic evidence admission | Implemented. `evidence/admission.py` is the only door into the evidence set and assigns the reference |
| Stable admitted-evidence and limitation structures | Implemented. Admitted observations carry identity, provenance, and completeness; limitations name the unanswered question. The operation ledger is kept separate |
| `succeeded + empty` represented as a positive observation | Implemented. Admitted with a deterministic representation naming the queried scope and the absence, and assigned an `absence:<capability>:<operation_ref>` evidence reference (D-008) so the finding is citable |
| Governed structured-query capability | Missing |

### 10.5 RCA Analyst and assessment

| Required behavior | Current standing |
| --- | --- |
| Distinct RCA Analyst as sole synthesis authority | Missing |
| Candidate cause set | Implemented. One bounded `rca_synthesis` call proposes candidates and `assessment/synthesis.py` admits them against the admitted evidence set |
| Qualitative support labels | Contract implemented: leading, plausible, weakly supported, with no numeric field anywhere in the assessment. The legacy numeric confidence still exists on the old report and dies with it |
| Supporting and weakening evidence per candidate | Contract implemented, with knowledge references refused in both roles |
| Established and possible grounded elements | Contract implemented; an alternative and a historical comparison cannot be constructed as established |
| Recommendation horizons and provenance categories | Contract implemented, with provenance and its knowledge reference checked together in both directions |
| Recorded limitations | Implemented. `Assessment.limitations` carries both kinds and the brief renders them: an operation that did not answer, and the incompleteness of a `partial` observation an element rests on. The execution outcome distinguishes them, so a source that answered in part stays separable from one that did not answer |
| Further-evidence need and its one bounded cycle | Missing |
| Deterministic brief projection | Implemented. `assessment/brief.py` projects the admitted assessment by traversal alone. Proven end to end by replaying `eval/cassettes/turn_synthesis.json` (inc-005, recorded against `gpt-5-mini`, the deployed model), where every reference the brief carries was one admission assigned |

### 10.6 Grounding and outcomes

| Required behavior | Current standing |
| --- | --- |
| Citation resolution and role/type pairing | Partial. `evidence/references.py` owns the one parser, resolver, and prefix-to-type map, so role compatibility is decidable from the reference type; the gate that applies it does not exist |
| Operational support for established grounded elements | Missing |
| Recommendation-provenance presence | Missing |
| Limitation disclosure | Missing |
| One shared correction allowance | Missing |
| Exactly complete, partial, inconclusive completed outcomes | Missing; old result/status vocabulary conflicts |
| Failed execution outside completed outcomes | Missing |
| No artifact after persistent grounding failure | Missing |

### 10.7 Turn lifecycle, cancellation, follow-up, and handoff

| Required behavior | Current standing |
| --- | --- |
| One live streaming request owns a turn | Missing |
| Explicit in-process state machine | Missing; LangGraph runtime must be replaced |
| One possible further-evidence cycle | Missing as the accepted back-edge |
| Safe-boundary cancellation | Missing |
| Early no-evidence cancellation: inconclusive, no assessment, no brief | Missing |
| Later cancellation with admitted evidence: honest partial or inconclusive result | Missing |
| Disconnect discards active state | Missing |
| Retained-state follow-up validation | Missing |
| Deterministic handoff with no model call | Missing |

### 10.8 Retrieval

| Required behavior | Current standing |
| --- | --- |
| Passage-bearing semantic retrieval | Partial primitives exist; runtime is BM25-only and hits omit passages |
| Lexical retrieval | Implemented and reusable |
| Reciprocal-rank fusion | Implemented in the evaluation-oriented hybrid path and reusable |
| Deterministic identifier and metadata promotion | Missing |
| Passage-budget truncation after promotion | Missing as the accepted pipeline |
| Categorized `knowledge` container | Implemented (2026-08-09). `retailease/knowledge`, partitioned by `/category`, vector policy 1536/cosine/diskANN with `/embedding` excluded from the normal index. Holds 196 passages from 28 documents |
| Azure OpenAI embeddings | Implemented. `text-embedding-3-small` deployment; corpus preparation embeds at load time. Retrieval does not read them yet |
| Retrieval influence captured in proposals and evaluation | Missing |
| Identifier extraction and category metadata at load time | Implemented. `scripts/prepare_corpus.py` extracts service names, error codes, and deployment identifiers deterministically, and carries the collection category, entity metadata, and a nullable date |

### 10.9 Governed structured query

| Required behavior | Current standing |
| --- | --- |
| Approved operational-records surface | Data files exist; container and capability do not |
| Canonical query structure with predicates, projection, and COUNT | Missing |
| Mandatory scope, result limit, and timeout | Missing |
| Decode or validation rejection before execution | Missing |
| Fixture-truth and rejection tests | Missing |
| No grouping, ordering, joins, writes, or non-count aggregates in baseline | No implementation exists, so the future contract must preserve this absence |

### 10.10 MCP

| Required behavior | Current standing |
| --- | --- |
| One real MCP boundary | Partial and promising |
| Same implementation and canonical result model as direct access | Implemented by delegation and tested |
| Only deployment-and-change-history exposed | Missing; current server exposes three different tools |
| Transport visible in activity and telemetry | Missing |
| D-004 library questions resolved before implementation cutover | Repository evidence answers much of the question, but the decision remains pending |

### 10.11 Investigation Record and persistence

| Required behavior | Current standing |
| --- | --- |
| Completed-turn artifact | Missing |
| Investigation Record port and its commit contract | Implemented over an in-memory backend. `record/port.py` fixes the commit success and failure contract and the commit-before-delivery ordering; a durable backend later replaces what sits behind the port, not the port |
| One `investigations` container for that artifact | Existing container stores the wrong job record |
| One categorized `knowledge` container | Implemented (2026-08-09), in the `retailease` database |
| One `operational-records` container | Implemented (2026-08-09), hierarchically partitioned by `/kind` then `/service`. Holds 14,013 records across six kinds |
| Commit before successful terminal delivery | Partial publication ancestor exists, but the accepted path is missing |
| Restart-safe citation resolution | Missing for the accepted artifact |
| No active-turn checkpoints, replay, index container, or worker state | Conflicting machinery currently exists and is deleted |

### 10.12 Telemetry and activity

| Required behavior | Current standing |
| --- | --- |
| Shared span seam | Implemented and reusable |
| Turn and agent identity | Partial. Turn identity (`turn/identity.py`) exists and is on every span (`obs/tracing.py` `standard_attributes`); agent identity does not exist, since no agents exist yet |
| Model task labels and usage totals | Partial model wrapper exists; accepted labels and totals are missing |
| MCP, evidence-admission, grounding, and persistence spans | Missing |
| Activity projection emitted from the same facts | Implemented, for the predefined-intake stub path (`stream/projection.py`) |
| Application Insights sink | Missing |
| No activity persistence or telemetry-query UI | Not currently implemented, which is aligned |

### 10.13 Evaluation

| Required behavior | Current standing |
| --- | --- |
| Golden scenario records of accepted shape | Implemented. `data/answer_key/golden_scenarios.yaml`, one eight-part record per authored incident, authored beside the answer key rather than generated from it; closure and shape asserted by `tests/test_golden_scenarios.py` |
| Deterministic conformance aggregation | Partial tests exist but ownership and contracts differ |
| Categorical scenario scoring | Missing |
| One judge with versioned rubric | Missing |
| Lexical-only baseline | Partial retrieval backend exists |
| Fixed-script evidence-plan baseline | Partial deterministic behavior exists but is wrongly a runtime fallback |
| Repeatability subset | Missing as accepted evaluation wiring |
| Retrieval-influence and further-evidence demonstrations | Scenarios selected (D-006, accepted 2026-08-09: retrieval influence inc-007, further evidence inc-004); the demonstrations themselves are unbuilt, since neither retrieval nor the further-evidence cycle exists yet |
| Advisory report rather than merge-gating numeric ratchet | Missing; current scorecards and gates conflict |

### 10.14 Corpus preparation

| Required behavior | Current standing |
| --- | --- |
| Seven authored incidents across five families | Implemented |
| Reference closure | Verified |
| Five-class evaluation coverage | Partial: multi-contributor absent; benign transient unscoreable |
| Credible chronology and mechanism-consistent telemetry | Fails for several incidents and must be repaired |
| No answer leakage | Fails in `inc-007` and deployment notes |
| Categorized knowledge metadata and embeddings | Implemented (2026-08-09). Category, provenance, extracted identifiers, entity metadata, nullable date, and a 1536-dimension embedding on every passage |
| Operational-records seed process | Implemented (2026-08-09). `scripts/prepare_corpus.py` seeds both containers idempotently by upsert and verifies by reading back what it wrote (`--verify-only`) |
| Absent preparation presents as a deployment-time failure | **Partial (2026-08-11).** Implemented for operational records: readiness counts every record kind in the container and reports not-ready when any is zero or the container cannot answer, so an unprepared or unreachable container fails the probe rather than answering turns with nothing. Still missing for knowledge, which has no reader: retrieval loads it from files in the image, so a readiness check on it would gate deployment on data no code consumes. The obligation for that half attaches to passage retrieval and is recorded in that slice |
| Controlled variants clearly distinct from authored incidents | Missing as formal fixtures |

### 10.15 Azure and deployment

| Required behavior | Current standing |
| --- | --- |
| One Container App, one image, zero-to-one replicas | One app and image exist; replica maximum is 3 |
| Static client served by same app | Implemented in old UI form |
| Primary, lower-cost, and embedding deployments | Only one chat deployment exists |
| Application Insights | Missing |
| Target three Cosmos containers | Old three-container set is deployed |
| Container Apps built-in authentication | Missing; hand-rolled role model exists |
| Eight hosted smoke checks | Missing; current smoke asserts old job and approval behavior |
| One OIDC workflow and Bicep | Implemented and reusable |

## 11. Data and Corpus Status

**Inventory:** authored answer key (7 scenarios, `data/answer_key/scenarios.yaml`), generated
telemetry (13,780 log rows of which 15 are signal, 175 metric series at 5-minute cadence over a
60-minute window, 16 alerts, 9 deploys, 7 incident tickets, 12 dependency edges), KB (6 runbooks +
3 architecture + 3 postmortems, all with frontmatter ids/kinds/services; postmortems carry
machine-checkable recurrence signatures), 16 same-domain distractors, 28 labeled retrieval queries,
calibration profiles, and 5.2 GB of gitignored third-party caches (RCAEval, ITSM).

**Reference closure:** verified programmatically by the inspection; all 42 evidence references and
all 22 retrieval references resolve. Identifier grammar is stable and uniform.

**Scenario coverage matrix** (families: saturation, dependency, deploy regression, cache, queue):

| Incident | Family | Expected outcome | Evidence (log/metric/deploy/edge) | Retrieval use | Retrieval-influence fit | Structured-query fit | MCP fit | Further-evidence fit | Degradation fit | Timestamps | Golden |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| inc-001 | saturation | complete | 2/2/1/1 | runbook | low | medium | medium | low | low | coherent | yes |
| inc-002 | saturation to dependency | complete | 2/2/1/1 | runbook | medium | medium | medium | high | medium | coherent, telemetry contradicts (RU flat at ~45% while throttling spikes) | yes |
| inc-003 | queue backlog | complete | 1/2/1/1 | runbook | medium | medium | medium | low | low | effect precedes cause (backlog 19:55 before crash loop 20:00); throughput flat contradicts "consumed nothing" | yes |
| inc-004 | external dependency with deploy red herring | complete (competing hypotheses) | 2/2/1/1 | rollback runbook | high | medium | high | **high (natural)** | high (`payment-gateway` has no metrics) | metrics coherent, logs inverted | yes |
| inc-005 | cache saturation | complete | 1/3/0/1 | runbook | low | low | low | low | **high (only no-deploy incident)** | best chain in corpus; hit_rate flat contradicts miss surge | yes |
| inc-006 | stale cache + causal deploy | complete | 2/1/1/1 | runbook | medium | medium | high (foil to inc-004) | medium | high (sparse: zero cache telemetry) | logs inverted | yes |
| inc-007 | queue backlog recurrence | complete (known issue) | 1/2/1/1 | **postmortem inc-003 with recurrence signature** | **high (strongest)** | high (version join) | **high (same-version redeploy)** | low | low | same defects as inc-003; log message leaks the answer | yes |
| (unlabeled) | benign transients (4 alerts + 4 logs, `incident_id: null`) | none scoreable | - | - | - | - | - | - | - | outside all windows | **no** |

**Five-class coverage audit (performed 2026-08-09).** The audit `evaluation.md` - "Scenario Corpus
and Coverage Audit" defines, asking its three questions per class and nothing more. One row per
class; the result is a finding from the corpus, not a design decision.

| Scenario class | Represented? | By which | Clear enough to evaluate against a golden scenario? |
| --- | --- | --- | --- |
| Clear single-cause | Yes | inc-001, inc-002, inc-003, inc-005, inc-007 | Yes. Each carries an unambiguous causal chain. Four of the five also carry a disqualifying signal ruling the neighbouring failure mode out; inc-005 instead has no deploy anywhere in its window, which rules out change regression by absence rather than by a flat reading |
| Competing or ambiguous hypotheses | Yes | inc-004 (primary), inc-006 (foil) | Yes. inc-004 carries an explicit authored `red_herring`; inc-006 is the inverse case, where the temporally adjacent deploy genuinely is contributory |
| Multiple contributing failures | Yes | inc-006 | Yes, since the 2026-08-08 repair. Two independently evidenced conditions (`metrics:inventory-api:reservation_queue_depth`, a concurrent capacity shortfall, and `metrics:redis-cache:stale_read_rate`, the stale-cache defect), neither sufficient alone |
| Sparse or unavailable evidence | Yes | inc-004 | Yes. `payment-gateway` is an external third party carrying zero metric series anywhere in the corpus, verified 2026-08-09, so the root cause is structurally unobservable and must be established indirectly and disclosed as a limitation |
| Benign or transient condition | Yes | `benign_fixture.yaml` (benign-01) | Yes. Four ambient sub-threshold events, structurally distinct from the seven scenarios (no `expected_evidence`, no `expected_match`, not counted by `load_scenarios()`) |

**Corpus gaps recorded by this audit:** none. Every class is represented and evaluable.

**Further-evidence scenario, which the audit must also identify:** inc-004, an authored scenario
rather than a fixture variant. Its unobservable third party is exactly what leaves a question the
first evidence pass cannot close, which is the condition the cycle exists to serve.

**One re-assessment this audit makes against the earlier pre-audit note.** The sparse-evidence class
was previously recorded as "accidental only (inc-006, inc-004)". Inspection on 2026-08-09 shows
inc-004's sparseness is structural rather than accidental: `payment-gateway` is an external
dependency the corpus deliberately never instruments (confirmed: no metric series exists for it),
so the class has a genuine representative rather than an incidental one. inc-006's sparseness was
the accidental kind and the 2026-08-08 repair removed it by adding the missing cache-side signal;
it is no longer offered as a representative of this class.

The benign fixture carries no golden record: it is a non-incident, so there is no correct
investigation for a golden record to describe. That exclusion is asserted by
`tests/test_golden_scenarios.py::test_one_golden_record_per_authored_incident`.

**Quality concerns:**

1. **Repaired (2026-08-08).** Physically contradictory telemetry, caused by the generator
   perturbing only the exact series in `expected_evidence`: inc-002 (`used_ru_pct` flat while
   throttling spikes and the postmortem narrates it climbing to 100%), inc-003/inc-007
   (`msg_processed_rate` steady while the postmortem says nothing is consumed), inc-005 (`hit_rate`
   flat during an eviction storm), inc-006 (zero cache-side deviation for a stale-cache cause). Each
   now has an `expected_evidence` reference (`used_ru_pct`, `msg_processed_rate` x2, `hit_rate`,
   `stale_read_rate`) so the generator deviates it; `tests/test_telemetry.py`'s deviation check is
   now direction-aware (drop-type metrics were previously inexpressible, not just untested) rather
   than assuming every reference rises.
2. **Repaired (2026-08-08).** Effect-precedes-cause orderings: inc-003 and inc-007 metric onsets
   (their `active_message_count` reference ts moved later so the ramp onset follows the causal log,
   not precedes it); inc-004 and inc-006 log orderings (`generate.py`'s `CAUSE_BEFORE_EFFECT` pass
   nudges the effect log's offset forward when the hash-based draw would otherwise invert it).
   Covered by new tests `test_causally_linked_log_pairs_stay_ordered` and
   `test_metric_onset_follows_its_causal_log`.
3. **Repaired (2026-08-08).** Answer leakage: `evt-007-01` named "same failure mode as inc-003" in
   the log line; `deployments.json` notes announced "(RED HERRING...)" and "(causal: ...)" in a
   tool-visible feed. Both removed at the generator source; covered by new test
   `test_no_answer_leakage_in_tool_visible_fields`, which scans every log message and deploy note.
4. **Repaired (2026-08-08).** Postmortem narrative timelines were date-less and matched neither the
   answer key nor the tickets (inc-003 off by ~6.5 hours); narrative Container Apps `--rev-NN`
   identifiers resolved nowhere. The three historical postmortems (`data/kb/postmortems/`) are
   retimed to fall within their incident's actual `occurred_at ± 30min` telemetry window with
   explicit dates, and `--rev-NN` mentions are paired with the real `dep-YYYYMMDD-NN` id or replaced
   with a plain description where no deploy record exists for them.
5. Noise is templated (905 identical error strings), so discrimination is trivial; no pre-incident
   baseline history exists (uniform 60-minute windows). Not addressed by this repair: outside the
   four items horizontal-execution-plan.md 1.1 closes.
6. **Repaired (2026-08-08).** Stale data docs: `data/answer_key/README.md` said "Six incident
   scenarios" (there are 7 and a third type `recurrence`); both mentions corrected.

**Corpus-repair verification (2026-08-08):** `uv run python data/synthetic/generate.py` reports
`evidence refs required=42 resolved=42`, no unresolved refs; `build_goldens.py` regenerated;
`tests/test_answer_key.py`, `test_closure.py`, `test_incidents_alerts.py`, `test_kb.py`,
`test_telemetry.py`, `test_evidence_coverage.py`, `test_benign_fixture.py` all pass (54 tests); full
marker-filtered suite is 389 passed, 1 failed, 5 deselected. The one failure,
`test_single_agent_gate.py::test_single_agent_beats_the_deterministic_floor`, is a disclosed,
out-of-scope consequence, not a corpus defect: the repair added five previously-missing metric
evidence refs, which the deterministic fixed plan picks up incidentally (it sweeps a service's full
metric catalog) but the old single-agent LLM planner does not yet ask for, so its `evidence_recall`
(0.3571) no longer strictly beats the deterministic floor (0.4286) after both baselines were
regenerated against the repaired corpus (`eval/baselines/slice_baseline.json`,
`eval/baselines/single_agent_baseline.json`, `eval/cassettes/single_agent.json`, the last two
re-recorded live against `gpt-4o-mini`). Fixing the LLM planner's tool selection is out of this
repair's scope and belongs to different, later work; the file itself is old-architecture machinery
already named for deletion in both plans. `ruff check` and `mypy src` are clean.

**D-006 selections, recorded 2026-08-09.** The candidate mapping this section previously carried
has been resolved into `decisions.md` D-006, which is the authority for the selections; it is not
restated here. The candidates it proposed were confirmed by the coverage audit above with two
refinements worth recording, because both were open questions the earlier note left to the audit:
the change-time subset resolved to inc-005 rather than "inc-001 or inc-005", on the shortest-path
criterion; and the repeatability subset's third slot resolved to inc-006 rather than "a
sparse/inconclusive case", because no authored incident has partial or inconclusive as its only
acceptable outcome, and inc-006 is the one scenario whose golden record accepts partial as correct
rather than as a shortfall. The multi-contributor revision and the benign fixture the earlier note
called for both landed in the 2026-08-08 repair.

**Structured-query implications:** `incidents.json` (7 rows with SLA/known-error/priority fields),
`deployments.json` (9), `alerts.json` (16) are a sufficient operational-records surface for
lookup/filter/COUNT cases; small enough that the demonstration should lean on governed refusal and
provenance rather than scale.

**Retrieval-index implications:** KB docs carry the identifiers exact-match needs (service names,
metric names, error codes, semver versions); no category/date metadata field exists yet for the
categorized `knowledge` container (`kind` maps cleanly onto the three logical collections).

## 12. Azure and Deployment Status

**Target footprint:** six services (Container Apps, Azure OpenAI, Cosmos, ACR, Azure Monitor with
Application Insights, Entra); three Cosmos containers (`investigations` RW, `knowledge` RO,
`operational-records` RO); three OpenAI deployments (primary chat, lower-cost chat, embeddings);
0-1 replicas; one workflow; Bicep.

**Repository-declared (`infra/main.bicep`, compiles clean):** an old-system resource composition
that does not match the accepted six-service target: Log Analytics (no App Insights
component), ACR Basic, Azure OpenAI (`disableLocalAuth`, one `gpt-5-mini` GlobalStandard
deployment), Cosmos serverless (`disableLocalAuth`) with `checkpoints`, `investigations`,
`investigation-index`, managed environment, one Container App (system MI, external ingress, probes,
minReplicas 0 / **maxReplicas 3**), AcrPull/OpenAI-User/Cosmos-data-contributor role assignments.
No Key Vault, queues, VNet, or second app: matches the deliberate-absence list.

**Live (`rg-opspilot`, read-only):** matches the repository template, not the accepted target:
`opspilot-logs`, `acropspilot...`,
`opspilot-env`, `opspilot-api` (image at `main` SHA `e567adf`, 0-3 replicas, FQDN active),
`opspilotoai...` (single `gpt-5-mini` deployment), `opspilot-cosmos-...` (database `opspilot` with
exactly the three old containers). Plus one orphan not in any template: `rytesting`
(CognitiveServices account, kind AIServices) with project `proj-default`.

**Drift / gaps against target:** Application Insights missing (NFR-14/NFR-20 name it as one of the
six services); no lower-cost chat deployment and no embedding deployment (D-002/D-003); Cosmos
containers are the old architecture's set; `maxReplicas: 3` exceeds the 0-1 replica contract; no
Cosmos vector-index configuration exists anywhere (D-003 viability **unverified**); Entra
realization is three app roles + hand-rolled JWT versus built-in auth with no roles.

**Excess/delete candidates (deferred, live changes are out of scope this phase):** `checkpoints`
and `investigation-index` containers; the `Approver`/`Submitter`/`Reader` app-role machinery;
`rytesting` (user to confirm); merged remote branches.

**Progress note (2026-08-08):** the `rytesting` orphan and its `proj-default` project are deleted
from `rg-opspilot`, confirmed via `az cognitiveservices account show` (`ResourceNotFound`) and
`az cognitiveservices account list-deleted` (soft-deleted, recoverable, not yet purged). No other
item in the excess/delete-candidates list above was touched.

**Progress note (2026-08-09):** the `checkpoints` and `investigation-index` containers are deleted,
not as a scoped live change but as a consequence of rebuilding the Cosmos account: vector search
requires a capability Cosmos only accepts at account creation, so the account was deleted and
recreated with it. Bicep now declares one container, `investigations`. The two deployment settings
that would have recreated the deleted containers at runtime were removed with them, and the hosted
smoke's durable-pause assertion went at the same time. The `Approver`/`Submitter`/`Reader` app-role
machinery and the merged remote branches are untouched.

**Deployment blockers:** the current pipeline deploys `main` green; the reconciled system will
break the smoke contract immediately (it asserts `awaiting_approval` and the decision protocol),
so smoke must be replaced in step with the streaming/persistence slices. The Entra submit-role
grant for the deploy SP is a manual step documented only in a smoke failure string.

**Local versus hosted readiness:** local run is `uvicorn opspilot.api:app` with `.env`
(`.env.example` is drifted: no `azure` provider value, none of the Cosmos/identity keys); tests run
offline via fakes/cassettes. Hosted is green for the old contract.

## 13. Test and Evaluation Gap Status

**Deterministic tests (owned by code-guidelines target):** ~365 tests, strong where the old
architecture was strong: decision protocol/idempotency (37), auth (30), tools (26+), corpus
integrity gates (answer key, closure, telemetry, KB), MCP parity (4, over 3 exposed tools),
contracts, cassette drift. Execution result under CI's filter is recorded in section 16.

- Tests that die with their subjects: HITL/decision suite, `test_report_binding.py`,
  `test_checkpointer.py`, auth-role suites (mostly), wild-probe tests, reranker-marked tests.
- Tests worth porting: tool envelope and dispatcher allowlist, corpus gates, MCP parity pattern,
  cassette/replay, prompt registry, tracing seam, state reducers (concept).
- Target-required tests with no counterpart today: four-check gate outcomes, correction allowance,
  cancellation both paths, commit-before-terminal with failure branches (in-memory decision-commit
  ordering exists; Cosmos repo has zero behavioral tests), rendering fidelity, follow-up
  validation, activity projection fidelity/sanitization, structured-query fixture truth and
  rejection, reranking identifier promotion, turn isolation (exists), read-only on every path
  (partial via allowlist).
- Named overclaims found: `test_rerank_scorecard_matches_live_score` only checks sort order;
  `test_scorecard_records_rerank_gain` reads a committed JSON; the single-agent gate replays a
  cassette recorded with `gpt-4o-mini` while production runs `gpt-5-mini`.

**Hosted smoke:** one script, asserts the old contract end to end including a revision-restart
durability check for the HITL pause. It also omits `decision_id`, which
`test_investigations_api.py` asserts is required: the smoke script and the test suite disagree
about the deployed contract.

**Offline evaluation:** four Python evaluators; 13 numeric scorecard metrics; baselines are
recorded runs of the system itself (no lexical baseline for scenarios, no fixed-script evidence
plans, no judge, no categorical outputs, no report generator; `eval/harness.py` is a stub whose
only test asserts it returns zero). The retrieval scorecard's rerank gain (0.749 to 0.821 MRR) is
never re-verified in CI, and it was produced with `bge-small-en-v1.5` while config reports
`bge-m3`. Eval-vs-target mismatch is structural, not incremental.

## 14. Dependency Status

| Dependency | Classification | Reason |
| --- | --- | --- |
| `fastapi`, `uvicorn[standard]`, `pydantic`, `python-dotenv`, `pyyaml` | Keep | Web/serving/contracts baseline |
| `mcp` | Keep | The one protocol boundary (D-004 pending may adjust usage) |
| `rank-bm25` | Keep (verify) | Fits D-003's in-process BM25-style lexical scorer |
| `openai`, `azure-identity` (`llm` group) | Keep | Azure OpenAI adapter, keyless auth |
| `azure-cosmos` (`checkpoint` group) | Keep (regroup) | Needed for the Investigation Record and knowledge/operational containers |
| `numpy`, `pandas` (`data` group) | Keep | Corpus generators; drop from the core CI lane if unused there |
| `ruff`, `mypy`, `pytest`, `httpx` (dev) | Keep | `ruff format` is enforced, scoped to the files a change touches |
| `langgraph`, `langchain-core` | Remove | D-001 rejects a graph runtime; brings `langsmith`, `langgraph-sdk` transitives |
| `langgraph-checkpoint-sqlite`, `langchain-azure-cosmosdb` | Remove | Checkpointing is a deliberate absence; drags `sqlite-vec` into the runtime image |
| `sentence-transformers` (`eval` group, torch + CUDA stack) | Remove | D-003 uses Azure OpenAI embeddings; CrossEncoder reranker is rejected |
| `pyjwt[crypto]` | Verify | Removable if Container Apps built-in auth replaces hand-rolled validation |
| (absent) `azure-servicebus` | Correctly absent | The WIP queue seam that wants it is deleted |
| (absent) OpenTelemetry / Azure Monitor exporter | Missing (add later) | App Insights export for the telemetry seam (A-1); keep to one small package |

## 15. Documentation and Repository Hygiene

- `README.md`: replaced (PR #54, merged to `main`). No longer claims "no LLM in the loop yet";
  describes the runtime actually deployed and points to `docs/status.md` for the reconciliation.
- `.env.example`: replaced (PR #54, merged to `main`). Now covers every setting `config.py` reads,
  including Cosmos and Entra identity variables, checked by `tests/test_env_example.py` rather
  than by eye; the `OLLAMA_BASE_URL` name drift is fixed to `OPSPILOT_OLLAMA_BASE_URL`.
- `docs/` (the authoritative set) and `.githooks/` are committed (PR #54, merged to `main`). Bicep and
  smoke comments citing ADRs that existed only locally are unaffected; still to check when those
  files are next touched.
- Stale G-xx/stage vocabulary is retired from `config.py` (PR #54, merged to `main`, required by
  the full-file scan `code-guidelines.md` §12 obligates on a file a change touches). It still lives on
  in Bicep comments, smoke strings, and prompt/module docstrings, none of which this reset touched;
  retire as the referencing code is replaced.
- `data/answer_key/README.md` and `data/synthetic/README.md` stale (counts, phase references,
  provenance sources disagreeing with `provenance.md`). Not touched by this reset.
- Debris: `out.txt`/`raw.txt`, `infra/.gitkeep`, `data/.gitkeep`, and the orphan `.pyc` for a
  deleted scratch test are removed (PR #54, merged to `main`). The six merged remote branches named in
  the original inspection were not verified or deleted; still outstanding.
- Duplicated definitions flagged for the rewrite: `EvidenceItem` (state.py vs contracts.py),
  `READ_ONLY_TOOLS` vs the registry key set, `KNOWN_IMPLEMENTATIONS` twice, embedding/reranker
  model names defined twice with divergent values, `_UNIT_SEP` three times.

## 16. Verified, Inferred, and Unavailable

**Executed and verified:** `ruff check` (pass); `ruff format --check` (66 files would reformat);
`mypy src` (2 errors: `api.py:862`, `api.py:866`, `epoch` kwarg, confirming the WIP dispatch path
is broken including its inline default); `az bicep build` (compiles); live Azure inventory of
`rg-opspilot` (resources, Cosmos containers, single model deployment, deployed image SHA, replica
range); corpus reference closure (all 42 evidence and 22 retrieval refs resolve); pytest under
CI's filter `-m "not reranker and not llm"`: **31 failed, 351 passed, 5 deselected (11m28s)**. All
31 failures are in `tests/test_investigations_api.py` (decision protocol, decision auth,
concurrency limits), consistent with the mypy-confirmed `epoch` kwarg defect the WIP dispatch
commit introduced into the inline job path; CI at `main` (`e567adf`) ran this suite green, so the
breakage is specific to the unpushed WIP commit and reinforces abandoning it.

**Re-verified on `main` at `4c8f706` (2026-08-08, PR #54 merged), after the WIP commit was
abandoned and the debris/dead-config removal landed:** `ruff check` (pass); `mypy src` (0 errors,
was 2); pytest under the same CI filter (**382 passed, 5 deselected, 0 failed**, was 31 failed/351
passed). `ruff format --check`, `az bicep build`, and the live Azure inventory were not
re-run.

**Statically inspected (code read, not executed):** everything in sections 4 to 15, with file
and symbol citations gathered from full reads of `src/`, `tests/`, `eval/`, `data/`, `infra/`,
`.github/`, `scripts/`.

**Inferred (not proven):** that the deployed app behaves as `main`'s code (image SHA matches, but
no live requests were made); that the recorded scorecards reproduce (known nondeterminism;
`gpt-4o-mini` cassette versus `gpt-5-mini` production).

**Not accessible / not attempted:** container build (`az acr build` is CI-side; no local Docker
build was run); live smoke against the deployed app (would spend model tokens and touch the
approval flow); Cosmos data-plane reads.

**Blocked by D-004 (library inspection):** MCP hosting arrangement (in-runtime vs companion
process), result-vocabulary carriage. The repo's stdio server is evidence that the `mcp` package
works in-process against `ToolService`, which partially answers D-004's first and third questions;
the fourth (result vocabulary) is answered favorably by the existing byte-identical
`ToolResult` passthrough.

**Resolved (D-006, 2026-08-09):** final scenario identifier assignments. The repairs landed, the
five-class coverage audit ran (section 11), and `decisions.md` D-006 now names real identifiers for
every criterion. Nothing here is blocked on corpus selection.

## 17. Implementation Clarifications Exposed by the Repository

These questions were exposed by repository reconciliation. They should be settled in the owning
slice or a small decision update before code invents incompatible answers.

1. **Resolved (D-007).** Normalized incident context fields: the implementation needs one typed
   contract for normalized input. The current `Alert` shape is evidence, not automatic authority.
   `decisions.md` D-007 fixes the contract to five fields (`incident_id`, `scope`, `symptom`,
   `time_anchor`, `supplied_context`), deliberately excluding the raw `IncidentRecord`'s
   answer-leaking and ticket-workflow fields.
2. **Resolved (D-008).** Evidence and knowledge reference encoding: deterministic resolution needs
   one owner for prefixes, keys, and parsing. The existing frozen grammar was evaluated rather than
   copied, and `decisions.md` D-008 adopts it as the canonical encoding with the prefix as the
   declared static discriminator for reference type, one authoritative prefix-to-type map,
   `postmortem:` canonical and `past_incident:` retired, and admission rather than the capability as
   the assigner of the evidence reference. Amended since, adding the `absence:` evidence prefix so an
   authoritative empty result is citable; see D-008 for the encoding and its bounds.
3. **Stateless clarification token:** if the interface uses a short-lived normalization token, the
   signing, expiry, and payload rules need a small explicit contract. A simpler resubmission path
   should be preferred if it meets the requirement.
4. **Resolved (D-009).** Evaluation artifact storage: the report, fixtures, and historical runs
   needed a physical repository location. `decisions.md` D-009 fixes it as files under the existing
   `eval/` tree, with committed `eval/fixtures/` and `eval/reports/` and an ignored `eval/runs/`,
   and keeps authored golden scenario truth under `data/answer_key/`. No store, service, or hosted
   resource is introduced.
5. **D-004 evidence:** the current MCP SDK usage demonstrates in-process execution, same-service
   delegation, and canonical envelope passthrough. D-004 still needs the explicit library
   inspection and final record.
6. **Resolved (D-006).** D-006 evidence: the corpus provides credible candidates, but selections
   must wait for the required repairs and coverage audit. Both happened: the repairs landed
   2026-08-09 (#56) and the five-class coverage audit in section 11 ran against the repaired
   corpus, so `decisions.md` D-006 is accepted with real identifiers for every criterion.
7. **Resolved (2026-08-10).** D-003 vector viability: no Cosmos vector-index configuration exists.
   One now does. The `knowledge` container carries a 1536-dimension cosine vector policy with a
   diskANN index, 196 real embeddings are stored, and a `VectorDistance()` query returns the
   semantically correct runbook with the same-domain distractor absent from the top results.
   D-003's dense-retrieval choice is viable as written; the in-process cosine scan does not need
   its recorded revision.

   Two constraints found while establishing this, both worth keeping: the account capability
   `EnableNoSQLVectorSearch` can only be set at account creation, which is why the account was
   rebuilt; but a container's vector embedding policy is NOT fixed at creation. It can be added to
   a container that lacks one, and a path can be removed and re-added at a different dimension.
   Only in-place modification of a live path is refused. The partition key is the genuinely
   immutable choice.

## 18. Final Status Assessment

**The repository materially conflicts with the target.** The conflict is architectural, not
incidental: the turn lifecycle, approval protocol, orchestration technology, durability model,
outcome vocabulary, agent topology, and persistence layout all realize the previous design that
the accepted documentation explicitly removed. At the same time, a meaningful minority of the code
(tools, corpus and its gates, MCP parity, LLM client/prompt/cassette seams, tracing, CI/Bicep
skeleton) is directly reusable with bounded changes, and the authored corpus is a genuine asset
that needs repair rather than replacement. The correct posture is a deletion-led rebuild of the
orchestration core on the retained foundations, not an incremental adaptation of the existing
graph, and not a from-scratch repository.
