# OpsPilot Status

**What is the repository right now, measured against the governing design?**

This document records implementation truth: what exists and is reusable, what is partial, what is
missing, and what exists only because an earlier design required it and must now be retired. It is
anchored to the design set, not to any execution plan, and carries no plan identifiers or sequence.
Every row was read in the repository at the inspected commit. A row changes only where the
repository contradicts it.

---

## 1. Baseline

- **Inspected:** `main` at `491e0cd` plus the governed-query landing, working tree, 2026-08-20.
- **Toolchain:** `uv`; Python 3.12.
- **Gates at this tree:** `ruff check` clean; `ruff format --check` clean repository-wide; `mypy`
  strict clean over 61 source files with no override list; deterministic lane
  `pytest -q -m "not llm"`: **566 passed, 1 deselected, no xfails**; the pre-commit hook (lint,
  format, em-dash, vocabulary) passes. CI runs one lane.
- **The count rose** by what the offering and the budget now carry, and by the recurrence
  recording: that every capability describes itself, that the investigator is told what it has
  left to spend, that the analyst is shown the knowledge the run retrieved, and five replayed
  cases over a run that consulted written knowledge and cited it.
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
| Retrieval | `retrieval/retriever.py`, `retrieval/embeddings.py`, `data/knowledge_records.py` | Cosmos vector search over an Azure OpenAI query embedding, in-process BM25-style lexical pass over the same category-filtered candidates, reciprocal-rank fusion, then stable promotion of passages whose extracted identifiers the question names, then truncation to the passage budget; the collection searched is the one the calling capability names, never inferred; one passage shape carrying text and reference, returned by the capabilities unreshaped; no model ranks at any stage; a search fixes the duration it was given as one deadline and spends it down across embedding, vector search, and the lexical read, so the three together cannot outlast what the caller allowed | Nothing |
| Corpus preparation | `scripts/prepare_corpus.py`, `retrieval/corpus.py`, `data/answer_key/topology.yaml` | Loads, chunks, embeds, and indexes the authored corpus into the containers the runtime reads, and verifies by read-back; runs under its own identity; the topology file is what preparation reads for entities | Nothing; `retrieval/corpus.py` and `topology.yaml` are reached only by preparation and stay for it |
| Model seam | `llm/base.py`, `llm/client.py`, `llm/fake.py`, `llm/cassette.py`, `llm/prompts.py`, `llm/manifest.py` | One Azure adapter, one fake, cassette record and replay, prompt loading with versions. A call takes a task label, messages, and the time the run has left, and nothing else; the live adapter hands that bound to the request itself, so a model call cannot go on being paid for after the investigation that made it has stopped. Absent means unbounded, which is for callers outside an investigation. The result carries the task, the deployment that answered, the latency, and the token usage, for every call through every implementation. Authentication is keyless with no key setting, because the account has local authentication disabled | Nothing |
| Assessment and brief | `assessment/contracts.py`, `assessment/brief.py` | The designed field set once: `what_happened` with its references, ordered `candidates` (statement, label, `established`, supporting, weakening), `unknowns`, `limitations`, `next_check`, `actions` (action, `now`, optional knowledge reference), `history`, `knowledge_used`; no shape re-checks support and none carries a number; the brief renders deterministically, states the outcome, presents co-causes as contributing causes, and never shows a probability | Nothing |
| Synthesis | `assessment/synthesis.py`, `llm/prompts/rca_synthesis.v5.md` | One task-labelled call proposes; admission is structural only, so no candidate is removed, no `established` is derived, and no action is discarded; an unreadable response, a label outside the vocabulary, or a string no reference grammar could produce is refused as unusable rather than degraded; a `null` written for an optional field reads as absent, because that is what JSON means by it and what the field's default already says; the one routing field travels beside the assessment rather than inside it, and names an evidence kind from the vocabulary the proposable capabilities supply; the analyst is shown the passages the run retrieved and must name the guidance that shaped an action, so a recommendation says whether it is documented practice or inference from what this run observed | Nothing |
| Grounding | `grounding/gate.py` | One deterministic function returning zero or more issues over the assessment, the admitted references, the retrieved knowledge references, and the recorded limitations: operational support resolves in this run, knowledge resolves in what was retrieved, knowledge never stands as current proof, `what_happened` and every established candidate rest on admitted evidence, every recorded limitation is disclosed | Nothing |
| Telemetry seam and projection | `obs/tracing.py`, `stream/projection.py`, `stream/contracts.py` | One seam with contextvar-nested spans and a swappable exporter; the activity event is built at the same call as the span it mirrors, from the same stated facts, so the two cannot drift; correlation is by `investigation_id` and `incident_id` alone; the sequence comes from what the run has already emitted rather than a counter held beside it | Nothing |
| Streaming transport and screen | `POST /investigations`, `static/investigation.html` | One streaming request owns one investigation: identity first, activity as it happens, then exactly one terminal event carrying the brief or a sanitized failure category, never both and never neither; a client that disconnects is sent nothing further, and nothing was persisted before the graph's own save; the page shows intake, the feed, the brief as the dominant element once the terminal event arrives, one details area, and the question box beside it once that event carries a brief | Nothing |
| Investigation runtime | `investigation/state.py`, `investigation/agents.py`, `investigation/graph.py` | One compiled in-process graph over typed state with no checkpointer: set objective, gather with deterministic continuation, synthesize, ground, persist, deliver, and the return edge declared. Three model-directed roles that only ever propose. Five bounds set by code at objective time: deadline, capability-call cap, model-call cap, `correction_used`, `return_used`, with the model cap reserving what synthesis and its one correction still need. The run's remaining time travels with every capability call and every model call, so neither a source read nor a model request can outlive the investigation that asked for it. Every registered capability is proposable, so the one inventory the registry is built from is also what the investigator chooses among and what the returnable evidence kinds are derived from. Retrieved passages are held in a knowledge set beside the evidence set and reach both roles as context, the grounding gate as its second reference set, and the completed record; admission never sees them, because a document cannot observe the running system. Authorization is a membership test on the registered set, the questions already put, and the calls already made by capability and arguments. One return from analysis to gathering, authorized on the same terms and costed before it is granted, so a run that returns is bounded exactly like one that does not and cannot end as a failure for having asked. Failure is a first-class path emitting a sanitized category and persisting nothing | Nothing |
| Outcome assignment | `assessment/brief.py`, `investigation/graph.py` | One function derives the outcome from two facts the assessment already holds, and the run records it: inconclusive where nothing is established, partial where something is with a limitation recorded, complete where something is without one | Nothing |
| Normalized incident context | `intake/contracts.py` | Typed and frozen: `incident_id` required, `scope` where the incident names one, `symptom`, `time_anchor`, and nothing answer-bearing or ticket-workflow shaped | Nothing |
| Completed-investigation record | `record/completed.py`, `record/port.py`, `record/memory.py`, `record/cosmos.py` | One `CompletedInvestigation` carrying identity, incident, objective, outcome and why gathering stopped, admitted observations, limitations, the operations list, retrieved passages with their text, the assessment, the brief, the telemetry correlation reference, and the model and prompt versions; one seam with `save` and `get`; in-memory and Cosmos backends that both normalize through the stored document, so a second save of the same identifier is refused and a read carries the same contents whichever is behind the seam; the run writes through it before it delivers | Nothing |
| Authored expectations and fixture | `data/answer_key/scenarios.yaml`, `golden_scenarios.yaml`, `benign_fixture.yaml`, `tests/answer_key.py` | Seven authored records with all required parts, every required reference resolving in the corpus, each now also carrying what an evaluation reads of it: the outcomes the scenario accepts, evidence the corpus deliberately holds none of, the behavior it tests, the alternatives an assessment may reach instead, how retrieved knowledge should matter, and the recommendation that fits. The benign fixture carries only what applies to a non-incident, an accepted outcome and the requirement of an affirmative no-action-now answer, and names which of its four ambient rows it is reported from; it stays structurally invisible to scenario counting. One loader in the tests' own directory reads both files, the builder that used to expose those loaders on its way to a projection having gone with the projection | Expectations live in two authored files whose fields overlap: `scenarios.yaml` now states accepted outcomes, absent evidence, and the behavior tested, and `golden_scenarios.yaml` states the same ideas under its own names beside the expected cause and required evidence |
| Deterministic replay | `eval/cassettes/inc-005.json`, `eval/cassettes/inc-004.json`, `eval/cassettes/inc-007.json`, `eval/record_investigation.py` | Three committed cassettes, one per recorded incident, each holding every model call of one whole investigation, so the deterministic lane replays real runs rather than scripted calls; one is a run where the analyst asked for more and code granted it, one where it asked for nothing and closed on what it had, and one where the investigator consulted written knowledge and the assessment cited it; the recorder drives the real streaming request, so a recorded response can only be one the replay path would ask for, and refuses to run unless the endpoint and deployment are named; the recording is taken through the Azure adapter against the chat deployment the application calls, keyless as the signed-in identity, so it is evidence about the serving path the application actually takes; the manifest refuses a cassette recorded under a different deployment, reasoning effort, API version, or prompt version, and names the field that moved | Nothing |
| Interaction over a completed record | `api.py`, `investigation/agents.py`, `llm/prompts/record_question.v1.md`, `static/investigation.html` | The application builds the Cosmos store through the factory that already existed, so a record outlives the process and the revision that wrote it; tests substitute through the dependency they already override and no setting chooses between the two. Two ordinary requests over a finished investigation: read one by identifier, and ask about one, which the Supervisor answers in a single call whose only context is that record and which returns the answer, the references it rests on, and optionally a candidate's place in the list the record carries. Code then checks every citation against the record and any position against that list, and a failure of either replaces the answer rather than trimming it. The digest states the citable references on their own lines, because a call asked to quote exactly cannot be left to decide where a reference ends. Nothing is gathered and no record is written; an identifier naming nothing is a clean absence on both requests. The screen gains the question box, shown once a terminal event carries a brief | Nothing |
| One capability over MCP | `mcp/server.py` | `get_deployments` additionally served by an in-process stdio server on the official SDK, dispatching to the same registered capability and returning the envelope it produced without reshaping it. One tool and no other, so every other capability is unreachable through the boundary by construction rather than by a check; a write-shaped or unknown request has nowhere to arrive. The exposure records `transport: mcp` on its span where the investigation records `direct` for the same capability. The server starts and describes itself without a backing store, so the built image can be asked what it offers; the registry is built on the first call that needs one. Nothing starts this in the application, readiness does not probe it, and no HTTP route fronts it | Nothing |
| Azure baseline | `infra/main.bicep`, `.github/workflows` | One Container App, ACR, one OpenAI account with one chat and one embedding deployment, one Cosmos account with the three containers, Log Analytics, scoped data-plane roles, OIDC deploy; readiness asks only that the operational source answer a seeded lookup and that retrieval came up as the configured backend, and the post-deploy smoke run is where a whole hosted investigation is proven | Replicas 0-3 become 0-1; App Insights and built-in auth are absent |

---

## 3. Partial

| Capability | What exists | What does not |
| --- | --- | --- |
| Offline evaluation | `eval/evaluation.py`, `eval/run_evaluation.py`, `tests/test_evaluation.py` | The deterministic half and the runner around it. Correctness reuses the runtime's own gate rather than restating grounding: references resolve in what the run admitted, `what_happened` and every established candidate rest on admitted evidence, no knowledge reference stands as current proof. Read-only is checked from the operations the run actually attempted against the registry. Deliberately absent evidence must be disclosed, truthfully either way it happened: an authoritative absence in the evidence or a limitation where the source could not answer, and silence satisfies neither. Scenario behavior reads the accepted outcome, and the benign fixture additionally requires an affirmative no-action-now entry rather than an empty one. Each check is proven by mutation, so a wiring that could never fail is caught. One runner replays a scenario that has a recording, obtains the benign fixture live against its own constructed incident context, and reports anything else as not run with the reason named, so coverage is stated rather than implied; a live run that cannot complete is reported the same way instead of ending the report, while a replay that fails is left to raise. One report per run, per-scenario results with named failures, no composite score, recording the configuration identity it ran under, written to a gitignored directory | The two controlled comparisons and the evaluation-only injection seam they need; the judge and its rubric; the judge categories in the report |

---

## 4. Missing

Required by the governing design and not present in any form:

- the two controlled comparisons and their evaluation-only injection seam, and the judge;
- Application Insights and the exporter wiring; Container Apps built-in authentication; the
  startup and configuration-validation records.

---

## 5. Superseded: exists only because an earlier design required it

Every item below is reachable in the tree today and conflicts with the governing design. Each is a
named retirement; none is "missing" and none is retained by test coverage or effort spent.

**Numeric evaluation.** Gone. `eval/golden_incidents.json`, `eval/golden_retrieval.json`, and
`data/answer_key/build_goldens.py` are absent, with the sync assertions in
`tests/test_answer_key.py` that read those files; what the builder uniquely held, the loaders six
test modules reached it through, moved to `tests/answer_key.py`, which is where they belong now
that nothing projects a golden set. The scenario and single-agent gates, their harness, their
baselines, and their recorders had already gone: each drove the runtime that no longer exists or
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

Last live-inspected 2026-08-20. One Container App and image from the Bicep template; replicas 0-3;
one chat and one embedding deployment; no Application Insights; the three containers are declared.
The deployment workflow, including its post-deploy smoke run, passes on merge to main; the revision
running now was built and deployed from this branch directly, to prove its hosted effect before the
merge rather than after, with the previous image kept for rollback.

Readiness answers there in its narrowed form: two checks, `operational_records` and `retrieval`,
both ok, with the backend reported as the configured one. The two probes before it timed out at the
client while the scaled-to-zero application started, which is cold start rather than a slow check.

One hosted investigation ran end to end against that revision, through the graph: inc-005, fourteen
activity events, one terminal event carrying a brief and no failure. Because a failed gate spends
the one correction and then fails the execution, a delivered brief is a grounded brief; and because
the save runs before delivery, the record existed before the terminal event. The run reported an
inconclusive outcome, which is a result rather than a failure.

A completed investigation now outlives the process and the revision that wrote it. One record
was written by one revision, then read back by a separate request against the revision that
replaced it, and four questions about it were answered there: every citation each answer rested on
resolved against that record, and two of them named a candidate by its place in the record's own
list. Both requests answer a clean not-found for an identifier naming nothing.

Getting there took a correction the deterministic lane could not have surfaced. The first hosted
questions were refused every time, and correctly: the digest rendered each reference with what it
says beside it, the model quoted the whole line, and the whole line is not a reference the record
carries. The digest now states the citable references on their own lines and the prompt says the
text beside a reference is to read rather than to quote. A test holds the digest to that shape,
but only a real model asked the question that exposed it.

A hosted stream can end with the connection closed and no terminal event, which fails the
deploy's smoke run on a revision that is otherwise healthy. Observed three times, once in CI. In the
case examined the replacing revision logged no request at all for the run that failed, while
readiness had answered moments earlier, so the investigation was begun against the revision being
drained and cut when it went. A run started after the new revision is sole-active completes. This is
recorded rather than fixed: it is the deploy sequence, not the application, and it belongs with the
step that owns hosted posture.

`/version` on that revision reports `environment=local`. `OPSPILOT_ENV` is set nowhere in the
template, so the container takes the default. Nothing keys off it today and no behavior is affected,
but the hosted revision misreports which environment it is.

Retrieval is reached because the investigator chooses it, not because anything privileges it: it is
one entry among nine and nothing orders them. On the recurrence it consulted the runbooks and the
assessment cited four passages, two of them behind actions. On the ambiguous incident it consulted
none and closed on what it had, which is the same conditionality the return has.

The recordings also settled why retrieval had gone unreached, and only part of it was selection. The
offering described arguments and not purpose; the budget was never stated, so calls were spent as
though free and a run ended at the cap rather than when it had enough; and the analyst was never
shown the retrieved passages at all, so no amount of better selection could have produced a
citation. That last one was plumbing.

The governed structured query executes hosted. On the deployed revision one investigation of
inc-004 proposed a structure, validation accepted it, translation bound every value as a parameter,
and the real store answered with nothing, which admission recorded as an authoritative absence
carrying a reference that resolves. Nothing about the path is untried now: the model proposes, code
validates and translates, the store answers, and the answer is citable whether or not it has rows.

Before this, the capability had never executed anywhere. Both recorded runs proposed one and both
were refused for a key the structure does not have, because what a caller was told described the
predicate instead of showing it. The corpus fake cannot answer a translated query either, since it
matches parameters by the field they are named for and a translated one carries positional names,
so the deterministic lane proves translation and outcome mapping directly and the executing path is
proven against the store.

Retrieval is reached hosted, and what it read is carried into the brief. On the revision built
from this landing merged with main, one investigation of inc-007 gathered four times, chose
`search_runbooks` of its own accord as one entry among nine, gathered twice more, synthesized, was
sent back once, synthesized again, grounded, saved, and delivered. Its brief rests partly on
`runbook:service-bus-backlog` and `architecture:service-dependency-map`, and it reported a partial
outcome. The return and retrieval both appear in the same run, which is the first hosted evidence
that neither excludes the other.

A hosted run before that one, on the same tree, chose no retrieval at all and spent its first
assessment on the correction. Both are recorded because both are true: what a model reaches for is
its own to decide, and a step is proven by the behavior being available and correct rather than by
every run exhibiting it.

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
