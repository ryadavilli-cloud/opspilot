# OpsPilot cascade inventory: execution-plan handoff

The single handoff artifact for re-deriving the execution plans. It joins the final governing design
(`architecture.md`, `system-design.md`, `workflow-design.md`, `data-and-evidence.md`,
`runtime-and-deployment.md`, `evaluation.md`, `decisions.md`, `code-guidelines.md`) to the actual
repository (`status.md` at `23c44aa`) and states what must be built, aligned, shrunk, and retired.
`requirements.md` governs everything. Git holds the history of how this baseline was reached; it is
not repeated here.

Two rules govern every plan derived from this file:

    Every still-valid retirement, delete, or rewrite item must be assigned to the execution slice
    that owns the affected module. Rewriting the execution plan may not silently erase retirement
    work.

    Existing code survives only where the final design independently selected it; implementation
    existence, test coverage, previous acceptance, and effort already spent are not retention
    reasons.

---

## A. Final target

- **One investigation, one run, one record.** `investigation_id` is the only identity: persistence
  key, telemetry correlation, question handle. No turn, no session, no history.
- **Three agents:** Supervisor (objective, bounds, continuation, the one return, grounding gate,
  persist, deliver, and the question answer), Evidence Investigator (what to gather next, through
  registered capabilities), RCA Analyst (the assessment, and one optional unresolved question).
- **One small compiled in-process graph** over typed state, no checkpointer:
  set_objective, gather with deterministic continuation, synthesize, ground with one correction,
  persist, deliver, and one conditional return from synthesize to gather.
- **Evidence access:** registered read-only tools over operational records; retrieval; the governed
  structured query; one MCP exposure of `get_deployments`. Every operational result admitted
  through one path; retrieval passages join the knowledge set and a failed retrieval is a
  limitation; every capability call, retrieval included, counts against the one capability-call
  cap; the two-axis tool result with one pairing validator. The incident record reaches an agent
  only in the approved structured-query surface's fields.
- **References:** evidence `logs:`, `metrics:`, `deploys:`, `deps:`, `alert:`, `incident:`,
  `absence:`, `query:`; knowledge `runbook:`, `architecture:`, `postmortem:`; segment forms as
  `data-and-evidence.md` states them; a structured-query row carries its underlying record's
  reference, a count carries `query:<operation>`.
- **Retrieval:** embed, Cosmos vector search plus in-process lexical over category-filtered
  candidates, reciprocal-rank fusion, deterministic identifier promotion, small passage budget,
  passages carry text and reference. No model reranker.
- **Structured query:** predicates, projection, count, limit over an approved surface; two
  validators; one parameterized read-only query. Unchanged.
- **Grounding:** one function returning issues over the admitted assessment, the admitted
  operational evidence, the retrieved knowledge, and the limitations, covering every material
  claim about the incident: operational-support references resolve in admitted evidence and
  knowledge references in retrieved knowledge; `what_happened` and every established candidate
  have admitted operational support; knowledge never stands as current proof; an action's
  `knowledge_ref`, where present, resolves in retrieved knowledge; limitations are disclosed.
  Structural admission is structural only; one correction flag.
- **Assessment** as `data-and-evidence.md` §6 defines it, once: what happened, ordered candidates
  (statement, label, established, supporting, weakening), unknowns, limitations, next check,
  actions (action, now, optional knowledge ref; an affirmative no-immediate-action entry where
  the evidence supports it), history, knowledge used; proposal carries an optional
  `unresolved_question` as routing metadata, with the same matter in unknowns; the Supervisor
  never edits the assessment when the return is unavailable or spent.
- **Persistence:** one `CompletedInvestigation` carrying the contents `data-and-evidence.md` §9
  states, including the operations list (identifier, capability, outcome per operation);
  `save`/`get`, in-memory and Cosmos.
- **Question:** one operation over the completed record; cited references checked to exist in
  the record and any structural candidate position checked to be valid, deterministically; the
  no-new-conclusion property rests on the constrained context, the instruction, those structured
  references, and refusal, never on code judging prose. No new evidence or investigation.
- **Evaluation:** one runner, authored expectations, deterministic checks reusing runtime
  functions, two controlled comparisons through one harness-only injection seam, one judge, one
  report. In each comparison the scenario, model deployment and version, prompt versions,
  configuration, and evidence environment are held constant and the model's responses come from
  live calls or from responses recorded separately per condition, never from one identical cassette
  replayed across both variants.
- **Outcome:** code assigns Inconclusive (no candidate established), Partial (some candidate
  established and at least one limitation recorded), or Complete (some candidate established and no
  limitation recorded). Nothing else contributes for a run with at least one admitted operational
  observation. A run with zero admitted operational observations is a failed execution, since no
  grounded brief can be produced; failed execution also covers an unusable proposal or grounding
  issues after the one correction, a failed save, the deadline expiring before a trustworthy brief,
  and an unhandled error.
- **Evaluation harness access:** the harness may invoke the investigation runner directly with the
  benign fixture's incident context; the fixture is not selectable in the product interface.
  Semantic diagnosis matching is decided by the one judge path; the mechanical layer stays
  mechanical.
- **Azure:** one Container App at 0-1 replicas, ACR, one chat and one embedding deployment, Cosmos
  with three containers, Log Analytics and Application Insights, built-in authentication, keyless
  model access as the managed identity, OIDC deploy.

## B. Final decisions

D-001 minimal compiled graph; D-002 retired; D-003 hybrid retrieval as above; D-004
`get_deployments` over the official `mcp` SDK in-process stdio server sharing the direct
implementation; D-005 one offline judge on the runtime chat deployment with one rubric; D-006
inc-005 fast signal, inc-004 return and ambiguity, inc-006 correct partial, inc-007 retrieval
influence, R-29 scenario chosen empirically with inc-004 a candidate until measured; D-007
four-field incident context; D-008 prefixed references; D-009 retired; D-010 one optional
`unresolved_question` field, at most one return.

## C. Reusable implementation

Each earned retention on its own; the last column is what still shrinks.

| Area | Exists | Why retained | Simplification still required |
| --- | --- | --- | --- |
| Structured query | `data/structured_query.py`, `tools/structured_query.py` | Narrow, deterministic; validators guard the real boundary | None |
| Operational adapters | `tools/*.py`, `data/operational_records.py` | The read-only surface | Request models to typed parameters |
| Two-axis result | `tools/contracts.py` | R-21 invariant with one enforcement point | Table may become inline rule; drop `legacy_status`, `DocHit` |
| Reference grammar | `evidence/references.py` | Deterministic resolution | `Resolution` to return value; add `alert:`, `incident:`, `query:` |
| Admission | `evidence/admission.py`, `evidence/operations.py` | The trust boundary decision is right | Wrapper classes to fields; drop `turn_id` |
| Retrieval | `retrieval/retriever.py`, `retrieval/embeddings.py`, `data/knowledge_records.py` | Already the derived shape | Add identifier promotion; collapse passage types |
| Corpus preparation | `scripts/prepare_corpus.py`, `retrieval/corpus.py`, `data/answer_key/topology.yaml` | Reached only by preparation; stays for it | None |
| Model seam | `llm/` | Fake and cassette replay are the determinism mechanism | Drop provider branches, `LLM_SEED`, superseded response models |
| Synthesis structural half | `assessment/synthesis.py`, prompt | Model-proposes, code-admits | Remove semantic filtering; shrink proposal |
| Grounding logic | `grounding/checks.py` functions | The computations are right | Return issues; delete contract layer |
| Telemetry seam and projection | `obs/`, `stream/` | Small, projection-at-span-site idea kept | Drop `turn_id`; fold close marker into terminal event |
| Streaming transport and screen | `POST /turns`, `static/investigation.html` | The shape is right | Investigation-only vocabulary; brief branch; question box |
| Incident context | `intake/contracts.py` | Answer-key exclusion is a real boundary | Four fields; drop `InteractionKind`, `supplied_context`; `incident_id` becomes required |
| In-memory record | `record/memory.py` | Tests need it | Narrow to `save`/`get` |
| Expectations and fixture | `data/answer_key/scenarios.yaml`, `golden_scenarios.yaml`, `benign_fixture.yaml`, `build_goldens.py` | The scenarios and their truths; the builder derives the golden set | Record shape may simplify; the builder's `golden_incidents.json` and `golden_retrieval.json` branches go |
| Replay cassette | `eval/cassettes/turn_synthesis.json`, recorder | Determinism | None |
| Azure baseline | `infra/main.bicep`, workflows | Already the target minus three items | Replicas, App Insights, built-in auth |

## D. Missing implementation

- The compiled graph and its typed state; objective, gathering with authorization, synthesis, the
  return, grounding with correction, outcome assignment from established candidates and recorded
  limitations, persist, deliver, all wired into the streaming request.
- The `alert:`, `incident:`, and `query:` reference forms, their parsing and resolution, and the
  admission that assigns them; the operations list on the record.
- The Evidence Investigator and RCA Analyst as model-directed roles with their prompts; the
  Supervisor's objective-interpretation call.
- `CompletedInvestigation` and its Cosmos repository; the runtime write path.
- The question endpoint with reference-existence and candidate-position validation.
- MCP exposure narrowed to `get_deployments`, with the parity test.
- The evaluation runner, harness seam, fixed-path control, retrieval-influence control (with
  per-condition model responses, not one shared cassette), judge, report; the R-29 scenario
  measurement.
- Application Insights wiring and the startup and configuration records; built-in authentication;
  the smoke suite as `runtime-and-deployment.md` §11 describes.
- The screen's brief branch and question box.

## E. Partial implementation

- The run: a linear generator with a fixed evidence plan and one synthesis call, no graph, no
  grounding, no persistence, no outcome.
- Grounding: functions exist, nothing calls them.
- Persistence: port and memory backend, no model, no Cosmos, no writer.
- Retrieval: promotion absent.
- Screen: no brief branch, no question box.

## F. Complete retirement, delete, and replace ledger

Verified present at `23c44aa`. Nothing here is deleted by this pass.

| Group | Items |
| --- | --- |
| Superseded orchestration | `graph.py`, `nodes/investigation.py`, `router.py`, `checkpoint.py`, `state.py`, `hitl_gate`, `apply_edit`, `escalate`, `postmortem` path, `traced_node`; dep `langgraph-checkpoint-sqlite` |
| Async job, approval, polling | `investigations.py`, `cosmos_investigations.py`, `repository.py`; `/investigations`, `/investigations/{id}/decision`, `/investigate` routes and helpers in `api.py`; `CommittedDecision`, idempotency, leases, fencing, outbox, job status, publication identity, report hash; dep `langchain-azure-cosmosdb` |
| Legacy report, claim, diagnosis, triage | root `contracts.py`; `diagnosis/` (all nine); `triage.py`; `composition.py`; `guardrails/policies.py`; planner, claim, report, synthesis, triage, tool-call models in `llm/schema.py`; the `implementation` template parameter and `OPSPILOT_IMPLEMENTATION` setting; the explicit `langchain-core` base dependency |
| Authorization | `auth.py`, `ReviewerPrincipal`, dep `pyjwt[crypto]`; template parameters `entraApiAudience`, `entraApproverRole` and the settings they feed (`entraTenantId` stays for built-in authentication) |
| Console | `static/console.html`, `/console`, `/console/config`; template parameter `entraConsoleClientId` and its setting |
| Numeric evaluation | `eval/scenario_eval.py`, `eval/record_single_agent.py`, `eval/cassettes/single_agent.json`, `eval/baselines/*.json`, `eval/harness.py`, `EvalTargets`/`TARGETS`, `tests/test_scenario_gate.py`, `tests/test_single_agent_gate.py`, `tests/test_scaffold.py`; `eval/golden_incidents.json`, `eval/golden_retrieval.json`, the `build_goldens.py` branches that emit them and the `test_answer_key.py` sync assertions that read them; the `full` lane in `.github/workflows/deploy.yml` |
| Model reranker | `retrieval/reranker.py`, `CrossEncoder`, `RERANKER_MODEL`, `RERANK_CANDIDATES`, `reranker` marker, dep `sentence-transformers` and transitives; the `llm` marker's provider text follows the model seam |
| Plural-turn identity and persistence | `turn_id`, `TurnIdentity`; `CompletedTurn`, `completed_turns()`, `turn()`, `CommitOutcome`, `CommitResult`, `DeliveryOutcome`, `commit_then_deliver()`; `turn_id` on evidence set, spans, stream events |
| Interaction and intake residue | `InteractionKind`, `supplied_context`, the optionality of `incident_id` |
| Grounding contract layer | `CheckName`, `CheckResult`, `GroundingResult` and validators, `CorrectionAllowance`, `GateRouting`, `route_grounding_result`; the eleven `model_construct()` test sites and their tests |
| Oversized assessment | `SupportRelationship`, `Horizon`, `RecommendationKind`, `RecommendationProvenance`, `ConclusionDisposition`, `BriefSection`, `Citation` model, `GroundedElement`, `HistoricalComparison`; duplicate validators; semantic filtering in `synthesis.py` |
| Evidence and tool wrappers | eight request models, `legacy_status()`, `DocHit`, `AuthoritativeAbsence`, `AdmissionResult`, `Resolution`, `OperationRecord`, `OperationLedger`; pairing-table tests |
| Tests attached to deleted behavior | `test_investigations_api.py`, `test_investigations.py`, `test_report_binding.py`, `test_checkpointer.py`, `test_auth.py`, `test_triage.py`, `test_triager.py`, `test_composition.py`, `test_sufficiency.py`, `test_planner_seam.py`, `test_diagnose.py`, `test_llm_planner.py`, `test_state_contract.py`; approval and async cases in `test_api.py`, `test_guardrails.py`; plural and ordering cases in `test_record_commit.py`; turn-id assertions in `test_turn_synthesis_stream.py` |
| Infrastructure and packaging | replica max 3 to 1; in `pyproject.toml`, `azure-cosmos` moves from the `checkpoint` group into base dependencies first (retained code and the target Cosmos repository import it), then `langgraph-checkpoint-sqlite` (base), `langchain-azure-cosmosdb`, and the emptied `checkpoint` group go; in the `Dockerfile`, `--group checkpoint` is dropped from both `uv sync` lines and the `CMD`; mypy strict-override entries for deleted modules. The base `langgraph` runtime dependency is RETAINED for D-001 and is not a retirement target |

**Not retired:** the `ToolResult` pairing validator (real invariant, one enforcement point); the
base `langgraph` runtime dependency (D-001 compiles the graph against it; only
checkpoint-specific and superseded-graph extras go); `azure-cosmos` (moves to base; every Cosmos
read and the target repository import it); `retrieval/corpus.py` and `data/answer_key/topology.yaml`
(corpus preparation); `data/answer_key/build_goldens.py` (derives `golden_scenarios.yaml`; only its
numeric-evaluation output branches go); the `entraTenantId` template parameter (built-in
authentication).

**Reverse-direction classification.** Items present in the repository that the ledger had not
assigned, each now placed:

| Item | Disposition | Reason |
| --- | --- | --- |
| `azure-cosmos` in the `checkpoint` group | Retained, moved to base | Imported by `data/knowledge_records.py`, `data/operational_records.py`, `scripts/prepare_corpus.py`; the Cosmos repository needs it |
| `langchain-core` explicit base dependency | Retired with the superseded graph | Imported only by `graph.py` and `nodes/investigation.py`; `langgraph` carries it transitively where needed |
| `infra/main.bicep` `implementation` parameter, `OPSPILOT_IMPLEMENTATION` | Retired | Selects between superseded diagnosis paths |
| `entraApiAudience`, `entraApproverRole` parameters and settings | Retired | Hand-rolled token validation and approver role, replaced by built-in authentication |
| `entraConsoleClientId` parameter and setting | Retired | Console client |
| `entraTenantId` parameter | Retained | Built-in authentication needs the tenant |
| `eval/golden_incidents.json` | Retired | Triage-style expectations of the superseded diagnosis path |
| `eval/golden_retrieval.json` | Retired | Relevance labels for a retrieval metric the evaluation design does not carry |
| `data/answer_key/build_goldens.py` | Retained, narrowed | Derives `golden_scenarios.yaml`; its two JSON output branches go |
| `data/answer_key/topology.yaml` | Retained | Read by corpus preparation and by the answer-key tests |
| `llm` pytest marker text | Retained marker, reworded | Names Ollama and OpenAI providers the model seam drops |
| `.github/workflows/deploy.yml` `full` lane | Retired | Exists to install the eval group for the reranker; empty once the reranker goes |

## G. Complexity-reduction work

Places where implementation must shrink, not extend: the assessment (18 classes and 7 enums to
about 5 and 1); grounding (contract layer to one function and one flag); identity and state
(`turn_id` out everywhere; five bound fields on graph state, nothing else); persistence (six types
to one model and two methods); evidence and tool contracts (wrapper classes to fields, request
models to parameters, `LEGAL_PAIRINGS` table to an inline rule if smaller); the old evaluation
(replaced, not extended).

## H. Evaluation work

Simplify the authored-expectation shape to what the runner reads; build the runner; the harness
seam; the fixed-path control and the empirical R-29 measurement across candidate scenarios; the
retrieval-influence control on inc-007; the judge with one rubric; the report.

## I. Azure and runtime work

Replica range 0-1; Application Insights component and exporter wiring; startup, configuration,
and readiness records; Container Apps built-in authentication and removal of hand-rolled auth with
its template parameters and settings; keyless model access as the managed identity; dependency
moves and removals per section F; the smoke suite.

## J. Corpus and data work

None required. The corpus is repaired and reference-closed; the benign fixture exists. The
templated-error-telemetry observation stands as a note.

## K. Remaining implementation decisions

- The exact graph state field list, derived from `workflow-design.md` §11 and `system-design.md` §5,
  written once in code.
- Query-side identifier extraction for promotion: regex or token match against the corpus's
  extracted-identifier field. Small; no record needed.
- Whether the Cosmos write of the completed investigation needs any conditional; the design assumes
  a plain create with one writer.

## L. Mandatory plan rules

Every still-valid retirement, delete, or rewrite item in section F must be assigned to the
execution slice that owns the affected module. Rewriting the execution plan may not silently erase
retirement work.

Existing code survives only where the final design independently selected it; implementation
existence, test coverage, previous acceptance, and effort already spent are not retention reasons.
