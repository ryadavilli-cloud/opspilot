# OpsPilot Horizontal Execution Plan

Nine steps that build the final technical system layer by layer, bottom up by dependency, from the
repository as `docs/status.md` describes it to the system the governing design describes.

## How this plan works

- **Sequencing.** Each step completes a technical capability, or the declared portion of one, before
  work that depends on it begins. Completion means the final designed capability, not a framework
  around it.
- **Same destination.** Executing this plan to completion produces exactly the repository, runtime,
  persistence, MCP boundary, evaluation, hosted deployment, and retired code that
  `docs/vertical-execution-plan.md` produces. The two plans differ only in sequencing.
- **Eligibility.** A step is eligible because everything it consumes exists in the current
  repository, as `docs/status.md` and inspection show. Not because the step before it ran. Before
  starting: read the step, read `status.md`, inspect the code it touches, verify every Consumes
  line. If one is missing, stop and report; do not build it.
- **One step, one PR.** A step is as large as is logically coherent and no larger. Split only for a
  real prerequisite, an independently risky migration, a deployment boundary, or reviewability.
- **Deletion first.** Every "if present, remove" line names implementation the step's replacement
  makes obsolete. Remove it in the same PR. If a Vertical landing already removed it, the absence
  is the correct no-op.
- **Hosted effect.** Each step is None (no hosted change, no ceremonial deploy), Data (publish and
  verify changed corpus, database, or vector state), Application (deploy the application and prove
  the changed hosted behavior), or Infrastructure (deploy changed Azure or runtime configuration
  and prove it).
- **Verification.** `docs/code-guidelines.md` owns the standing gates; each step states only the
  proof unique to it.
- **After a landing.** In the same PR, preferably as a trailing documentation commit: update
  `docs/status.md` first to repository truth; then re-evaluate this plan and the Vertical plan and
  change only the steps whose completion condition now holds, partly holds, or no longer holds. A
  step is Not started, Partial (Already present / Remaining), or Complete. Complete means the
  repository provides what the step promises and its named obsolete implementation is absent. Do
  not redesign unrelated future steps during bookkeeping; if a landing proves a future step wrong,
  report it.
- **Vocabulary.** Step identifiers, requirement and decision identifiers, document section numbers,
  and migration terms stay out of source, comments, tests, configuration, branches, commits, and PR
  titles and descriptions. Say what the code does and why, technically.

---

## H1. Evidence foundation

**State:** Complete.

Everything this step builds and every removal it names holds, as `status.md` records, and the
hosted proof has run: a deployed investigation admitted through this code and delivered a brief
whose every citation was assigned by admission. `incident:` and `query:` were exercised against the
real corpus rather than hosted, because the streaming request's fixed evidence plan reaches neither
capability; they become reachable hosted when the Evidence Investigator chooses what to call.

**Builds.** The final evidence contract, end to end below the agents. The reference grammar gains
the three evidence forms the design fixes for alerts, the incident record, and aggregate query
results (`alert:<service>:<alert_id>`, `incident:<incident_id>`, `query:<operation>`), parsed and
resolved by the one parser and one resolver alongside the existing forms. Admission returns plain
values: admitted observations, limitations, and the operations list, each operation carrying its
identifier, capability, and outcome, all keyed by `investigation_id`. The two-axis tool result keeps
its one pairing enforcement point, as an inline rule if that is smaller than the table. Operational
adapters take typed parameters instead of per-capability request models, and the registry validates
those parameters. The incident record is admitted only in the fields the approved structured-query
surface exposes; its cause and resolution text never leaves the adapter. A structured-query row
carries the reference of the record it projects, formed from identifying fields every projection
includes; a count carries the `query:` reference of its operation; an empty result carries an
`absence:` reference as today.

**Consumes.** The operational-records adapters, the reference parser and resolver, admission, the
governed structured query, and the two-axis result as `status.md` records them.

**Provides.** Admitted operational evidence with a citable reference for every observation any
capability can produce, an operations list with stable identifiers, and typed capability calls.

**If present, remove.** The eight per-capability request models; `legacy_status()`; `DocHit`;
`AuthoritativeAbsence`, `AdmissionResult`, `Resolution`, `OperationRecord`, `OperationLedger` as
classes; `turn_id` on the evidence set; the pairing-table tests in
`tests/test_evidence_admission.py`; the three superseded MCP tool exposures in `mcp/server.py` and
their parity test, which depend on the request models and are replaced by the final MCP step.

**Proof unique to this step.** An alert observation, an incident-record observation, a query row,
and a query count each admit with a reference that parses and resolves; an incident-record
observation contains no cause or resolution field; a projection over any approved collection returns
the identifying fields needed to form each row's reference; the operations list identifies every
attempted call including failed ones.

**Hosted effect: Application.** The streaming path in the deployed application admits through this
code. Deploy and run one hosted investigation; every citation in its output resolves.

**Complete when** every capability's result admits with a citable reference, admission returns plain
values, adapters take typed parameters, and the named wrappers and superseded exposures are absent.

---

## H2. Retrieval, final

**State:** Complete.

Everything this step builds and every removal it names holds, as `status.md` records: stable
promotion of passages whose extracted identifiers the question names, running over the whole fused
list and followed by truncation to the passage budget; one passage shape on the runtime path, with
corpus preparation's own shapes reaching nothing outside preparation; a retrieval that cannot
execute admitted as a limitation and no passage, while a successful one produces knowledge rather
than an operational observation. The reranker module, its dependency, the marker, and the CI lane
that existed to install that dependency are absent.

The deployed application runs this code and reaches the knowledge container through it. The
ordering itself was proven against the authored corpus rather than hosted, because no route returns
retrieval results for a hosted call to inspect. It is observable now that the Evidence Investigator
proposes retrieval inside an investigation: a recorded run of the recurrence consults the runbooks
and the assessment cites what it read.

**Builds.** The final retrieval behavior over the knowledge container: embed the question, vector
search plus the in-process lexical pass over the same category-filtered candidates, reciprocal-rank
fusion, then deterministic promotion of passages whose extracted identifiers match identifier-like
terms in the question, then truncation to the small passage budget. One passage shape carrying text
and reference replaces the three current shapes. Retrieval is a registered capability: its passages
join the knowledge set rather than passing through operational admission, a retrieval that fails,
times out, or is unavailable becomes a limitation, and the retrieval adapter in `tools/search.py`
returns that shape.

**Consumes.** The retriever, embeddings client, and knowledge-records access as `status.md` records
them; the admission and reference behavior of the evidence foundation for the limitation path.

**Provides.** Final retrieval: hybrid ranking with exact-identifier promotion, one passage shape,
knowledge-set semantics, limitation on failure.

**If present, remove.** `retrieval/reranker.py`, `CrossEncoder`, `RERANKER_MODEL`,
`RERANK_CANDIDATES`, the `reranker` pytest marker, `sentence-transformers` and its transitive
`torch`, `transformers`, `scikit-learn`, `scipy` in the eval dependency group, and the `full` lane
in `.github/workflows/deploy.yml` that exists to install that group; the `Doc`/`Chunk`/`Passage`
multiplicity.

**Proof unique to this step.** A passage whose extracted identifier exactly matches a service name,
error code, or deploy identifier in the question is promoted ahead of otherwise higher fused
results; fused order is unchanged when no identifier matches; a retrieval that cannot execute
yields a limitation and no passage.

**Hosted effect: Application.** Deploy; a hosted retrieval for a query containing an exact
identifier returns the promoted passage first.

**Complete when** the promotion path exists, one passage shape is used everywhere, retrieval
failure is a limitation, and the reranker implementation, dependencies, marker, and lane are absent.

---

## H3. Assessment, synthesis, grounding, and the brief

**State:** Complete.

The assessment is the designed field set; synthesis is structural only and refuses an unusable
proposal rather than thinning one; one grounding function returns issues over the assessment, the
admitted evidence, the retrieved knowledge, and the recorded limitations; the brief renders
deterministically with the outcome, contributing causes where more than one candidate is
established, and no probability. The synthesis prompt is the new proposal shape. The model seam is
one Azure adapter with the fake and the cassette, and the cassette is recorded through it. The
assessment types, the grounding contract layer, the semantic filtering, the `model_construct()`
scaffolding, and the removed provider branches are absent. The hosted effect has run: a deployed
investigation delivered a brief with the designed sections and no probability. See
`docs/status.md`.

**Builds.** The final assessment-producing capability as pure functions, called by the graph later
without change. The assessment shape becomes the designed field set once: `what_happened`, ordered
`candidates` (statement, label, established, supporting, weakening), `unknowns`, `limitations`,
`next_check`, `actions` (action, now, optional `knowledge_ref`, with an affirmative
no-immediate-action entry where the evidence supports it), `history`, `knowledge_used`; the model's
proposal is that shape as loose strings plus the optional `unresolved_question`, routing metadata
whose matter also appears in `unknowns`. Synthesis becomes structural only: parse, normalize
representation, reject malformed structure or a syntactically impossible reference, never remove a
candidate, derive `established`, or discard an action. Grounding becomes one function returning
zero or more issues over the admitted assessment, admitted evidence, retrieved knowledge, and
limitations, enforcing the designed properties: operational-support references resolve in admitted
evidence and knowledge references (including an action's `knowledge_ref`) in retrieved knowledge;
no knowledge reference where operational support is required; `what_happened` and every
established candidate have admitted operational support; every recorded limitation is disclosed. The
brief renders the assessment deterministically: contributors when more than one candidate is
established, the affirmative no-action entry as such, the outcome, no probability. The model seam
reduces to one Azure adapter, one fake, and cassette record and replay, with the synthesis cassette
re-recorded against the new proposal shape.

**Consumes.** The current synthesis and grounding functions, brief renderer, model seam, and
cassette as `status.md` records them; the evidence foundation's admitted values and references.

**Provides.** The final assessment contract, structural synthesis, the grounding function, and the
brief renderer, ready to be called from an orchestrator.

**If present, remove.** `SupportRelationship`, `Horizon`, `RecommendationKind`,
`RecommendationProvenance`, `ConclusionDisposition`, `BriefSection`, `Citation` as a model,
`GroundedElement`, `HistoricalComparison`, and the validators that duplicate the gate; the semantic
filtering in `assessment/synthesis.py` (`_grounded`, the drop-if-unsupported and
derive-`established` branches of `_candidate`); `CheckName`, `CheckResult`, `GroundingResult` and
its exact-set validators, `CorrectionAllowance`, `GateRouting`, `route_grounding_result`; the eleven
`model_construct()` sites in `tests/test_grounding_gate.py` and the tests that exist only to
exercise them; the Ollama and generic-OpenAI branches with their endpoint and key settings, and
`LLM_SEED`; the `llm` marker's provider text. The response models in `llm/schema.py` are not
removed here: the legacy diagnosis path still imports them, and they are retired with it.

**Proof unique to this step.** A proposal with an unsupported candidate reaches the gate unchanged
and the gate reports the issue; `what_happened` without operational support is an issue; a
knowledge reference offered as current support is an issue; a limitation the assessment omits is
an issue; a clean assessment yields zero issues; the brief adds nothing and drops nothing; two
established candidates render as contributors.

**Hosted effect: Application.** The deployed stream renders the new brief shape. Deploy and confirm
one hosted investigation delivers a brief with the designed sections and no probability.

**Complete when** the assessment is the designed shape, synthesis is structural only, one grounding
function returns issues, the brief renders as designed, the model seam is Azure-only, and the named
contract layer, oversized models, filtering, and provider branches are absent.

---

## H4. Completed-investigation persistence foundation

**State:** Complete.

`CompletedInvestigation` carries the contents the design lists, the seam is `save` and `get`, and
both backends stand behind it: the in-memory one narrowed to those two operations, and a Cosmos one
over the declared container keyed by `investigation_id` with a plain create. Both normalize through
the stored document, so a record reads back with the same contents whichever is behind the seam and
a second save is refused by either. `azure-cosmos` is a base dependency. The plural-turn
persistence types are absent. This step built the seam unconnected; the investigation run now
writes through it before it delivers. See `docs/status.md`.

**Builds.** The final persistence seam, unconnected to any runtime path yet. One
`CompletedInvestigation` carrying what the design lists: identity, incident, objective, outcome and
why gathering stopped, admitted observations and limitations, the operations list (identifier,
capability, outcome per operation), retrieved passages with references and text, the assessment,
the brief, the telemetry correlation reference and model and prompt versions. One repository seam
with `save` and `get`; the in-memory implementation narrowed to that; a Cosmos implementation over
the `investigations` container keyed by `investigation_id`, one plain create per record. The
`azure-cosmos` dependency moves from the `checkpoint` group into the base dependencies so every
Cosmos read and this repository run from the runtime image; nothing else in that group changes
here.

**Consumes.** The final assessment and brief shapes; admitted values, limitations, and the
operations list; the in-memory record backend and Cosmos access as `status.md` records them; the
declared, empty `investigations` container.

**Provides.** `CompletedInvestigation`, `save`/`get`, in-memory and Cosmos repositories, ready for
the graph's persist step and the record readers.

**If present, remove.** `CompletedTurn`, `completed_turns()`, `turn()`, `CommitOutcome`,
`CommitResult`, `DeliveryOutcome`, `commit_then_deliver()` in `record/port.py`; the plural and
delivery-ordering cases in `tests/test_record_commit.py`. The async job repositories
(`investigations.py`, `cosmos_investigations.py`, `repository.py`) stay until the runtime that calls
them is replaced in H5.

**Proof unique to this step.** A saved record reads back byte-equal through both repositories; a
second save of the same identifier is refused; a saved record's operations list includes failed
operations; every reference in a saved record resolves against the record's own evidence and
passages.

**Hosted effect: None.** No runtime path writes yet; the base dependency change alters no hosted
behavior. No deployment for ceremony.

**Complete when** the model, seam, and both repositories exist as designed, `azure-cosmos` is a
base dependency, and the plural-turn persistence types are absent.

---

## H5. The three-agent graph and the runtime it replaces

**State:** Complete.

*Already present.* The graph, the three roles, the five bounds, deterministic authorization,
grounding with one correction, the outcome rule, the failure categories, persist-before-deliver,
and the streaming request under investigation-only vocabulary. Every module, route, setting,
dependency, override, and test this step names for removal is absent, and the strict-override list
is gone entirely rather than shortened. The dormant checkpoint and asynchronous-job
configuration went with the runtime that read it: no setting, template parameter, or container
environment entry can select a durable intermediate store. Evidence access carries the run's own
remaining time, bounded by the configured source ceiling, so no source read outlives the
investigation that asked for it.

The return is built, followed, and observed hosted. The analyst names what it could not settle and
the kind of evidence that would settle it; the Supervisor grants a return only on an unspent bound,
a kind a proposable capability supplies, a question this run has not already put, and a budget that
affords the resumed proposal, the second synthesis, and the correction that synthesis may still
need. It is demonstrated on a recorded real model rather than on a predicted incident, because
which incident a model finds unsettled is the model's to decide. Spending `return_used` sets a
field on nested state in place, as the one correction already does; that is the pattern to stop at
rather than extend, and the graph is not to be restructured to avoid the one that exists.

Each capability says what it answers, on itself, and the offering the investigator chooses from is
rendered from that alongside the arguments it already carried. The investigator is told how many
calls it has left, which the runtime always claimed it could see and could not: without it a run
spent its budget as though calls were free and ended at the cap rather than when it had enough. The
analyst is shown the passages the run retrieved, and names the guidance that shaped an action.

Every registered capability is proposable, and the separate list of proposable ones is gone rather
than maintained beside an identical inventory. Retrieved passages are held beside the evidence set,
never inside it, and reach both roles as context, the gate as its second reference set, and the
completed record. A knowledge reference is real because this investigation retrieved the passage it
names: the resolver decides that against the run's knowledge set, and against the passages the
completed record carries when the record is what is being read, never by looking for an authored
file, because the runtime image ships no corpus and the knowledge the runtime searches lives in the
knowledge container. Whether every authored file exists and every reference in it closes stays a
corpus-preparation and closure concern, offline and separate.

The hosted effect is taken. The revision built from this landing serves the designed runtime, and
one investigation of inc-005 against it gathered, synthesized, grounded, saved, and delivered a
brief with an inconclusive outcome and no failure. What that run also shows is that the
investigator works down the offering rather than selecting from it: the capability cap is spent
before analysis is reached, neither retrieval capability is proposed, and two calls are refused at
the boundary rather than executed. That is a selection problem and not a bound to raise; it is
recorded in `status.md` as one finding and it is the charter of the step that makes retrieval
influential, not a remaining build here.

**Builds.** The designed runtime, and the removal of the one it supersedes. One small compiled
in-process graph over typed investigation state, no checkpointer: set objective, gather with
deterministic continuation, synthesize, ground, persist, deliver, and one conditional return from
synthesize to gather. The Supervisor interprets the four-field incident context (`incident_id`
required, `scope`, `symptom`, `time_anchor`) into an objective in one model call and sets the five
bounds: deadline, capability-call cap (retrieval counts), model-call cap, `correction_used`,
`return_used`. The Evidence Investigator proposes one registered capability with arguments and the
question it expects answered, choosing from the incident, objective, admitted evidence, and
retrieved knowledge; that includes proposing a bounded structured-query structure that code
validates and translates. Once every registered investigation capability is eligible for
proposal, the separate list of proposable capabilities is removed rather than maintained beside
an identical one; it is not replaced by a capability-descriptor layer, and no extensible registry
is built ahead of the MCP boundary, which can use the direct implementation mapping that already
exists. The Supervisor authorizes each proposal deterministically (registered,
question not already answered, cap and deadline have room), evidence access executes with the
remaining deadline, admission runs, and gathering ends when the investigator reports ready or no
useful permitted action, or a source the objective depends on is unavailable, or a bound is
reached. The RCA Analyst synthesizes in one call; the return happens at most once when
`unresolved_question` names an evidence kind a registered capability supplies and the bounds have
room; if the return is unavailable or spent the edge is not followed and the assessment is not
edited. The grounding function runs; a non-empty issue list or a structurally unusable proposal may
spend the one correction; the outcome follows from established candidates and recorded limitations
(none established: inconclusive; established with a limitation: partial; established without:
complete). Failed execution covers zero admitted operational observations at the end of gathering,
an unusable proposal or issues after the correction, a failed save, the deadline expiring before a
trustworthy brief, or an unhandled error; it persists nothing and emits a sanitized failure
category. The completed investigation is saved through the repository seam, then the terminal
event carries the brief and outcome. One streaming request mints `investigation_id`, runs the graph,
streams activity events built at the tracing span sites (agent or capability acting, what it did
and obtained, why gathering continued or stopped, the return, the grounding result, persistence,
terminal outcome or failure), correlated by `investigation_id` alone, under investigation-only route
and identity vocabulary; the screen shows the brief as the dominant element when the terminal event
arrives.

**Consumes.** The evidence foundation; final retrieval as a registered capability; the final
assessment, synthesis, grounding, and brief; the persistence seam; the tracing seam and activity
projection, model seam, and streaming page as `status.md` records them; the four-field intake
contract's current shape.

**Provides.** The designed investigation running end to end in the streaming request: three
model-directed roles under deterministic control, bounded, grounded, persisted before delivery,
observable.

**If present, remove.** The superseded orchestration: `graph.py`, `nodes/investigation.py`,
`router.py`, `checkpoint.py`, `state.py`, `hitl_gate`, `apply_edit`, `escalate`, the `postmortem`
path, `traced_node`; `langgraph-checkpoint-sqlite`; `langchain-azure-cosmosdb`; the emptied
`checkpoint` dependency group and the Dockerfile's `--group checkpoint` on both `uv sync` lines and
the `CMD`. The async job, approval, and polling path: `investigations.py`,
`cosmos_investigations.py`, `repository.py`, the `/investigations`, `/investigations/{id}/decision`,
and `/investigate` routes and helpers in `api.py`, `CommittedDecision`, idempotency, leases,
fencing, outbox, job-status vocabulary, publication identity, the approval-bound report hash. The
legacy diagnosis path: root `contracts.py`, `diagnosis/` (nine modules), `triage.py`,
`composition.py`, `guardrails/policies.py`, the planner, claim, report, triage, and tool-call
response models in `llm/schema.py` and `tests/test_schema.py`, the `OPSPILOT_IMPLEMENTATION`
setting and selector code, the explicit `langchain-core` dependency. The fixed synthesis path:
`turn/synthesis_step.py` and the stub-backed branch of the streaming route in `api.py`.
Hand-rolled authorization code: `auth.py`, `ReviewerPrincipal`, `pyjwt[crypto]`, and the
`OPSPILOT_API_AUDIENCE` and `OPSPILOT_APPROVER_ROLE` settings. The console:
`static/console.html`, `/console`, `/console/config`, the `OPSPILOT_CONSOLE_CLIENT_ID` setting.
Plural-turn identity: `turn/identity.py`, `TurnIdentity`,
`turn_id` on spans and stream events, the close marker folded into the terminal event. Intake
residue: `InteractionKind`, `supplied_context`, the optionality of `incident_id`. Their tests:
`test_investigations_api.py`, `test_investigations.py`, `test_repository_factory.py`,
`test_report_binding.py`, `test_checkpointer.py`, `test_auth.py`, `test_triage.py`,
`test_triager.py`, `test_composition.py`, `test_sufficiency.py`, `test_planner_seam.py`,
`test_diagnose.py`, `test_llm_planner.py`, `test_state.py`, `test_state_contract.py`,
`test_conclusion_contracts.py`, `test_conclusion_wiring.py`, `test_cycle_onset_clamp.py`,
`test_observe.py`, `test_llm_e2e.py`, the approval and async cases in `test_api.py` and
`test_guardrails.py`, the turn-id assertions in `test_turn_synthesis_stream.py`, and any other test
that imports a removed module; the mypy strict-override entries for the removed modules. Template
parameters that fed removed settings stay until the hosted step removes them with built-in
authentication.

**Proof unique to this step.** Two authored incidents take different evidence paths; a proposal
naming an unregistered capability, an already-answered question, or an exhausted cap ends
gathering with the reason recorded; a run whose sources all fail is a failed execution with a
sanitized category and no record; a run with one admitted observation and no established candidate
is inconclusive and persisted; the return happens at most once and a second `unresolved_question`
does not re-enter gathering; the record is saved before the terminal event and a failed save is a
failed execution; a deadline expiring during synthesis is a failed execution; every activity event
carries `investigation_id` and none carries prompt text or hidden reasoning; the model call count
never exceeds the cap.

**Hosted effect: Application.** Deploy; one hosted investigation streams identity, activity, and a
terminal brief; the record is readable through the repository afterwards.

**Complete when** the graph runs the streaming request as designed with all three roles, bounds,
return, grounding, correction, outcome, failure rules, and persist-before-deliver, every evidence
access is bounded by the run's remaining time rather than by a fixed per-source ceiling alone,
knowledge references resolve against what the investigation retrieved rather than against files
on disk, and every module, route, setting, dependency, override, and test named above is absent.

---

## H6. Interaction over the completed record

**State:** Complete.

**Builds.** Durable completed-investigation use, the two ordinary requests over it, and the screen
that uses them. The application runtime uses the existing Cosmos implementation of the
completed-investigation repository over the declared investigations container, through the factory
beside it, while the in-memory implementation remains what tests inject; no setting selects between
them, because a second way to be wrong about which store is live is worse than none. Then: read a
completed investigation by identifier; ask a question, which the Interface receives
and presents while the Supervisor answers it in one model call whose only context is the record,
returning answer text, cited references, and optionally a candidate's position in the retained
ordered list, with code checking that every cited reference exists in the record and any position
is valid, and the answer saying so when a check fails or the record cannot answer. The screen gains
the question box beside the brief and details area. No evidence is gathered; no investigation is
created.

**Consumes.** The graph runtime writing completed investigations; the repository seam and its
existing Cosmos implementation; Cosmos access and the declared investigations container; the model
seam; the streaming page with its brief branch.

**Provides.** The question and read operations, and the complete engineer-facing screen.

**If present, remove.** Nothing new; the console and its routes were removed with the runtime.

**Proof unique to this step.** A completed investigation written by one application process can be
read after that process is replaced; an answer citing a reference absent from the record is replaced
by the refusal; a candidate position beyond the retained list is rejected; the question issues no
capability call and creates no record; the read of an unknown identifier is a clean not-found.

**Hosted effect: Application.** Deploy; ask a question about a hosted completed investigation and
receive an answer whose citations resolve.

**Complete when** both operations and the question box exist as designed.

---

## H7. One MCP capability

**State:** Not started.

**Builds.** `get_deployments` additionally served through an in-process MCP server built on the
official Python SDK over stdio, dispatching to the same registered implementation the direct path
uses, read-only, with the transport (`direct` or `mcp`) recorded on the capability's activity event
and telemetry span. Nothing else is exposed.

**Consumes.** The typed deployments adapter and registry; the activity projection and tracing seam
of the runtime.

**Provides.** The one designed protocol boundary with a parity proof.

**If present, remove.** Nothing: the three legacy tools and the server that fronted them went with
the evidence foundation, so this step builds against no existing exposure.

**Proof unique to this step.** For the same arguments the MCP path and the direct path return the
same admitted result; the MCP path refuses any write-shaped request; the activity event for an MCP
call carries `transport: mcp` and nothing else differs.

**Hosted effect: Application.** Deploy; the hosted MCP call returns the same result as the direct
call.

**Complete when** the exposure exists over the official SDK with parity and transport visibility
and no other tool is exposed.

---

## H8. Evaluation

**State:** Not started.

**Builds.** The offline evaluation capability over completed investigations, kept small. The
authored expectation shape simplified to what the runner reads (expected cause, acceptable
alternatives, required evidence references, deliberately absent evidence, accepted outcomes, the
behavior the scenario tests, and how retrieved knowledge should matter where it should). One runner
that obtains or replays completed investigations for a scenario set, applies the checks, runs the
two comparisons where the set includes their scenarios, calls the judge, and writes one report per
run recording the configuration identity. Deterministic correctness reusing the runtime's resolver
and grounding function, which decide a knowledge reference against the passages the completed
record carries rather than against authored files on disk, so evaluation reads the same
knowledge the run itself saw: references resolve, `what_happened` and established candidates have
operational support, no knowledge reference stands as proof, no attempted operation was a write
(from the record's operations list against the registry), deliberately absent evidence is
disclosed, structured-query results match expected rows. Scenario behavior: the mechanical checks
(accepted outcome, affirmative no-immediate-action entry where required) read from the record;
diagnosis matching, ambiguity handling, and multiple-contributor recognition decided by the one
offline judge against the expectation as categories. The evaluation-only injection seam on the
investigation runner: substitute a fixed next-action source, withhold retrieved passages at prompt
assembly, or invoke the runner with the benign fixture's incident context; never an API parameter,
configuration, or persisted state. The adaptive-versus-fixed-path comparison run across candidate
scenarios to find the one where the adaptive path reaches a meaningfully better result. The
retrieval-influence comparison on the postmortem-recurrence scenario with scenario, model
deployment, prompt versions, configuration, and evidence environment held constant, model responses
live or recorded per condition, never one cassette across both. The judge on the runtime chat
deployment with one authored rubric returning categories for usefulness and coherence, appropriate
uncertainty, explanation in context, recommendation fit, plus the diagnosis matching; reported
beside the deterministic results, never combined.

**Consumes.** The complete runtime path including the return and retrieval influence; the
persistence seam; the model seam and cassette replay; the authored scenarios and benign fixture as
`status.md` records them.

**Provides.** The designed evaluation capability and its report.

**If present, remove.** `eval/scenario_eval.py`, `eval/baselines/slice_baseline.json`,
`eval/harness.py`, `EvalTargets` and `TARGETS` in `config.py`, `tests/test_scenario_gate.py`,
`tests/test_scaffold.py`; `eval/golden_incidents.json`, `eval/golden_retrieval.json`, the branches
of `data/answer_key/build_goldens.py` that emit them, and the sync assertions in
`tests/test_answer_key.py` that read them.

**Proof unique to this step.** The fixed-path control issues the same tools in its predetermined
order regardless of what it observes; the retrieval-influence control still records retrieval while
the agents' prompts carry no passage; the two conditions of either comparison never share a model
response; the injection seam is unreachable from the API; the report names each failed check and
never emits a composite score.

**Hosted effect: None.** Evaluation runs offline.

**Complete when** the runner, checks, seam, both comparisons, judge, and report exist as designed
and the numeric evaluation machinery and golden files are absent.

---

## H9. Hosted final posture

**State:** Not started.

**Builds.** The remaining hosted gaps, and nothing beyond them. Container App replicas 0 to 1.
Application Insights component and exporter wiring for the one tracing seam, with spans for the
run, each agent step, each model call, each capability call including transport, admission,
grounding and its issues, persistence, and the terminal outcome or failure category. This is
wiring and simplification, not a second observability system: use the tracing seam that exists,
and add no telemetry manager, middleware layer, metric registry, dashboard, event store, or
viewer. A span must surround the operation whose duration and status it reports, so a span that
opens and closes after the work has already happened is removed rather than kept for symmetry
unless it carries a real event of its own. The model spans must be emitted by the runtime
composition the application actually runs, not only by a test that exercises the seam directly.
Readiness stays cheap: it establishes that the revision can accept work, and proving the model,
retrieval, and a whole investigation belongs to the smoke suite below, which runs once per
deployment rather than continuously. Container Apps built-in authentication with one app
registration; presence of an authenticated caller is the whole
check. Startup validation that refuses to start with a required setting missing or an unknown
capability enabled, naming the setting and never its value; the startup record naming revision and
image tag; health and version as designed. Model access already keyless as the managed identity.
The smoke suite that proves the deployment: healthy at the deployed revision, authenticated caller
admitted and unauthenticated refused, one investigation streams identity, activity, and a terminal
brief, the record reads back with resolving citations, a question is answered, the MCP path matches
the direct path, and the run's telemetry is queryable by `investigation_id`.

**Consumes.** Everything above: the runtime, interaction, MCP, and the current Bicep template and
deployment workflow as `status.md` records them.

**Provides.** The designed hosted OpsPilot, verified after each deployment.

**If present, remove.** `maxReplicas: 3`; the template parameters `entraApiAudience`,
`entraApproverRole`, `entraConsoleClientId` and the environment variables they feed
(`entraTenantId` stays for built-in authentication); the old `scripts/smoke_deployment.py`,
replaced by the suite above.

**Proof unique to this step.** The smoke suite passes against the deployed revision; an
unauthenticated request is refused; a span query by `investigation_id` in Application Insights
returns the run, its model calls with task label and usage, and its capability calls with transport.

**Hosted effect: Infrastructure.** Deploy the template and application; run the smoke suite.

**Complete when** the hosted composition matches the design and the smoke suite passes.
