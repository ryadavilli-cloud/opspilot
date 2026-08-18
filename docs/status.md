# OpsPilot Status

**What is the repository right now, measured against the governing design?**

This document records implementation truth: what exists and is reusable, what is partial, what is
missing, and what exists only because an earlier design required it and must now be retired. It is
anchored to the design set, not to any execution plan, and carries no plan identifiers or sequence.
Every row was read in the repository at the inspected commit. A row changes only where the
repository contradicts it.

---

## 1. Baseline

- **Inspected:** `main` at `2a0fe7a` plus the investigation-runtime landing, working tree,
  2026-08-18.
- **Toolchain:** `uv`; Python 3.12.
- **Gates at this tree:** `ruff check` clean; `ruff format --check` clean repository-wide; `mypy`
  strict clean over 59 source files with no override list; deterministic lane
  `pytest -q -m "not llm"`: **469 passed, 1 deselected, no xfails**; the pre-commit hook (lint,
  format, em-dash, plan-vocabulary) passes. CI runs one lane.
- **The count fell** because the runtime this landing replaced took its tests with it. Every
  guarantee those tests protected either moved to the graph's own suite or described behavior the
  design no longer carries.
- **The one deselected** is the only case that calls a live deployment; it is excluded from every
  CI lane, and the seam it exercises is covered deterministically by cassette replay.

---

## 2. Implemented and reusable

Each of these independently earned retention under the governing design; the note says what, if
anything, must still shrink.

| Area | Where | What holds | Still to simplify |
| --- | --- | --- | --- |
| Governed structured query | `data/structured_query.py`, `tools/structured_query.py` | Predicates, projection, count, limit over an approved surface of three collections; two validators guard the boundary; one parameterized read-only query; every projection is widened with the collection's identifying fields so each row carries the reference of the record it projects; a count carries no row reference; admitted like any other result | Nothing |
| Operational tool adapters | `tools/{alerts,logs,metrics,deployments,dependencies,incidents}.py`, `data/operational_records.py` | Typed function parameters, validated where the registry invokes them; read the operational-records container with an explicit deadline; refuse a call that names its own deadline; report unavailability rather than a generic error; every row-producing capability names its rows, alerts as `alert:` and the incident record as `incident:` | Nothing |
| Two-axis tool result | `tools/contracts.py` | Execution outcome and completeness as separate fields with one inline pairing rule that rejects a meaningless combination and content on a non-succeeded outcome | Nothing |
| Reference grammar | `evidence/references.py` | One parser and one resolver over eleven prefixes; the prefix decides evidence versus knowledge; `absence:` makes an empty result citable and `query:` an aggregate, both resolving against what admission recorded; the resolver answers whether a reference names something real and nothing more | Nothing |
| Evidence admission | `evidence/admission.py`, `evidence/operations.py` | Only a succeeded result becomes evidence; empty becomes a citable absence; an aggregate becomes an observation citable by its operation; partial stays marked; everything else becomes a limitation naming its question; the evidence set carries observations, limitations, and the operations list, keyed by `investigation_id` alone | Nothing |
| Retrieval | `retrieval/retriever.py`, `retrieval/embeddings.py`, `data/knowledge_records.py` | Cosmos vector search over an Azure OpenAI query embedding, in-process BM25-style lexical pass over the same category-filtered candidates, reciprocal-rank fusion, then stable promotion of passages whose extracted identifiers the question names, then truncation to the passage budget; the collection searched is the one the calling capability names, never inferred; one passage shape carrying text and reference, returned by the capabilities unreshaped; no model ranks at any stage | Nothing |
| Corpus preparation | `scripts/prepare_corpus.py`, `retrieval/corpus.py`, `data/answer_key/topology.yaml` | Loads, chunks, embeds, and indexes the authored corpus into the containers the runtime reads, and verifies by read-back; runs under its own identity; the topology file is what preparation reads for entities | Nothing; `retrieval/corpus.py` and `topology.yaml` are reached only by preparation and stay for it |
| Model seam | `llm/base.py`, `llm/client.py`, `llm/fake.py`, `llm/cassette.py`, `llm/prompts.py`, `llm/manifest.py` | One Azure adapter, one fake, cassette record and replay, prompt loading with versions. A call takes a task label and messages and nothing else; the result carries the task, the deployment that answered, the latency, and the token usage, for every call through every implementation. Authentication is keyless with no key setting, because the account has local authentication disabled | Nothing |
| Assessment and brief | `assessment/contracts.py`, `assessment/brief.py` | The designed field set once: `what_happened` with its references, ordered `candidates` (statement, label, `established`, supporting, weakening), `unknowns`, `limitations`, `next_check`, `actions` (action, `now`, optional knowledge reference), `history`, `knowledge_used`; no shape re-checks support and none carries a number; the brief renders deterministically, states the outcome, presents co-causes as contributing causes, and never shows a probability | Nothing |
| Synthesis | `assessment/synthesis.py`, `llm/prompts/rca_synthesis.v3.md` | One task-labelled call proposes; admission is structural only, so no candidate is removed, no `established` is derived, and no action is discarded; an unreadable response, a label outside the vocabulary, or a string no reference grammar could produce is refused as unusable rather than degraded; a `null` written for an optional field reads as absent, because that is what JSON means by it and what the field's default already says | Nothing |
| Grounding | `grounding/gate.py` | One deterministic function returning zero or more issues over the assessment, the admitted references, the retrieved knowledge references, and the recorded limitations: operational support resolves in this run, knowledge resolves in what was retrieved, knowledge never stands as current proof, `what_happened` and every established candidate rest on admitted evidence, every recorded limitation is disclosed | Nothing |
| Telemetry seam and projection | `obs/tracing.py`, `stream/projection.py`, `stream/contracts.py` | One seam with contextvar-nested spans and a swappable exporter; the activity event is built at the same call as the span it mirrors, from the same stated facts, so the two cannot drift; correlation is by `investigation_id` and `incident_id` alone; the sequence comes from what the run has already emitted rather than a counter held beside it | Nothing |
| Streaming transport and screen | `POST /investigations`, `static/investigation.html` | One streaming request owns one investigation: identity first, activity as it happens, then exactly one terminal event carrying the brief or a sanitized failure category, never both and never neither; a client that disconnects is sent nothing further, and nothing was persisted before the graph's own save; the page shows intake, the feed, the brief as the dominant element once the terminal event arrives, and one details area | A question box |
| Investigation runtime | `investigation/state.py`, `investigation/agents.py`, `investigation/graph.py` | One compiled in-process graph over typed state with no checkpointer: set objective, gather with deterministic continuation, synthesize, ground, persist, deliver, and the return edge declared. Three model-directed roles that only ever propose. Five bounds set by code at objective time: deadline, capability-call cap, model-call cap, `correction_used`, `return_used`, with the model cap reserving what synthesis and its one correction still need. Authorization is a membership test on the registered set, the questions already put, and the calls already made by capability and arguments. Failure is a first-class path emitting a sanitized category and persisting nothing | The one return is declared and not yet followed; retrieval and the structured query are registered and not yet offered to the investigator |
| Outcome assignment | `assessment/brief.py`, `investigation/graph.py` | One function derives the outcome from two facts the assessment already holds, and the run records it: inconclusive where nothing is established, partial where something is with a limitation recorded, complete where something is without one | Nothing |
| Normalized incident context | `intake/contracts.py` | Typed and frozen: `incident_id` required, `scope` where the incident names one, `symptom`, `time_anchor`, and nothing answer-bearing or ticket-workflow shaped | Nothing |
| Completed-investigation record | `record/completed.py`, `record/port.py`, `record/memory.py`, `record/cosmos.py` | One `CompletedInvestigation` carrying identity, incident, objective, outcome and why gathering stopped, admitted observations, limitations, the operations list, retrieved passages with their text, the assessment, the brief, the telemetry correlation reference, and the model and prompt versions; one seam with `save` and `get`; in-memory and Cosmos backends that both normalize through the stored document, so a second save of the same identifier is refused and a read carries the same contents whichever is behind the seam; the run writes through it before it delivers | Nothing |
| Authored expectations and fixture | `data/answer_key/golden_scenarios.yaml`, `benign_fixture.yaml`, `data/answer_key/scenarios.yaml`, `data/answer_key/build_goldens.py` | Seven authored records with all required parts; every required reference resolves in the corpus; the benign fixture is structurally invisible to scenario counting; the builder derives `golden_scenarios.yaml` from `scenarios.yaml` | The record shape may simplify to what evaluation reads; the builder's `golden_incidents.json` and `golden_retrieval.json` outputs go with numeric evaluation |
| Deterministic replay | `eval/cassettes/investigation.json`, `eval/record_investigation.py` | One committed cassette holds every model call of one whole investigation, so the deterministic lane replays a real run rather than one scripted call; the recorder drives the real streaming request, so a recorded response can only be one the replay path would ask for, and refuses to run unless the endpoint and deployment are named; the recording is taken through the Azure adapter against the chat deployment the application calls, keyless as the signed-in identity, so it is evidence about the serving path the application actually takes; the manifest refuses a cassette recorded under a different deployment, reasoning effort, API version, or prompt version, and names the field that moved | Nothing |
| Azure baseline | `infra/main.bicep`, `.github/workflows` | One Container App, ACR, one OpenAI account with one chat and one embedding deployment, one Cosmos account with the three containers, Log Analytics, scoped data-plane roles, OIDC deploy | Replicas 0-3 become 0-1; App Insights and built-in auth are absent |

---

## 3. Partial

| Capability | What exists | What does not |
| --- | --- | --- |
| The investigation run | The whole path: objective, adaptive gathering under deterministic authorization, synthesis, grounding, one correction, outcome, save, deliver. One incident runs it end to end on a recorded real model | The one return is declared as an edge and never followed, because nothing proposes one yet; retrieval and the structured query are registered and not offered to the investigator, so a run reaches neither, and no run carries a retrieved passage into its record |
| Screen | Intake, the live feed, the brief as the dominant element on the terminal event, and one details area | A question box |
| Capability deadline | The run holds one deadline and stops on it; each source call carries the configured per-source ceiling, and dispatch refuses a call that names its own | The remaining run time is not what each capability call carries, because the registry is a process singleton that owns its own ceiling |

---

## 4. Missing

Required by the governing design and not present in any form:

- the Cosmos repository behind the record seam;
- the question over a completed record;
- any MCP exposure: the server that fronted three superseded tools is gone and nothing replaces it
  yet;
- the evaluation runner, the two controlled comparisons and their harness seam, the judge, the
  report;
- Application Insights and the exporter wiring; Container Apps built-in authentication; the
  startup and configuration-validation records.

---

## 5. Superseded: exists only because an earlier design required it

Every item below is reachable in the tree today and conflicts with the governing design. Each is a
named retirement; none is "missing" and none is retained by test coverage or effort spent.

**Numeric evaluation.** `eval/golden_incidents.json` and `eval/golden_retrieval.json` with the
builder branches in `data/answer_key/build_goldens.py` that emit them and the sync assertions in
`tests/test_answer_key.py` that read them. The scenario and single-agent gates, their harness,
their baselines, and their recorders are gone: each drove the runtime that no longer exists or
replayed a cassette recorded through a provider the model seam no longer has, so neither could be
re-recorded or run.

**Infrastructure and packaging.** Replica max 3, and the `implementation`, `entraApiAudience`,
`entraApproverRole`, and `entraConsoleClientId` template parameters, which now feed settings no
code reads. `entraTenantId` stays for built-in authentication. The base `langgraph` dependency is
retained for the compiled graph and is not a retirement target.

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

Last live-inspected 2026-08-18, at a revision carrying the tree through the retrieval landing.
That revision predates this one: it still serves the superseded runtime, so what is described here
is what is deployed, not what the tree now builds. One Container App and image from the Bicep
template through the OIDC workflow; replicas 0-3; one chat and one embedding deployment; no
Application Insights; the three containers are declared. Readiness reports every check ok:
operational records, repository, logs, and retrieval, the last of which reaches the knowledge
container through the promoting retriever. The deployment workflow, including its post-deploy smoke
test, passes against that revision.

One hosted investigation ran end to end against that revision. It admitted 79 observations across
the alert, log, metric, and absence forms; every one parsed and every one is an evidence reference.
The brief it delivered cites fifteen references and every one was assigned by admission during that
run, including the alert and the authoritative absence, which the assessment uses to weaken a
candidate rather than to support one. The brief carries the designed sections and no probability.

What that hosted run could not show is what this tree changed. It had no gate in its streaming
path, so an invented reference would have reached the brief rather than being reported, and its
evidence plan was fixed, so `incident:` and `query:` had no hosted path. Both forms are proven
against the real corpus in the deterministic suite. A hosted run of the current tree has not been
taken.

---

## 8. Open items

- **The MCP boundary is settled at design level** (official `mcp` SDK, in-process, stdio) and no
  server exists in the tree: the one that fronted three superseded tools went with the request
  models its schemas were generated from. The `mcp` dependency is retained for the exposure the
  design carries.
- **The streaming route is unauthenticated**, and it is now the only route that starts work. The
  hand-rolled three-role authorization went with the endpoints it fronted, and Container Apps
  built-in authentication has not replaced it, so the gap is open rather than merely pending.
- **Comments describing something no longer true.** `tests/test_answer_key.py` cites a heading that
  no longer exists.
- **Untracked local configuration.** `.claude/settings.json` and `.claude/settings.local.json`
  appear in every `git status`.
