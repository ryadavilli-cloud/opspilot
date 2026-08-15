# OpsPilot - Status

**Purpose:** record what the repository currently is, against the accepted OpsPilot design. What is
built, what is partial, what still runs only because its replacement has not landed, and what has
been verified.

This document is independent of any execution sequence. It carries no slice, stage, or phase
identifier, no completion ledger, and no notion of what comes next. Capabilities and gaps are named
in architectural and product terms, because that is what survives a resequencing.

The dependency runs one way. `vertical-execution-plan.md` and `horizontal-execution-plan.md` read
this document to decide ordering, dependencies, migration mechanics, and how gaps map to work. This
document does not read them, and nothing here changes because a plan implies it should.

`requirements.md`, `architecture.md`, `system-design.md`, `workflow-design.md`,
`data-and-evidence.md`, `runtime-and-deployment.md`, and `evaluation.md` own the accepted design.
This document never restates intent; it records what exists against it.

A statement changes only where the repository contradicts it.

---

## 1. Current repository baseline

- **Inspected:** branch `worktree-opspilot-session` at `e5f3a93`, 2026-08-15.
- **Toolchain:** `uv` for everything. Python 3.12.
- **Enforced on every change:** formatting, linting, strict type checking, tests, and repository
  hygiene, through continuous integration and local hooks. `code-guidelines.md` holds the governing
  rules; the workflow and `pyproject.toml` hold their realization. Coverage is not identical between
  the two, and continuous integration is the authority.

---

## 2. Implemented capabilities

Each row below was read in the repository, not inferred from a plan.

| Capability | Where | What holds |
| --- | --- | --- |
| Turn and investigation identity | `turn/identity.py` | Both identities are minted together and carry the incident under study beside them |
| Streaming turn transport | `POST /turns`, `stream/contracts.py` | One streaming HTTP request owns one turn: the two identities as its first event, activity as it happens, then a closing event. An ordinary streaming body, with no create-then-attach pair, no reconnection, no event buffering, and no sequence cursor |
| Activity projection | `stream/projection.py` | Built at the same call site that opens the telemetry span, from the same explicit facts, so the two cannot drift. No parameter exists through which raw span attributes could reach a projected event |
| Predefined intake normalization | `intake/contracts.py`, `decisions.md` D-007 | The typed, frozen normalized incident context, carrying exactly five fields and deliberately excluding the source record's answer-bearing and ticket-workflow fields. Free-text intake does not exist |
| Evidence reference model | `evidence/references.py`, `decisions.md` D-008 | One parser, one resolver, and one prefix-to-type map over the evidence and knowledge prefixes, including the form that makes an authoritative empty result citable |
| Two-axis capability results | `tools/contracts.py` | Whether an operation executed and how complete its answer was are separate axes, with the legal pairings enforced where the envelope is constructed, so an illegal pairing cannot exist to be read. A source that answered with nothing stays distinguishable from one that did not answer |
| Evidence admission | `evidence/admission.py`, `evidence/operations.py` | The only door into the evidence set: it admits a successful result, assigns its reference, and produces a limitation naming the unanswered question for everything else. The operation ledger is kept separately, with turn-scoped opaque references outside the evidence grammar |
| Read-only operational capabilities | `tools/`, `data/operational_records.py` | Read the operational-records container through the registry with validated parameters and an explicit deadline. A request naming no deadline is refused at dispatch, and a container that cannot answer reports unavailability rather than a generic error |
| Governed structured query | `data/structured_query.py`, `tools/structured_query.py` | A bounded structure over an approved surface of three collections, validated before anything executes, translated into one parameterized read-only query, and admitted through the same two axes as any other capability. No query text is constructed from caller input; grouping, ordering, joins, writes, and non-count aggregates have no representable form |
| Assessment contracts | `assessment/contracts.py` | A candidate set with three qualitative support labels, supporting and weakening references per candidate, established-or-possible markers, recommendations carrying one horizon and one provenance category, and recorded limitations. No numeric confidence exists anywhere in the assessment or its projection |
| Model-proposes, code-admits synthesis | `assessment/synthesis.py`, `llm/prompts/rca_synthesis.v1.md` | One bounded, task-labelled model call proposes an assessment; deterministic code admits it against the admitted evidence set, dropping any reference the turn never admitted and any candidate left without support, and deriving the conclusion disposition from the evidence rather than from the model's assertion about itself |
| Deterministic brief projection | `assessment/brief.py` | The brief is a traversal of the assessment, introducing nothing it does not hold and dropping nothing it does, including weakening evidence |
| Investigation Record port and commit ordering | `record/port.py`, `record/memory.py` | The commit success and failure contract, and the rule that a successful result is never delivered before it is persisted, expressed in one place where delivery is unreachable on a failed commit. The backend is in-memory: it refuses a second commit of the same turn and creates the investigation only on the first successful one |
| Telemetry emission seam | `obs/` | One seam emitting at shared primitives with correlation identifiers, contextvar-nested parents, a swappable exporter, and an in-memory fixture for deterministic assertions. Capability, model, and admission operations emit through it |
| Offline corpus preparation | `scripts/prepare_corpus.py` | A separate task with its own identity that loads, chunks, embeds, and indexes the authored corpus into the containers the runtime reads, and verifies by reading back what it wrote. It participates in no turn |
| Deterministic replay | `eval/cassettes/turn_synthesis.json` | A committed cassette keeps synthesis reproducible without a live model, exercised end to end from a recorded incident through to a rendered brief |

---

## 3. Partially implemented and missing capabilities

| Capability | State | What exists, and what does not |
| --- | --- | --- |
| Explicit turn controller | Missing | No stage sequence exists. The streamed path is a linear generator, not a state machine with transitions. Turn identity exists and is the one input it would consume |
| Supervisor, Evidence Investigator, RCA Analyst as distinct roles | Missing | Synthesis exists as a module that reaches no capability, which is the structural half. No role separation, no objective ownership, no continuation authorization. The superseded planner still both gathers and concludes |
| Observation-driven evidence selection | Missing | The evidence path is a fixed deterministic plan bounded by a window and a service count (`turn/synthesis_step.py`). Adaptive source selection does not exist |
| Grounding gate, correction allowance, completed outcomes | Missing | No four-check gate, no correction allowance, no outcome vocabulary. `guardrails/policies.py` holds an unrelated two-policy citation check belonging to the superseded runtime |
| Completed-turn artifact | Missing | The record port is structural over anything carrying the two identities, and deliberately does not define the artifact. Nothing carries terminal outcome, stop reason, admitted evidence, assessment, limitations, or a version stamp as one object |
| Durable completed-turn persistence | Missing | In-memory backend only. No runtime path calls the commit ordering, so the property holds today only where tests drive it |
| Explicit cancellation signal | Partial | Client-disconnect detection exists and is checked before each further unit of work, abandoning the turn without persisting. No cancellation request surface, no control in the client, and no map from turn identity to a signal |
| Brief rendering in the client | Partial | The screen carries intake, the activity feed, a brief region, and one expandable details area. It handles the identity, activity, and closing events and has no branch for the brief, so a rendered brief arrives and is visible only in the details area |
| Free-text normalization and clarification | Missing | Predefined intake only. No clarification path of any kind exists |
| Follow-up, redirect, supplied context, handoff | Missing | The five-kind interaction type exists as a type (`intake/contracts.py`). No classifier produces it and no retained-state answering exists |
| Accepted retrieval | Partial | The superseded lexical, dense, and model-reranker stack is gone (`retrieval/index.py`, `adapters.py`, `factory.py`, `bm25.py`); no local embedding model is loaded anywhere. Retrieval reads the prepared `knowledge` container: dense search via Cosmos `VectorDistance()` over an Azure OpenAI query embedding, an in-process BM25-style lexical scorer over the same category-filtered candidates, and reciprocal rank fusion, over section-level passages carrying the matched text itself rather than a pointer. A request may name its collection or leave it unnamed, in which case routing selects one from the question's shape. Deterministic identifier and time-window promotion after fusion (D-003's reranking step) does not exist yet; the passage budget is not yet the only truncation |
| Single accepted protocol exposure | Missing | The boundary exposes three superseded capabilities (`get_incident`, `query_logs`, `search_runbooks`, `mcp/server.py`) rather than the one the design names |
| Further-evidence cycle | Missing | No representation exists anywhere in the source tree, including on the assessment |
| Categorical evaluation, judge, baselines, report | Missing | Golden scenario records and cassette replay exist as inputs. Scoring is still numeric and gate-shaped |
| Hosted composition alignment | Missing | See section 6 |

---

## 4. Temporary legacy and coexisting implementation

Everything below still runs and is superseded rather than retained. Each is reachable, so each is
still a way to obtain behavior the accepted design assigns elsewhere.

| Component | What it still serves | Superseded by |
| --- | --- | --- |
| Graph orchestration and its nodes, routers, and checkpointer (`graph.py`, `nodes/investigation.py`, `router.py`, `checkpoint.py`) and the `langgraph`, `langchain-core`, and `langgraph-checkpoint-sqlite` dependencies | The superseded pipeline behind `/investigate` and the job API | The explicit turn controller |
| Job API: create-then-poll transport, decision endpoint, committed decisions, leases and fencing (`api.py`, `investigations.py`, `cosmos_investigations.py`) | The superseded turn lifecycle | The streaming request and the completed-turn artifact |
| Approval console (`static/console.html`) at `/console` | Submit, poll, review, and approve, including a numeric confidence rendering | The one-screen client |
| Report and claim model (`contracts.py`, `diagnosis/{admission,cycle,llm_planner,planner,sufficiency,render}.py`, `triage.py`, `composition.py`) | The superseded report object, the fused planner that both gathers and concludes, and implementation selection between a planner and a triager | The assessment contracts and the role separation |
| Two-policy grounding (`guardrails/policies.py`) | A citation check ahead of the superseded approval gate | The four-check grounding gate |
| Hand-rolled three-role authorization (`auth.py`, `pyjwt`) | Guards the superseded endpoints only. `POST /turns` is unauthenticated | Platform built-in authentication |
| Numeric evaluation thresholds (`EvalTargets`, `config.py`) | Read by `eval/scenario_eval.py` and the scorecard gates | Categorical scoring |

---

## 5. Data and evidence state

| Subject | What holds | Established by |
| --- | --- | --- |
| Authored corpus and repairs | Seven incidents (`inc-001` through `inc-007`) across five families, verified against `data/answer_key/scenarios.yaml`. Chronology and answer-leakage repairs have landed: a referenced series must move toward its own authored direction, and no log message or deployment note may name an incident identifier or announce its narrative role. Reference closure holds across the corpus | `tests/test_telemetry.py`, `tests/test_closure.py` |
| Golden scenario records | One record per authored incident, authored beside the answer key rather than projected from it (`data/answer_key/golden_scenarios.yaml`). Every reference a record requires resolves in the corpus; evidence the corpus deliberately lacks is held as prose so it cannot be read as a reference. Every record carries all eight required parts, and its classes and outcome shapes come from the accepted vocabularies | `tests/test_golden_scenarios.py` |
| Scenario class coverage | All five classes are represented: the multi-contributor class by an authored incident whose golden record requires two independently evidenced conditions, the benign or transient class by a controlled non-incident fixture derived from the ambient events, structurally invisible to scenario counting and carrying no golden record (`data/answer_key/benign_fixture.yaml`). The audit that established coverage was performed 2026-08-09 and recorded one row per scenario class. No test asserts full class coverage; the two classes whose representation could be faked are asserted individually | Audit performed 2026-08-09. Multi-contributor: `tests/test_golden_scenarios.py`. Benign distinctness: `tests/test_benign_fixture.py`. Full-coverage assertion: not asserted anywhere |
| Corpus preparation idempotence | A re-shaping produces identical passage ids and identical extracted identifiers, asserted deterministically. Seeding is by upsert, so a re-run converges rather than failing on the second pass; after a partial run on 2026-08-10, a re-run left both live containers byte-identical to a fresh shaping, verified by read-back. No gate asserts the live half | Shaping: `tests/test_corpus_preparation.py::test_extraction_is_stable_across_runs`. Seeding and read-back: `scripts/prepare_corpus.py` (`seed()`, `--verify-only`) |
| Corpus writer identity | The application identity holds contributor rights scoped to `investigations` alone and reader rights across `retailease`; corpus preparation writes as a different principal holding contributor on `retailease` only, so the setup identity is the only writer to the knowledge and operational-records containers. Declared in the template rather than granted by hand. No automated check asserts the refusal yet | `infra/main.bicep` data-plane role assignments (`cosmosDataContributor`, `cosmosDataReaderRetailEase`, `cosmosDataContributorCorpusSetup`); live-inspected 2026-08-11 |
| Open corpus quality item | Generated error telemetry is templated: 915 error rows carry only 10 distinct messages, one of them repeated 905 times, and there is no pre-incident baseline history | Measured 2026-08-13 against `data/synthetic/logs.jsonl` |
| Cosmos data plane | `retailease/knowledge` holds 196 passages from 28 documents under a 1536-dimension vector policy. `retailease/operational-records` holds 14,013 documents across six kinds, hierarchically partitioned. Both are read by the accepted capabilities. `opspilot/investigations` is declared and empty; nothing writes to it, because the artifact it would hold does not exist | Live-inspected 2026-08-11; not re-verified since |

---

## 6. Runtime and deployment state

**Last live-inspected 2026-08-09; not re-verified since.** Deployed and green, at the superseded
composition.

- One Container App and one image, built and deployed by one OIDC workflow from the Bicep template.
- Replica range is 0 to 3 in the template (`infra/main.bicep`), against an accepted 0 to 1.
- One chat deployment (`gpt-5-mini`) and one embedding deployment (`text-embedding-3-small`). The
  accepted composition names a second, lower-cost chat deployment that does not exist.
- No Application Insights resource.
- The hand-rolled three-role authorization fronts the superseded endpoints. Platform built-in
  authentication is not configured.
- The template declares the knowledge, operational-records, and investigations containers. Nothing
  declares or recreates the retired checkpoint and index containers.

---

## 7. Current verification state

Both lanes measured at `e5f3a93`, each run after syncing exactly its own dependency groups.
No test now depends on the `eval` group: retrieval no longer loads a local embedding or reranker
model on any path, so Core and Full run the identical, unskipped test set.

| Lane | Command | Result |
| --- | --- | --- |
| Core | `uv sync --group dev --group data`; `ruff check .`; `mypy`; `pytest -q -m "not llm"` | lint clean, strict type check clean, **696 passed, 3 deselected, 2 xfailed** (32.3s) |
| Full | `uv sync --group dev --group data --group eval`; `pytest -q -m "not reranker and not llm"` | **696 passed, 3 deselected, 2 xfailed** (34.2s) |

Formatting is clean repository-wide, and is checked repository-wide rather than over the files a
change touches. The plan-vocabulary check passes over the whole tree outside `docs/`, excluding the
superseded modules named in its own exempt list. `az bicep build` was not re-run this pass; no
`infra/` file changed.

**Two disclosed regressions carried as xfails**, both in both lanes.
`tests/test_single_agent_gate.py::test_single_agent_beats_the_deterministic_floor`: the corpus
repair added metric evidence the deterministic fixed plan sweeps incidentally and the superseded
planner does not request, so it no longer strictly beats that floor. Its subject is superseded
machinery, so the resolution is deletion rather than repairing the planner's tool selection.
`tests/test_single_agent_gate.py::test_single_agent_replay_reproduces_committed_baseline`: the
retrieval rewrite changed what `search_past_incidents` returns, which the triager's prompt embeds
verbatim (`triage.py::_render_candidates`), so the recorded cassette's request hashes no longer
match and replay cannot reach the committed `single_agent` baseline without a live re-recording.
Its subject is the same superseded planner; re-recording is deferred rather than performed here.

Nothing in the deployed environment was verified in this pass. Sections 5 and 6 carry their own
inspection dates.

---

## 8. Known gaps and unresolved issues

**One open decision.** `decisions.md` D-004, the protocol library and its realization, is still
pending library inspection. It blocks the single accepted protocol exposure and nothing else. Every
other decision record is accepted, and no contradiction was found between `decisions.md` and the
repository.

**One open question with no decision record.** If free-text intake clarifies through a short-lived
normalization token, that token needs an explicit signing, expiry, and payload contract; a simpler
resubmission path is preferred where it meets the requirement. Nothing in the repository takes a
position, because no clarification path exists, so the absence of a token is not evidence that the
simpler path was chosen. It blocks free-text intake and nothing else.

**Comments describing something that is no longer true.** Four of these, in three modules, all of
the same class: a comment that was accurate when written and that nothing re-reads when the thing
it describes changes.

`turn/identity.py` cites this document by section number, which cannot resolve and is not how this
document is cited. `tests/test_answer_key.py` cites a heading that no longer exists. The remaining
in-code references name the document without a heading and still resolve, so they are not defects.
Neither module carrying a stale citation is superseded, so nothing removes either as a side effect.

`api.py` calls the assessment and brief a stub in two places, which stopped being accurate when real
synthesis and admission landed. The second is the more misleading, because it justifies why there is
no operation to interrupt mid-flight, and that claim shaped how cancellation was scoped. Both sit in
a superseded module, so both leave with it.

**Untracked local configuration.** `.claude/settings.json` and `.claude/settings.local.json` are
untracked and unignored, so they appear in every `git status`.
