# OpsPilot Vertical Execution Plan

Ten slices that build coherent, demonstrable functional increments, using the final architectural
seams narrowly from the first slice that needs them and widening afterwards, from the repository as
`docs/status.md` describes it to the system the governing design describes.

## How this plan works

- **Sequencing.** Each slice answers "what is the smallest useful next behavior that can run and
  be shown working?" A slice may cross data, evidence, tools, retrieval, agents, graph, grounding,
  persistence, screen, telemetry, evaluation, and Azure. It is complete for its declared functional
  scope and may leave a technical layer partial. Two early slices are contained prerequisites that
  establish final seams the graph then consumes unchanged.
- **Narrow but final.** Any seam a slice implements is its final seam, exercised narrowly. Later
  slices widen it; they never replace it. No temporary single-model runtime, temporary tool loop,
  temporary agent composition, or temporary graph.
- **Same destination.** Executing this plan to completion produces exactly the repository,
  runtime, persistence, MCP boundary, evaluation, hosted deployment, and retired code that
  `docs/horizontal-execution-plan.md` produces. The two plans differ only in sequencing.
- **Eligibility.** A slice is eligible because everything it consumes exists in the current
  repository, as `docs/status.md` and inspection show. Not because the slice before it ran. Before
  starting: read the slice, read `status.md`, inspect the code it touches, verify every Consumes
  line. If one is missing, stop and report; do not build it.
- **One slice, one PR.** A slice is as large as is logically coherent and no larger. Split only for
  a real prerequisite, an independently risky migration, a deployment boundary, or reviewability.
- **Deletion first.** Every "if present, remove" line names implementation the slice's replacement
  makes obsolete. Remove it in the same PR. If a Horizontal landing already removed it, the absence
  is the correct no-op.
- **Hosted effect.** Each slice is None (no hosted change, no ceremonial deploy), Data (publish and
  verify changed corpus, database, or vector state), Application (deploy the application and prove
  the changed hosted behavior), or Infrastructure (deploy changed Azure or runtime configuration
  and prove it).
- **Verification.** `docs/code-guidelines.md` owns the standing gates; each slice states only the
  proof unique to it.
- **After a landing.** In the same PR, preferably as a trailing documentation commit: update
  `docs/status.md` first to repository truth; then re-evaluate this plan and the Horizontal plan and
  change only the steps whose completion condition now holds, partly holds, or no longer holds. A
  slice is Not started, Partial (Already present / Remaining), or Complete. Complete means the
  repository provides what the slice promises and its named obsolete implementation is absent. Do
  not redesign unrelated future slices during bookkeeping; if a landing proves a future slice wrong,
  report it.
- **Vocabulary.** Slice identifiers, requirement and decision identifiers, document section
  numbers, and migration terms stay out of source, comments, tests, configuration, branches,
  commits, and PR titles and descriptions. Say what the code does and why, technically.

---

## V1. Final assessment, structural synthesis, grounding, and brief

**State:** Not started.

**Builds.** The final output seam, as pure functions the graph will call unchanged. The assessment
shape becomes the designed field set once: `what_happened`, ordered `candidates` (statement, label,
established, supporting, weakening), `unknowns`, `limitations`, `next_check`, `actions` (action,
now, optional `knowledge_ref`, with an affirmative no-immediate-action entry where the evidence
supports it), `history`, `knowledge_used`; the model's proposal is that shape as loose strings plus
the optional `unresolved_question`, routing metadata whose matter also appears in `unknowns`.
Synthesis becomes structural only: parse, normalize representation, reject malformed structure or
a syntactically impossible reference, never remove a candidate, derive `established`, or discard an
action. Grounding becomes one function returning zero or more issues over the admitted assessment,
admitted evidence, retrieved knowledge, and limitations, enforcing the designed properties:
operational-support references resolve in admitted evidence and knowledge references (including an
action's `knowledge_ref`) in retrieved knowledge; no knowledge reference where operational support
is required; `what_happened` and every established candidate have admitted operational support;
every recorded limitation is disclosed. The brief renders the assessment deterministically:
contributors when more than one candidate is established, the affirmative no-action entry as such,
the outcome, no probability. The synthesis cassette is re-recorded against the new proposal shape.
The existing streaming request already synthesizes and renders, so it demonstrates the new output
seam without any disposable implementation.

**Consumes.** The current synthesis and grounding functions, brief renderer, model seam, and
cassette as `status.md` records them; admitted evidence and the reference resolver as they are.

**Provides.** The final assessment contract, structural synthesis, the grounding function, and the
brief renderer.

**If present, remove.** `SupportRelationship`, `Horizon`, `RecommendationKind`,
`RecommendationProvenance`, `ConclusionDisposition`, `BriefSection`, `Citation` as a model,
`GroundedElement`, `HistoricalComparison`, and the validators that duplicate the gate; the semantic
filtering in `assessment/synthesis.py` (`_grounded`, the drop-if-unsupported and
derive-`established` branches of `_candidate`); `CheckName`, `CheckResult`, `GroundingResult` and
its exact-set validators, `CorrectionAllowance`, `GateRouting`, `route_grounding_result`; the eleven
`model_construct()` sites in `tests/test_grounding_gate.py` and the tests that exist only to
exercise them.

**Proof unique to this slice.** A proposal with an unsupported candidate reaches the gate unchanged
and the gate reports the issue; `what_happened` without operational support is an issue; a
knowledge reference offered as current support is an issue; a limitation the assessment omits is
an issue; a clean assessment yields zero issues; the brief adds nothing and drops nothing; two
established candidates render as contributors; an affirmative no-action entry renders as such.

**Hosted effect: Application.** The deployed stream renders the new brief shape. Deploy and confirm
one hosted investigation delivers a brief with the designed sections and no probability.

**Complete when** the assessment is the designed shape, synthesis is structural only, one grounding
function returns issues, the brief renders as designed, and the named contract layer, oversized
models, filtering, and scaffolding are absent.

---

## V2. Final model seam and incident intake

**State:** Not started.

**Builds.** The two seams the graph is built against and must not change inside the graph PR. Model
access reduces to one Azure adapter, one fake, and cassette record and replay, taking a task label
and messages and recording deployment, latency, and token usage. The incident context becomes the
final four fields: `incident_id` required, `scope` where the incident names one, `symptom`,
`time_anchor`; answer-bearing and ticket-workflow fields stay excluded.

**Consumes.** The model seam, its fake and cassette, and the intake contract as `status.md`
records them; the final assessment proposal shape.

**Provides.** The final model seam and the final incident context.

**If present, remove.** The Ollama and generic-OpenAI branches, `LLM_SEED`, and the planner,
claim, report, triage, and tool-call response models in `llm/schema.py`; the `llm` marker's
provider text; `InteractionKind`, `supplied_context`, and the optionality of `incident_id`.

**Proof unique to this slice.** Every model call records its task label, deployment, latency, and
usage; the fake and cassette stand in for the adapter without a live service; a raw incident
record normalizes to exactly the four fields with no cause, resolution, or ticket-workflow value.

**Hosted effect: Application.** Deploy; the hosted stream still runs its model calls through the
one adapter as the managed identity.

**Complete when** the model seam is Azure-only with fake and cassette, the intake contract is the
four fields, and the named branches, models, and residue are absent.

---

## V3. One authored incident through the final graph

**State:** Not started.

**Builds.** The designed runtime, narrowly: one authored incident (the fast change-time scenario,
inc-005) investigated end to end by the final three-agent graph in the streaming request, with the
composition it supersedes removed. Every seam below is the final one, exercised only as far as this
incident needs; the assessment, gate, brief, model seam, and intake are consumed unchanged.

- Graph and bounds: one small compiled in-process graph over typed investigation state, no
  checkpointer, with set objective, gather with deterministic continuation, synthesize, ground,
  persist, deliver, and the conditional return edge declared but not yet exercised by this
  scenario. The five bounds on state: deadline, capability-call cap, model-call cap,
  `correction_used`, `return_used`.
- Supervisor: interprets the incident context into an objective in one model call; authorizes each
  proposal deterministically (registered, question not already answered, cap and deadline have
  room); ends gathering when the investigator reports ready or no useful permitted action, or a
  source the objective depends on is unavailable, or a bound is reached; runs the gate; assigns
  the outcome; persists; delivers.
- Evidence Investigator: proposes one registered operational capability with arguments and the
  question it expects answered, choosing from the incident, objective, and admitted evidence, over
  the operational adapters this incident needs (correlated alerts, deployments, logs, metrics,
  dependencies as the registry offers them); holds its working hypothesis privately.
- Evidence: admission returns plain values (observations, limitations, the operations list with an
  identifier, capability, and outcome per operation) keyed by `investigation_id`; the
  `alert:<service>:<alert_id>` reference form is added to the parser and resolver so
  `what_happened` can rest on the alerts this incident observes; the operational adapters and
  their request models are used as they are.
- RCA Analyst: one synthesis call proposing the final assessment shape; structural admission as
  established.
- Grounding, correction, outcome, failure: the grounding function runs; one corrective model call
  when the proposal is unusable or issues remain; inconclusive when no candidate is established,
  partial when established with any recorded limitation, complete when established with none;
  failed execution for zero admitted operational observations at the end of gathering, an unusable
  proposal or issues after the correction, a failed save, the deadline expiring before a
  trustworthy brief, or an unhandled error, emitting a sanitized failure category and persisting
  nothing.
- Persistence: `CompletedInvestigation` with the designed contents including the operations list;
  `save`/`get`; the in-memory repository, narrowed to that seam; saved before the terminal event.
- Delivery: the streaming request mints `investigation_id`, streams activity events built at the
  tracing span sites and correlated by `investigation_id` alone, then one terminal event with the
  brief and outcome or the failure category, under investigation-only route and identity
  vocabulary; the screen shows the brief as the dominant element when the terminal event arrives.

Retrieval, the structured query, the return, Cosmos persistence, the question, and MCP are not in
this slice; each later slice widens the seams laid here.

**Consumes.** The final assessment, structural synthesis, grounding function, and brief; the final
model seam and four-field incident context; the operational-records adapters and registry,
reference parser and resolver, admission, two-axis result, tracing seam and activity projection,
streaming request and page, and in-memory record backend as `status.md` records them; the authored
incident inc-005.

**Provides.** A running final-architecture investigation for one incident: three model-directed
roles under deterministic control, bounded, grounded, persisted in memory before delivery,
observable, with the persistence seam and identity model in their final form.

**If present, remove.** The superseded orchestration: `graph.py`, `nodes/investigation.py`,
`router.py`, `checkpoint.py`, `state.py`, `hitl_gate`, `apply_edit`, `escalate`, the `postmortem`
path, `traced_node`; `langgraph-checkpoint-sqlite`; `langchain-azure-cosmosdb`; the `checkpoint`
dependency group after `azure-cosmos` moves into the base dependencies (every Cosmos read imports
it), and the Dockerfile's `--group checkpoint` on both `uv sync` lines and the `CMD`. The async job,
approval, and polling path: `investigations.py`, `cosmos_investigations.py`, `repository.py`, the
`/investigations`, `/investigations/{id}/decision`, and `/investigate` routes and helpers in
`api.py`, `CommittedDecision`, idempotency, leases, fencing, outbox, job-status vocabulary,
publication identity, the approval-bound report hash. The legacy diagnosis path: root
`contracts.py`, `diagnosis/` (nine modules), `triage.py`, `composition.py`,
`guardrails/policies.py`, the `OPSPILOT_IMPLEMENTATION` setting and selector code, the explicit
`langchain-core` dependency. The fixed synthesis path: `turn/synthesis_step.py` and the stub-backed
branch of the streaming route. Hand-rolled authorization code: `auth.py`, `ReviewerPrincipal`,
`pyjwt[crypto]`, the `OPSPILOT_API_AUDIENCE` and `OPSPILOT_APPROVER_ROLE` settings. The console:
`static/console.html`, `/console`, `/console/config`, the `OPSPILOT_CONSOLE_CLIENT_ID` setting.
Plural-turn identity and persistence: `turn/identity.py`, `TurnIdentity`, `turn_id` on the evidence
set, spans, and stream events, the close marker folded into the terminal event; `CompletedTurn`,
`completed_turns()`, `turn()`, `CommitOutcome`, `CommitResult`, `DeliveryOutcome`,
`commit_then_deliver()` in `record/port.py`. Admission wrappers displaced by plain values:
`AuthoritativeAbsence`, `AdmissionResult`, `Resolution`, `OperationRecord`, `OperationLedger` as
classes. Their tests: `test_investigations_api.py`, `test_investigations.py`,
`test_repository_factory.py`, `test_report_binding.py`, `test_checkpointer.py`, `test_auth.py`,
`test_triage.py`, `test_triager.py`, `test_composition.py`, `test_sufficiency.py`,
`test_planner_seam.py`, `test_diagnose.py`, `test_llm_planner.py`, `test_state.py`,
`test_state_contract.py`, `test_conclusion_contracts.py`, `test_conclusion_wiring.py`,
`test_cycle_onset_clamp.py`, `test_observe.py`, `test_llm_e2e.py`, the approval and async cases in
`test_api.py` and `test_guardrails.py`, the plural and delivery-ordering cases in
`test_record_commit.py`, the turn-id assertions in `test_turn_synthesis_stream.py`, and any other
test importing a removed module; the mypy strict-override entries for the removed modules. Not in
this slice: the per-capability request models and MCP exposures (widened evidence surface), the
reranker (retrieval), numeric evaluation (evaluation), template parameters and replicas (hosted
posture).

**Proof unique to this slice.** inc-005 streams identity, activity, and a terminal brief whose
citations resolve in the record; a proposal naming an unregistered capability, an already-answered
question, or an exhausted cap ends gathering with the reason recorded; a run whose sources all fail
is a failed execution with a sanitized category and no record; a run with one admitted observation
and no established candidate is inconclusive and persisted; the record is saved before the terminal
event and a failed save is a failed execution; a deadline expiring during synthesis is a failed
execution; every activity event carries `investigation_id` and none carries prompt text or hidden
reasoning; the model-call count never exceeds the cap; `alert:` references parse and resolve.

**Hosted effect: Application.** Deploy; the hosted stream for inc-005 delivers a grounded brief;
the record is readable through the repository during the process lifetime.

**Complete when** inc-005 runs through the final graph as described, every seam above is in its
final form, and every module, route, setting, dependency, override, and test named above is
absent.

---

## V4. The analysis-to-gathering return

**State:** Not started.

**Builds.** The one return, visible and demonstrable on the ambiguous scenario (inc-004). The
proposal's `unresolved_question` names what remains unanswered and what evidence kind could answer
it; the same matter stands in `unknowns`. The Supervisor authorizes a return only when
`return_used` is false, a registered capability supplies that evidence kind, and the bounds have
room; gathering resumes with the question seeded under the same continuation rules; synthesis runs
once more with the flag set; when the return is unavailable or spent, the edge is not followed and
the assessment is not edited. The Evidence Investigator changes direction when evidence weakens
its current explanation, and the activity feed shows the return. No general loop.

**Consumes.** The final graph runtime with its declared return edge, `return_used` bound, and
structural admission of `unresolved_question`; the authored incident inc-004.

**Provides.** The designed feedback loop: at most one return per investigation, and adaptive
redirection demonstrated on an incident whose first pass cannot close.

**If present, remove.** Nothing new.

**Proof unique to this slice.** On inc-004 the return occurs once, gathering resumes seeded with
the question, and the second synthesis carries the answer or the unknown; a second
`unresolved_question` after the return does not re-enter gathering; a question naming an evidence
kind no capability supplies is not authorized and stands in `unknowns`; the capability and model
caps still bound the resumed gathering.

**Hosted effect: Application.** Deploy; the hosted inc-004 stream shows the return in its
activity.

**Complete when** the return behaves as designed and inc-004 demonstrates it.

---

## V5. Retrieval materially influences the investigation

**State:** Not started.

**Builds.** Retrieval as a registered capability inside the investigation, final in behavior: embed
the question, vector search plus the in-process lexical pass over the same category-filtered
candidates, reciprocal-rank fusion, deterministic promotion of passages whose extracted identifiers
match identifier-like terms in the question, truncation to the small passage budget; one passage
shape carrying text and reference. The Evidence Investigator may propose retrieval; it counts
against the capability-call cap; passages join the knowledge set and reach the agents as context; a
retrieval that fails, times out, or is unavailable becomes a limitation, and the retrieval adapter
in `tools/search.py` returns the one passage shape. Knowledge references appear where the assessment
uses them (`history`, `knowledge_used`, an action's `knowledge_ref`) and the gate's knowledge
properties are exercised. The postmortem-recurrence scenario (inc-007) shows retrieved knowledge
changing what is checked or concluded.

**Consumes.** The final graph runtime; the retriever, embeddings client, knowledge-records access,
and retrieval adapter as `status.md` records them; the authored incident inc-007.

**Provides.** Final retrieval, knowledge-set semantics, and demonstrated retrieval influence.

**If present, remove.** `retrieval/reranker.py`, `CrossEncoder`, `RERANKER_MODEL`,
`RERANK_CANDIDATES`, the `reranker` pytest marker, `sentence-transformers` and its transitive
`torch`, `transformers`, `scikit-learn`, `scipy` in the eval dependency group, the `full` lane in
`.github/workflows/deploy.yml` that exists to install that group; the `Doc`/`Chunk`/`Passage`
multiplicity.

**Proof unique to this slice.** A passage whose extracted identifier exactly matches a service
name, error code, or deploy identifier in the question is promoted ahead of otherwise higher fused
results, and fused order is unchanged when nothing matches; a failed retrieval yields a limitation
and no passage; a knowledge reference offered as current operational support is a grounding issue;
on inc-007 a capability proposed, the leading candidate or its label, an interpretation, or an
action differs from the same investigation with passages withheld.

**Hosted effect: Application.** Deploy; the hosted inc-007 stream shows retrieval and a brief that
cites a postmortem.

**Complete when** retrieval behaves as designed inside the graph, inc-007 demonstrates influence,
and the reranker implementation, dependencies, marker, and lane are absent.

---

## V6. Governed structured query and the full evidence surface

**State:** Not started.

**Builds.** The governed structured query as a capability the Evidence Investigator can propose: the
model proposes a bounded structure of predicates, projection, optional count, and limit over one
approved collection; deterministic code validates it against the approved surface and translates it
into one parameterized read-only query; the result is admitted like any other. Rows carry the
reference of the record they project, formed from identifying fields every projection includes; a
count carries `query:<operation>`; an empty result carries `absence:`. The `incident:<incident_id>`
and `query:<operation>` reference forms join the parser and resolver; the incident record reaches an
agent only in the approved surface's fields. The operational adapters take typed parameters, the
registry validates them, and the two-axis result keeps its one enforcement point as an inline rule
if that is smaller than the table.

**Consumes.** The final graph runtime and registry; the structured-query validators and
translation, the operational adapters, and the two-axis result as `status.md` records them.

**Provides.** The full designed evidence surface with a citable reference for every observation any
capability can produce, and the model-proposed structured query inside the bounded investigation.

**If present, remove.** The eight per-capability request models; `legacy_status()`; `DocHit`; the
pairing-table tests in `tests/test_evidence_admission.py`; the three superseded MCP tool exposures
in `mcp/server.py` and their parity test, which depend on the request models. MCP is intentionally
absent after this slice until V8 establishes the final single `get_deployments` boundary; no
compatibility shim is retained.

**Proof unique to this slice.** A proposed structure naming a field or collection outside the
approved surface is rejected before anything executes; a query row's reference resolves to its
record; a count admits with a `query:` reference; an incident-record observation contains no cause
or resolution field; the query executes read-only with every value bound as a parameter.

**Hosted effect: Application.** Deploy; a hosted investigation that proposes a structured query
admits its rows with resolving references.

**Complete when** the query is proposable and governed as designed, all three added reference forms
exist, adapters take typed parameters, and the request models and superseded exposures are absent.

---

## V7. Durable persistence and the question over the completed record

**State:** Not started.

**Builds.** The Cosmos implementation of the repository seam over the `investigations` container,
keyed by `investigation_id`, one plain create per record, selected for local and hosted runs while
the in-memory implementation serves tests. The read of a completed investigation by identifier.
The question: the Interface receives it and presents the answer; the Supervisor answers in one model
call whose only context is the completed record, returning answer text, cited references, and
optionally a candidate's position in the retained ordered list; code checks that every cited
reference exists in the record and any position is valid, and the answer says so when a check
fails or the record cannot answer; no evidence is gathered and no investigation is created. The
screen gains the question box.

**Consumes.** The final graph runtime persisting `CompletedInvestigation` through the seam; the
in-memory repository; the model seam; Cosmos access and the declared `investigations` container.

**Provides.** Retained completed investigations and the two ordinary requests over them.

**If present, remove.** Nothing new.

**Proof unique to this slice.** A hosted investigation's record reads back through Cosmos with
every citation resolving; a second save of the same identifier is refused; an answer citing a
reference absent from the record is replaced by the refusal; a candidate position beyond the
retained list is rejected; the question issues no capability call and creates no record.

**Hosted effect: Application.** Deploy; ask a question about a hosted completed investigation
after the process has restarted and receive an answer whose citations resolve.

**Complete when** Cosmos persistence, the read, the question, and the question box exist as
designed.

---

## V8. One MCP capability

**State:** Not started.

**Builds.** `get_deployments` additionally served through an in-process MCP server built on the
official Python SDK over stdio, dispatching to the same registered implementation the direct path
uses, read-only, with the transport (`direct` or `mcp`) recorded on the capability's activity event
and telemetry span. Nothing else is exposed.

**Consumes.** The typed deployments adapter and registry; the activity projection and tracing seam
of the runtime.

**Provides.** The one designed protocol boundary with a parity proof.

**If present, remove.** Any superseded MCP exposure still present.

**Proof unique to this slice.** For the same arguments the MCP path and the direct path return the
same admitted result; the MCP path refuses any write-shaped request; the activity event for an MCP
call carries `transport: mcp` and nothing else differs.

**Hosted effect: Application.** Deploy; the hosted MCP call returns the same result as the direct
call.

**Complete when** the exposure exists over the official SDK with parity and transport visibility
and no other tool is exposed.

---

## V9. Evaluation

**State:** Not started.

**Builds.** The offline evaluation capability over completed investigations, kept small. The
authored expectation shape simplified to what the runner reads (expected cause, acceptable
alternatives, required evidence references, deliberately absent evidence, accepted outcomes, the
behavior the scenario tests, and how retrieved knowledge should matter where it should). One runner
that obtains or replays completed investigations for a scenario set, applies the checks, runs the
two comparisons where the set includes their scenarios, calls the judge, and writes one report per
run recording the configuration identity. Deterministic correctness reusing the runtime's resolver
and grounding function: references resolve, `what_happened` and established candidates have
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
retrieval-influence comparison on inc-007 with scenario, model deployment, prompt versions,
configuration, and evidence environment held constant, model responses live or recorded per
condition, never one cassette across both. The judge on the runtime chat deployment with one
authored rubric returning categories for usefulness and coherence, appropriate uncertainty,
explanation in context, recommendation fit, plus the diagnosis matching; reported beside the
deterministic results, never combined.

**Consumes.** The complete runtime path with the return, retrieval influence, and structured
query; Cosmos and in-memory persistence; the model seam and cassette replay; the authored scenarios
and benign fixture as `status.md` records them.

**Provides.** The designed evaluation capability and its report.

**If present, remove.** `eval/scenario_eval.py`, `eval/record_single_agent.py`,
`eval/cassettes/single_agent.json`, `eval/baselines/*.json`, `eval/harness.py`, `EvalTargets` and
`TARGETS` in `config.py`, `tests/test_scenario_gate.py`, `tests/test_single_agent_gate.py`,
`tests/test_scaffold.py`; `eval/golden_incidents.json`, `eval/golden_retrieval.json`, the branches
of `data/answer_key/build_goldens.py` that emit them, and the sync assertions in
`tests/test_answer_key.py` that read them.

**Proof unique to this slice.** The fixed-path control issues the same tools in its predetermined
order regardless of what it observes; the retrieval-influence control still records retrieval while
the agents' prompts carry no passage; the two conditions of either comparison never share a model
response; the injection seam is unreachable from the API; the report names each failed check and
never emits a composite score.

**Hosted effect: None.** Evaluation runs offline.

**Complete when** the runner, checks, seam, both comparisons, judge, and report exist as designed
and the numeric evaluation machinery and golden files are absent.

---

## V10. Hosted final posture

**State:** Not started.

**Builds.** The remaining hosted gaps, and nothing beyond them. Container App replicas 0 to 1.
Application Insights component and exporter wiring for the one tracing seam, with spans for the
run, each agent step, each model call, each capability call including transport, admission,
grounding and its issues, persistence, and the terminal outcome or failure category. Container Apps
built-in authentication with one app registration; presence of an authenticated caller is the whole
check. Startup validation that refuses to start with a required setting missing or an unknown
capability enabled, naming the setting and never its value; the startup record naming revision and
image tag; health and version as designed. Model access already keyless as the managed identity.
The smoke suite that proves the deployment: healthy at the deployed revision, authenticated caller
admitted and unauthenticated refused, one investigation streams identity, activity, and a terminal
brief, the record reads back with resolving citations, a question is answered, the MCP path matches
the direct path, and the run's telemetry is queryable by `investigation_id`.

**Consumes.** Everything above: the runtime, persistence and question, MCP, and the current Bicep
template and deployment workflow as `status.md` records them.

**Provides.** The designed hosted OpsPilot, verified after each deployment.

**If present, remove.** `maxReplicas: 3`; the template parameters `implementation`,
`entraApiAudience`, `entraApproverRole`, `entraConsoleClientId` and the environment variables they
feed (`entraTenantId` stays for built-in authentication); the old `scripts/smoke_deployment.py`,
replaced by the suite above.

**Proof unique to this slice.** The smoke suite passes against the deployed revision; an
unauthenticated request is refused; a span query by `investigation_id` in Application Insights
returns the run, its model calls with task label and usage, and its capability calls with transport.

**Hosted effect: Infrastructure.** Deploy the template and application; run the smoke suite.

**Complete when** the hosted composition matches the design and the smoke suite passes.
