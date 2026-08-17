# OpsPilot Status

**What is the repository right now, measured against the governing design?**

This document records implementation truth: what exists and is reusable, what is partial, what is
missing, and what exists only because an earlier design required it and must now be retired. It is
anchored to the design set, not to any execution plan, and carries no plan identifiers or sequence.
Every row was read in the repository at the inspected commit. A row changes only where the
repository contradicts it.

---

## 1. Baseline

- **Inspected:** `main` at `8789a81`, working tree, 2026-08-17.
- **Toolchain:** `uv`; Python 3.12.
- **Gates at this tree:** `ruff check` clean; `ruff format --check` clean repository-wide; `mypy`
  strict clean over 84 source files; deterministic lane `pytest -q -m "not llm"`: **684 passed,
  2 deselected, no xfails**; the pre-commit hook (lint, format, em-dash, plan-vocabulary) passes.
- **The two deselected** are the only cases that call a live deployment; both are excluded from
  every CI lane, and the seam they exercise is covered deterministically by cassette replay.

---

## 2. Implemented and reusable

Each of these independently earned retention under the governing design; the note says what, if
anything, must still shrink.

| Area | Where | What holds | Still to simplify |
| --- | --- | --- | --- |
| Governed structured query | `data/structured_query.py`, `tools/structured_query.py` | Predicates, projection, count, limit over an approved surface of three collections; two validators guard the boundary; one parameterized read-only query; admitted like any other result | Nothing |
| Operational tool adapters | `tools/{alerts,logs,metrics,deployments,dependencies,incidents}.py`, `data/operational_records.py` | Read the operational-records container through the registry with validated arguments and an explicit deadline; refuse a call with no deadline; report unavailability rather than a generic error | The eight per-capability request models become typed function parameters |
| Two-axis tool result | `tools/contracts.py` | Execution outcome and completeness as separate fields with one pairing validator that rejects a meaningless combination and content on a non-succeeded outcome | The lookup table may become an inline rule; the enforcement point stays; `legacy_status()` and `DocHit` go |
| Reference grammar | `evidence/references.py` | One parser and one resolver over eight prefixes; the prefix decides evidence versus knowledge; `absence:` makes an empty result citable | `Resolution` folds into a return value; the `alert:`, `incident:`, and `query:` evidence forms are absent |
| Evidence admission | `evidence/admission.py`, `evidence/operations.py` | Only a succeeded result becomes evidence; empty becomes a citable absence; partial stays marked; everything else becomes a limitation naming its question | `AuthoritativeAbsence`, `AdmissionResult`, `OperationRecord`, `OperationLedger` become fields or plain returns; `turn_id` leaves the evidence set |
| Retrieval | `retrieval/retriever.py`, `retrieval/embeddings.py`, `data/knowledge_records.py` | Cosmos vector search over an Azure OpenAI query embedding, in-process BM25-style lexical pass over the same category-filtered candidates, reciprocal-rank fusion, section-level passages carrying their text; routing by question shape when no collection is named | Deterministic identifier promotion after fusion does not exist yet; `Doc`/`Chunk`/`Passage` collapse toward one shape |
| Corpus preparation | `scripts/prepare_corpus.py`, `retrieval/corpus.py`, `data/answer_key/topology.yaml` | Loads, chunks, embeds, and indexes the authored corpus into the containers the runtime reads, and verifies by read-back; runs under its own identity; the topology file is what preparation reads for entities | Nothing; `retrieval/corpus.py` and `topology.yaml` are reached only by preparation and stay for it |
| Model seam | `llm/base.py`, `llm/client.py`, `llm/fake.py`, `llm/cassette.py`, `llm/prompts.py`, `llm/manifest.py` | One Azure adapter, one fake, cassette record and replay, prompt loading with versions. A call takes a task label and messages and nothing else; the result carries the task, the deployment that answered, the latency, and the token usage, for every call through every implementation. Authentication is keyless with no key setting, because the account has local authentication disabled | Nothing here; the planner and triage response models in `llm/schema.py` are retired by the legacy diagnosis path that imports them |
| Assessment and brief | `assessment/contracts.py`, `assessment/brief.py` | The designed field set once: `what_happened` with its references, ordered `candidates` (statement, label, `established`, supporting, weakening), `unknowns`, `limitations`, `next_check`, `actions` (action, `now`, optional knowledge reference), `history`, `knowledge_used`; no shape re-checks support and none carries a number; the brief renders deterministically, states the outcome, presents co-causes as contributing causes, and never shows a probability | Nothing |
| Synthesis | `assessment/synthesis.py`, `llm/prompts/rca_synthesis.v2.md` | One task-labelled call proposes; admission is structural only, so no candidate is removed, no `established` is derived, and no action is discarded; an unreadable response, a label outside the vocabulary, or a string no reference grammar could produce is refused as unusable rather than degraded | Nothing |
| Grounding | `grounding/gate.py` | One deterministic function returning zero or more issues over the assessment, the admitted references, the retrieved knowledge references, and the recorded limitations: operational support resolves in this run, knowledge resolves in what was retrieved, knowledge never stands as current proof, `what_happened` and every established candidate rest on admitted evidence, every recorded limitation is disclosed | Nothing |
| Telemetry seam and projection | `obs/tracing.py`, `stream/projection.py`, `stream/contracts.py` | One seam with contextvar-nested spans and a swappable exporter; the activity event is built at the span call site so the two cannot drift | `turn_id` leaves the correlation attributes and the events; the close marker folds into a terminal event carrying the outcome |
| Streaming transport and screen | `POST /turns`, `static/investigation.html` | One streaming request emits identity, activity, a brief event, and a close marker; the page shows intake, the feed, a brief region, and one details area | Route and identity vocabulary become investigation-only; the page needs a brief branch and a question box |
| Normalized incident context | `intake/contracts.py` | Typed and frozen: `incident_id` required, `scope` where the incident names one, `symptom`, `time_anchor`, and nothing answer-bearing or ticket-workflow shaped | Nothing |
| In-memory record | `record/memory.py` | Refuses a second save of the same key; creates the investigation on first save | The port narrows to `save`/`get` and one model; the plural-turn methods and outcome types go |
| Authored expectations and fixture | `data/answer_key/golden_scenarios.yaml`, `benign_fixture.yaml`, `data/answer_key/scenarios.yaml`, `data/answer_key/build_goldens.py` | Seven authored records with all required parts; every required reference resolves in the corpus; the benign fixture is structurally invisible to scenario counting; the builder derives `golden_scenarios.yaml` from `scenarios.yaml` | The record shape may simplify to what evaluation reads; the builder's `golden_incidents.json` and `golden_retrieval.json` outputs go with numeric evaluation |
| Deterministic replay | `eval/cassettes/turn_synthesis.json`, `eval/record_turn_synthesis.py` | One committed cassette, recorded through the same Azure adapter the application ships with, keeps synthesis reproducible without a live model; the manifest refuses a cassette recorded under a different deployment, reasoning effort, API version, or prompt version, and names the field that moved | Nothing |
| Azure baseline | `infra/main.bicep`, `.github/workflows` | One Container App, ACR, one OpenAI account with one chat and one embedding deployment, one Cosmos account with the three containers, Log Analytics, scoped data-plane roles, OIDC deploy | Replicas 0-3 become 0-1; App Insights and built-in auth are absent |

---

## 3. Partial

| Capability | What exists | What does not |
| --- | --- | --- |
| The investigation run | A linear generator in `api.py` gathers a fixed evidence plan (`turn/synthesis_step.py`), admits, synthesizes once, renders the brief, closes; an unusable proposal ends the stream without a brief | No graph, no objective step, no adaptive proposal or authorization, no return, no grounding call in the run, no correction, no persistence, no outcome assigned to a run. Until the gate runs there, a citation naming something the run never admitted reaches the rendered brief |
| Grounding | The function exists and reports issues | Nothing calls it from the run; no correction call; no run assigns an outcome |
| Persistence | Port and in-memory backend with delivery-after-save expressed once | No completed-investigation model; no Cosmos implementation; the `investigations` container is declared and empty; no runtime path writes |
| Retrieval | As in section 2 | Identifier promotion; passage-budget-only truncation |
| Screen | As in section 2 | A branch for the brief event (a rendered brief lands only in the details area); a question box |

---

## 4. Missing

Required by the governing design and not present in any form:

- the three-agent compiled graph over typed investigation state (D-001), with objective, adaptive
  gathering with deterministic authorization, the one return (D-010), grounding with one
  correction, persist, deliver;
- the Evidence Investigator and RCA Analyst as model-directed roles; the Supervisor's
  objective-interpretation call;
- the `CompletedInvestigation` model, carrying the operations list, and its Cosmos repository;
- the `alert:`, `incident:`, and `query:` reference forms and their admission;
- outcome assignment on a run: the rule exists as one function the brief renders from, and nothing
  runs it over an investigation or records the result;
- the question over a completed record;
- the MCP exposure of `get_deployments` (the current server exposes three superseded tools);
- the evaluation runner, the two controlled comparisons and their harness seam, the judge, the
  report;
- Application Insights and the exporter wiring; Container Apps built-in authentication; the
  startup and configuration-validation records.

---

## 5. Superseded: exists only because an earlier design required it

Every item below is reachable in the tree today and conflicts with the governing design. Each is a
named retirement; none is "missing" and none is retained by test coverage or effort spent.

**Superseded orchestration.** `graph.py`, `nodes/investigation.py`, `router.py`, `checkpoint.py`,
`state.py` (41 fields), `hitl_gate`, `apply_edit`, `escalate`, the `postmortem` path,
`traced_node`; the `langgraph-checkpoint-sqlite` dependency. The `langgraph` dependency itself
stays for D-001.

**Async job, approval, and polling.** `investigations.py`, `cosmos_investigations.py`,
`repository.py`; the `/investigations`, `/investigations/{id}/decision`, and `/investigate`
routes and helpers in `api.py`; `CommittedDecision`, idempotency, leases, fencing, outbox, job
status vocabulary, publication identity, approval-bound report hash; the `langchain-azure-cosmosdb`
dependency.

**Legacy report, claim, diagnosis, triage.** Root `contracts.py`; `diagnosis/` (nine modules);
`triage.py`; `composition.py`; `guardrails/policies.py`; `llm/schema.py`'s planner, claim, report,
synthesis, triage, and tool-call response models; the `implementation` template parameter and the
`OPSPILOT_IMPLEMENTATION` setting that select between them; the `langchain-core` explicit base
dependency, imported only by `graph.py` and `nodes/investigation.py`.

**Authorization.** `auth.py`, `ReviewerPrincipal`, `pyjwt[crypto]`; the `entraApiAudience` and
`entraApproverRole` template parameters and the `OPSPILOT_API_AUDIENCE` and
`OPSPILOT_APPROVER_ROLE` settings they feed. `entraTenantId` stays for built-in authentication.

**Console.** `static/console.html`, `/console`, `/console/config`; the `entraConsoleClientId`
template parameter and the `OPSPILOT_CONSOLE_CLIENT_ID` setting.

**Numeric evaluation.** `eval/scenario_eval.py`, `eval/baselines/slice_baseline.json`,
`eval/harness.py`, `EvalTargets` and `TARGETS` in `config.py`, `tests/test_scenario_gate.py`,
`tests/test_scaffold.py`; `eval/golden_incidents.json` and `eval/golden_retrieval.json` with the
builder branches in `data/answer_key/build_goldens.py` that emit them and the sync assertions in
`tests/test_answer_key.py` that read them; the `full` lane in `.github/workflows/deploy.yml`, which
exists to install the eval group for the reranker.

**Model reranker.** `retrieval/reranker.py`, `CrossEncoder`, `RERANKER_MODEL`,
`RERANK_CANDIDATES`, the `reranker` pytest marker, `sentence-transformers` and its transitive
`torch`, `transformers`, `scikit-learn`, `scipy` in the eval group. No caller anywhere.

**Plural-turn identity and persistence.** `turn_id` and `TurnIdentity` in `turn/identity.py`;
`CompletedTurn`, `completed_turns()`, `turn()`, `CommitOutcome`, `CommitResult`,
`DeliveryOutcome`, `commit_then_deliver()` in `record/port.py`; `turn_id` on the evidence set,
spans, and stream events.

**Evidence and tool wrappers.** The eight per-capability request models, `legacy_status()`,
`DocHit`, `AuthoritativeAbsence`, `AdmissionResult`, `Resolution`, `OperationRecord`,
`OperationLedger` as classes; the pairing-table tests in `tests/test_evidence_admission.py`.

**Tests attached to deleted behavior.** `test_investigations_api.py`, `test_investigations.py`,
`test_report_binding.py`, `test_checkpointer.py`, `test_auth.py`, `test_triage.py`,
`test_triager.py`, `test_composition.py`, `test_sufficiency.py`, `test_planner_seam.py`,
`test_diagnose.py`, `test_llm_planner.py`, `test_state_contract.py`; the approval and async cases
in `test_api.py` and `test_guardrails.py`; the plural and delivery-ordering cases in
`test_record_commit.py`; the turn-id assertions in `test_turn_synthesis_stream.py`.

**Infrastructure and packaging.** Replica max 3. In `pyproject.toml`: `azure-cosmos` moves from
the `checkpoint` group into the base dependencies, because `data/knowledge_records.py`,
`data/operational_records.py`, `scripts/prepare_corpus.py`, and the target Cosmos repository import
it; then `langgraph-checkpoint-sqlite` (base) and `langchain-azure-cosmosdb` go, and the emptied
`checkpoint` group is deleted. In the `Dockerfile`, `--group checkpoint` is dropped from the two
`uv sync` lines and the `CMD` line. The mypy strict-override list entries for the modules above are
deleted with them. The base `langgraph` dependency is retained for the compiled graph and is not a
retirement target.

---

## 6. Data state

- **Corpus.** Seven incidents (`inc-001` to `inc-007`) across five families; chronology and
  answer-leakage repairs landed; reference closure holds. Generated error telemetry is templated
  (915 error rows over 10 distinct messages) with no pre-incident baseline; recorded, not blocking.
- **Cosmos.** `retailease/knowledge` holds 196 passages from 28 documents under a 1536-dimension
  vector policy; `retailease/operational-records` holds 14,013 documents across six kinds;
  `opspilot/investigations` is declared and empty. Last live-inspected 2026-08-11.
- **Corpus writer identity.** The application identity holds contributor on `investigations` only
  and reader on `retailease`; preparation writes as a separate principal. Declared in the template.

---

## 7. Deployment state

Last live-inspected 2026-08-09; deployed and green at the superseded composition. One Container
App and image from the Bicep template through the OIDC workflow; replicas 0-3; one chat and one
embedding deployment; no Application Insights; hand-rolled three-role authorization fronts the
superseded endpoints and `POST /turns` is unauthenticated; the three containers are declared.

---

## 8. Open items

- **D-004 library detail** is settled at design level (official `mcp` SDK, in-process, stdio) and
  the current server already runs that way; only the exposed set changes.
- **Comments describing something no longer true.** `turn/identity.py` cites a status section
  number; `tests/test_answer_key.py` cites a heading that no longer exists. Both sit in modules
  that are rewritten or retired.
- **Untracked local configuration.** `.claude/settings.json` and `.claude/settings.local.json`
  appear in every `git status`.
