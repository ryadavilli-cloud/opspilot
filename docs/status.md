# OpsPilot Status

**What is the repository right now, measured against the governing design?**

This document records implementation truth: what exists and is reusable, what is partial, what is
missing, and what exists only because an earlier design required it and must now be retired. It is
anchored to the design set, not to any execution plan, and carries no plan identifiers or sequence.
Every row was read in the repository at the inspected commit. A row changes only where the
repository contradicts it.

---

## 1. Baseline

- **Inspected:** `main` at `a765efe`, working tree, 2026-08-19.
- **Toolchain:** `uv`; Python 3.12.
- **Gates at this tree:** `ruff check` clean; `ruff format --check` clean repository-wide; `mypy`
  strict clean over 59 source files with no override list; deterministic lane
  `pytest -q -m "not llm"`: **522 passed, 1 deselected, no xfails**; the pre-commit hook (lint,
  format, em-dash, vocabulary) passes. CI runs one lane.
- **The count rose** by the return's own cases: eleven scripted ones for the conditions that
  authorize or refuse it, each verified to fail when the condition it names is removed, and four
  replayed ones over the two recordings.
- **The one deselected** is the only case that calls a live deployment; it is excluded from every
  CI lane, and the seam it exercises is covered deterministically by cassette replay.

---

## 2. Implemented and reusable

Each of these independently earned retention under the governing design; the note says what, if
anything, must still shrink.

| Area | Where | What holds | Still to simplify |
| --- | --- | --- | --- |
| Governed structured query | `data/structured_query.py`, `tools/structured_query.py` | Predicates, projection, count, limit over an approved surface of three collections; two validators guard the boundary; one parameterized read-only query; every projection is widened with the collection's identifying fields so each row carries the reference of the record it projects; a count carries no row reference; admitted like any other result | Nothing |
| Operational tool adapters | `tools/{alerts,logs,metrics,deployments,dependencies,incidents}.py`, `data/operational_records.py` | Typed function parameters, validated where the registry invokes them; read the operational-records container with an explicit deadline, which is the configured source ceiling or the investigation's remaining time where that is shorter; refuse a call that names its own deadline, and take the bound positionally so no model-supplied argument can bind it; report a read that ran out of time apart from one that could not be reached, and both apart from a defect; every row-producing capability names its rows, alerts as `alert:` and the incident record as `incident:` | Nothing |
| Two-axis tool result | `tools/contracts.py`, `tools/errors.py` | Execution outcome and completeness as separate fields with one inline pairing rule that rejects a meaningless combination and content on a non-succeeded outcome; all five outcomes are reachable and each for its own reason, timed out for a read that ran past its bound, unavailable for a source that did not answer, rejected only for a request that did not fit the capability's parameters, checked before the body is entered, and failed for anything that goes wrong after that, whether a stored row would not normalize or the capability itself is defective, which the exception message tells apart without the outcome claiming to; no provider message, status, or stack crosses the boundary | Nothing |
| Reference grammar | `evidence/references.py` | One parser and one resolver over eleven prefixes; the prefix decides evidence versus knowledge; `absence:` makes an empty result citable and `query:` an aggregate, both resolving against what admission recorded; a knowledge reference resolves against the passages this investigation retrieved, which the run holds and the completed record carries, never against an authored file on disk; the resolver answers whether a reference names something real and nothing more | Nothing |
| Evidence admission | `evidence/admission.py`, `evidence/operations.py` | Only a succeeded result becomes evidence; empty becomes a citable absence; an aggregate becomes an observation citable by its operation; partial stays marked; everything else becomes a limitation naming its question; the evidence set carries observations, limitations, and the operations list, keyed by `investigation_id` alone | Nothing |
| Retrieval | `retrieval/retriever.py`, `retrieval/embeddings.py`, `data/knowledge_records.py` | Cosmos vector search over an Azure OpenAI query embedding, in-process BM25-style lexical pass over the same category-filtered candidates, reciprocal-rank fusion, then stable promotion of passages whose extracted identifiers the question names, then truncation to the passage budget; the collection searched is the one the calling capability names, never inferred; one passage shape carrying text and reference, returned by the capabilities unreshaped; no model ranks at any stage | Nothing |
| Corpus preparation | `scripts/prepare_corpus.py`, `retrieval/corpus.py`, `data/answer_key/topology.yaml` | Loads, chunks, embeds, and indexes the authored corpus into the containers the runtime reads, and verifies by read-back; runs under its own identity; the topology file is what preparation reads for entities | Nothing; `retrieval/corpus.py` and `topology.yaml` are reached only by preparation and stay for it |
| Model seam | `llm/base.py`, `llm/client.py`, `llm/fake.py`, `llm/cassette.py`, `llm/prompts.py`, `llm/manifest.py` | One Azure adapter, one fake, cassette record and replay, prompt loading with versions. A call takes a task label and messages and nothing else; the result carries the task, the deployment that answered, the latency, and the token usage, for every call through every implementation. Authentication is keyless with no key setting, because the account has local authentication disabled | Nothing |
| Assessment and brief | `assessment/contracts.py`, `assessment/brief.py` | The designed field set once: `what_happened` with its references, ordered `candidates` (statement, label, `established`, supporting, weakening), `unknowns`, `limitations`, `next_check`, `actions` (action, `now`, optional knowledge reference), `history`, `knowledge_used`; no shape re-checks support and none carries a number; the brief renders deterministically, states the outcome, presents co-causes as contributing causes, and never shows a probability | Nothing |
| Synthesis | `assessment/synthesis.py`, `llm/prompts/rca_synthesis.v4.md` | One task-labelled call proposes; admission is structural only, so no candidate is removed, no `established` is derived, and no action is discarded; an unreadable response, a label outside the vocabulary, or a string no reference grammar could produce is refused as unusable rather than degraded; a `null` written for an optional field reads as absent, because that is what JSON means by it and what the field's default already says; the one routing field travels beside the assessment rather than inside it, and names an evidence kind from the vocabulary the proposable capabilities supply | Nothing |
| Grounding | `grounding/gate.py` | One deterministic function returning zero or more issues over the assessment, the admitted references, the retrieved knowledge references, and the recorded limitations: operational support resolves in this run, knowledge resolves in what was retrieved, knowledge never stands as current proof, `what_happened` and every established candidate rest on admitted evidence, every recorded limitation is disclosed | Nothing |
| Telemetry seam and projection | `obs/tracing.py`, `stream/projection.py`, `stream/contracts.py` | One seam with contextvar-nested spans and a swappable exporter; the activity event is built at the same call as the span it mirrors, from the same stated facts, so the two cannot drift; correlation is by `investigation_id` and `incident_id` alone; the sequence comes from what the run has already emitted rather than a counter held beside it | Nothing |
| Streaming transport and screen | `POST /investigations`, `static/investigation.html` | One streaming request owns one investigation: identity first, activity as it happens, then exactly one terminal event carrying the brief or a sanitized failure category, never both and never neither; a client that disconnects is sent nothing further, and nothing was persisted before the graph's own save; the page shows intake, the feed, the brief as the dominant element once the terminal event arrives, and one details area | A question box |
| Investigation runtime | `investigation/state.py`, `investigation/agents.py`, `investigation/graph.py` | One compiled in-process graph over typed state with no checkpointer: set objective, gather with deterministic continuation, synthesize, ground, persist, deliver, and the return edge declared. Three model-directed roles that only ever propose. Five bounds set by code at objective time: deadline, capability-call cap, model-call cap, `correction_used`, `return_used`, with the model cap reserving what synthesis and its one correction still need. The run's remaining time travels with every capability call, so no source read can outlive the investigation that asked for it. Every registered capability is proposable, so the one inventory the registry is built from is also what the investigator chooses among and what the returnable evidence kinds are derived from. Retrieved passages are held in a knowledge set beside the evidence set and reach both roles as context, the grounding gate as its second reference set, and the completed record; admission never sees them, because a document cannot observe the running system. Authorization is a membership test on the registered set, the questions already put, and the calls already made by capability and arguments. One return from analysis to gathering, authorized on the same terms and costed before it is granted, so a run that returns is bounded exactly like one that does not and cannot end as a failure for having asked. Failure is a first-class path emitting a sanitized category and persisting nothing | Nothing |
| Outcome assignment | `assessment/brief.py`, `investigation/graph.py` | One function derives the outcome from two facts the assessment already holds, and the run records it: inconclusive where nothing is established, partial where something is with a limitation recorded, complete where something is without one | Nothing |
| Normalized incident context | `intake/contracts.py` | Typed and frozen: `incident_id` required, `scope` where the incident names one, `symptom`, `time_anchor`, and nothing answer-bearing or ticket-workflow shaped | Nothing |
| Completed-investigation record | `record/completed.py`, `record/port.py`, `record/memory.py`, `record/cosmos.py` | One `CompletedInvestigation` carrying identity, incident, objective, outcome and why gathering stopped, admitted observations, limitations, the operations list, retrieved passages with their text, the assessment, the brief, the telemetry correlation reference, and the model and prompt versions; one seam with `save` and `get`; in-memory and Cosmos backends that both normalize through the stored document, so a second save of the same identifier is refused and a read carries the same contents whichever is behind the seam; the run writes through it before it delivers | Nothing |
| Authored expectations and fixture | `data/answer_key/golden_scenarios.yaml`, `benign_fixture.yaml`, `data/answer_key/scenarios.yaml`, `data/answer_key/build_goldens.py` | Seven authored records with all required parts; every required reference resolves in the corpus; the benign fixture is structurally invisible to scenario counting; the builder derives `golden_scenarios.yaml` from `scenarios.yaml` | The record shape may simplify to what evaluation reads; the builder's `golden_incidents.json` and `golden_retrieval.json` outputs go with numeric evaluation |
| Deterministic replay | `eval/cassettes/inc-005.json`, `eval/cassettes/inc-004.json`, `eval/record_investigation.py` | Two committed cassettes, one per recorded incident, each holding every model call of one whole investigation, so the deterministic lane replays real runs rather than scripted calls; one of them is a run where the analyst asked for more and code granted it, and the other a run where it asked for nothing and closed on what it had; the recorder drives the real streaming request, so a recorded response can only be one the replay path would ask for, and refuses to run unless the endpoint and deployment are named; the recording is taken through the Azure adapter against the chat deployment the application calls, keyless as the signed-in identity, so it is evidence about the serving path the application actually takes; the manifest refuses a cassette recorded under a different deployment, reasoning effort, API version, or prompt version, and names the field that moved | Nothing |
| Azure baseline | `infra/main.bicep`, `.github/workflows` | One Container App, ACR, one OpenAI account with one chat and one embedding deployment, one Cosmos account with the three containers, Log Analytics, scoped data-plane roles, OIDC deploy; readiness asks only that the operational source answer a seeded lookup and that retrieval came up as the configured backend, and the post-deploy smoke run is where a whole hosted investigation is proven | Replicas 0-3 become 0-1; App Insights and built-in auth are absent |

---

## 3. Partial

| Capability | What exists | What does not |
| --- | --- | --- |
| The investigation run | The whole path: objective, adaptive gathering under deterministic authorization, synthesis, the one return where analysis asks for more and code grants it, grounding, one correction, outcome, save, deliver. Two incidents run it end to end on recorded real models | Retrieval and the structured query are registered and not offered to the investigator, so a run reaches neither, and no run carries a retrieved passage into its record |
| Screen | Intake, the live feed, the brief as the dominant element on the terminal event, and one details area | A question box |

---

## 4. Missing

Required by the governing design and not present in any form:

- runtime selection of the Cosmos record backend: `record/cosmos.py` exists and is covered, and
  the application still constructs the in-memory one, so a completed investigation does not
  survive the process that produced it;
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

**Infrastructure and packaging.** Replica max 3, and the `entraApiAudience`,
`entraApproverRole`, and `entraConsoleClientId` template parameters, which now feed settings no
code reads; their removal belongs with the step that settles hosted authentication.
`entraTenantId` stays for built-in authentication. The `implementation` parameter is gone, with
the setting and the container environment entry it fed. The base `langgraph` dependency is
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

Last live-inspected 2026-08-19, at the revision built from this landing. One Container App
and image from the Bicep template through the OIDC workflow; replicas 0-3; one chat and one
embedding deployment; no Application Insights; the three containers are declared. The deployment
workflow, including its post-deploy smoke run, passes against that revision.

Readiness answers there in its narrowed form: two checks, `operational_records` and `retrieval`,
both ok, with the backend reported as the configured one. The two probes before it timed out at the
client while the scaled-to-zero application started, which is cold start rather than a slow check.

One hosted investigation ran end to end against that revision, through the graph: inc-005, fourteen
activity events, one terminal event carrying a brief and no failure. Because a failed gate spends
the one correction and then fails the execution, a delivered brief is a grounded brief; and because
the save runs before delivery, the record existed before the terminal event. The run reported an
inconclusive outcome, which is a result rather than a failure.

`/version` on that revision reports `environment=local`. `OPSPILOT_ENV` is set nowhere in the
template, so the container takes the default. Nothing keys off it today and no behavior is affected,
but the hosted revision misreports which environment it is.

The return was observed hosted on a revision that offered six capabilities. One investigation of
inc-005 against it gathered six times, synthesized, was sent back for one further capability call,
synthesized again, grounded, saved, and delivered, with the return carried in the feed as its own
entry between the two assessments. The run reported an inconclusive outcome and no failure.

That proof describes a narrower offering than the tree now carries, so this tree was deployed and
run in turn. The revision built from this landing is healthy, readiness answers on its two checks
with Cosmos behind them, and one investigation of inc-005 gathered eight times, synthesized once,
grounded without an issue, saved, and delivered a brief with an inconclusive outcome and no
failure. The mechanism the earlier proof demonstrated is unchanged and is proven in the
deterministic lane, where the path can be held still.

What the hosted run shows about selection is the same thing the recordings show, on the deployed
revision and against the real corpus. Gathering spent the capability cap and the next proposal was
refused for it, so analysis was reached with nothing left to send back for and no return occurred.
Neither retrieval capability was proposed, so the run cited no knowledge at all. Two of the eight
calls were refused at the boundary rather than executed, one of them the structured query, whose
structure did not validate against the approved surface; the refusals cost calls the run then did
not have. That is the offering being worked through rather than selected from, and it is recorded
above as one finding with one owner.

Whether any given hosted run returns is the model's to decide: the same incident recorded locally
returned, and the incident the plan predicted would return did not. The smoke run therefore proves
the envelope and the delivered brief, and does not assert a return, because a run that settles its
question without asking for more is a correct run.

---

## 8. Open items

- **The MCP boundary is settled at design level** (official `mcp` SDK, in-process, stdio) and no
  server exists in the tree: the one that fronted three superseded tools went with the request
  models its schemas were generated from. The `mcp` dependency is retained for the exposure the
  design carries.
- **The streaming route is unauthenticated**, and it is now the only route that starts work. The
  hand-rolled three-role authorization went with the endpoints it fronted, and Container Apps
  built-in authentication has not replaced it, so the gap is open rather than merely pending.
- **The investigator works down the offering rather than selecting from it.** With six
  capabilities offered a recorded run made six capability calls and had budget left; with nine
  offered, both re-recorded runs made nine selection calls and spent the cap. The call count
  tracks the size of the menu rather than what the incident needs, and the two retrieval
  capabilities sit at the end of that menu, which is why neither recorded run reached for a
  runbook or a precedent even on the incident whose postmortem exists. Two consequences follow
  from the one cause: the analyst's request to return is declined for lack of room rather than
  refused on its merits, and retrieval is reachable without being consulted. Raising the cap
  would buy more enumeration at more cost, and reserving calls for the return would take them
  from first-pass gathering in every run to serve the rare one; neither addresses selection. This
  is the charter of the step that makes retrieval influential: prompt text about passages alone
  will report success while the same sweep continues.
- **Untracked local configuration.** `.claude/settings.json` and `.claude/settings.local.json`
  appear in every `git status`.
