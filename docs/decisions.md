# OpsPilot - Decisions

**Which concrete implementations were selected where the design left the choice open?**

## 1. Purpose and Boundaries

This document records only implementation-defining choices that higher-authority documents
explicitly left open.

`requirements.md` owns required behavior. `architecture.md`, `system-design.md`,
`workflow-design.md`, `data-and-evidence.md`, `runtime-and-deployment.md`, and `evaluation.md` own
the accepted design. Where those documents settled a choice, it is not repeated here.

This document originates the concrete selections assigned to it: where several implementations would
satisfy the accepted design, it picks one and states what that costs.

It does not restate architecture or requirements, does not preserve superseded history, and does not
record routine coding choices that constrain nothing beyond the code making them. Repository status
belongs to `status.md`; implementation sequence belongs to `execution-plan.md`.

---

## 2. Decision Summary

| ID | Decision | Status |
| --- | --- | --- |
| D-001 | Orchestration implementation | Accepted |
| D-002 | Model routing | Accepted |
| D-003 | Retrieval realization | Accepted |
| D-004 | MCP capability and realization | Pending library inspection |
| D-005 | Evaluation judge configuration | Accepted |
| D-006 | Evaluation scenario selections | Accepted |
| D-007 | Normalized incident-context contract | Accepted |
| D-008 | Evidence and knowledge reference encoding | Accepted |
| D-009 | Evaluation artifact storage | Accepted |

---

## 3. Accepted Decisions

### D-001 - Orchestration implementation

**Status:** Accepted

**Decision.** The turn executes as an explicit in-process state machine written in ordinary
application code. No orchestration framework, graph runtime, durable-execution library, or workflow
engine is adopted, and no checkpointing or replay feature is used.

**Why.** The accepted flow is five stages with one bounded back-edge, all inside one process, with
budgets that ordinary code already enforces. A framework would add a dependency and a second
execution model without enforcing anything the code cannot, and the durable-execution features that
justify such libraries are precisely the ones the design has removed.

**Accepted trade-off.** Stage transitions, continuation conditions, and bound enforcement are
hand-written and must be covered directly by tests rather than inherited from a library. There is no
framework-provided visualization or replay of a past run; reconstruction comes from telemetry.

**Rejected.** A graph orchestration framework, on the grounds that adopting one to demonstrate
framework usage would import durable-execution machinery the design forbids.

**Applies to.** `workflow-design.md` — "Investigation Stages"; `system-design.md` — "Technology
Responsibility Map"; FR-84, FR-85.

### D-002 - Model routing

**Status:** Accepted

**Decision.** Two chat deployments, selected by a fixed task label.

| Task | Deployment |
| --- | --- |
| Free-text intake normalization | Lower-cost |
| Supervisor objective interpretation | Primary |
| Evidence-source selection | Primary |
| Structured-query generation | Primary |
| RCA synthesis | Primary |
| Grounding correction | Primary |
| Follow-up answering | Primary |
| Offline evaluation judge | Primary |

Routing is by task label alone. It is not driven by incident severity, model confidence, dynamic cost
calculation, or inferred policy. Every model call records its task label and selected deployment in
telemetry.

Follow-up interaction classification is deterministic, established from the supported request shape,
and defaults to a question where ambiguous. It is not a model-routed task. Reranking is
deterministic and is not a model task (D-003). The pre-turn normalization routing signal is visible
in the intake response's technical detail and in telemetry; no separate event system carries it.

**Why.** Free-text normalization is short, bounded, and cheap to get slightly wrong: a poor
normalization costs the engineer one restatement. Everything that interprets evidence or produces an
assessment stays on the primary deployment, because a weak result there corrupts the brief;
follow-up answering restates retained evidence-bearing content, so it stays there for the same
reason. One task on the cheaper model is enough to demonstrate a deliberate routing decision without
spreading model variability into the investigative path.

**Accepted trade-off.** Two deployments must be provisioned and configured to demonstrate one
routing decision. A misclassified free-text intake costs a restatement.

**Rejected.** Severity tiers, policy engines, fallback chains, and dynamic cost optimization, none of
which the demonstration needs. Also rejected: routing any evidence-touching task, including retrieval
reranking, to the lower-cost deployment. D-003 keeps reranking deterministic so this boundary holds.

**Applies to.** `runtime-and-deployment.md` — "Model Connectivity"; `system-design.md` — "Shared
Model and Telemetry Seams"; `workflow-design.md` — "Follow-up"; FR-105, NFR-18.

### D-003 - Retrieval realization

**Status:** Accepted

**Decision.**

| Aspect | Choice |
| --- | --- |
| Chunking | One passage per document section, no overlap; short documents stay whole |
| Embedding | The Azure OpenAI embedding deployment already provisioned |
| Dense retrieval | Cosmos vector search over the stored passage embeddings |
| Exact identifiers | An identifiers field extracted at load time, matched with Cosmos string predicates |
| Lexical ranking | A small in-process term-overlap scorer, BM25-style, run over the filtered candidate passages |
| Fusion | Reciprocal rank fusion over the dense and lexical ranked lists |
| Reranking | Deterministic: exact-identifier matches, and requested entity or time-window metadata where available, stably promoted after fusion, then truncation to the passage budget |
| Bounds | At most 20 fused candidates, at most 5 passages supplied for reasoning |
| Storage | One categorized Cosmos knowledge container; a collection category field carries the three routed logical collections |

The identifier field answers whether a passage mentions a service name, error code, or deployment
identifier. It does not order results, so a lexical ranking method sits beside it: the in-process
scorer ranks the passages that survive metadata and identifier filtering. No search platform,
lexical index service, or external ranking service is adopted.

Reranking is deterministic and performs real reordering: after fusion, passages whose extracted
identifiers match the query's identifiers, or whose metadata matches a requested entity or window,
are stably promoted before the passage budget truncates the list. No model reranker exists in the
baseline. Adding one, or replacing Cosmos vector search with an in-process cosine scan if vector
indexing proves unsuitable at this corpus size, is an explicit revision to this record, never a
runtime fallback.

**Why.** The corpus is seven authored incidents and their supporting knowledge, already structured by
heading, so section-level passages need no overlap tuning and a scorer without a persistent index is
adequate. Reciprocal rank fusion combines two differently-scaled retrievers without calibrating
scores between them. Extracting identifiers at load time is what makes exact matching deterministic
rather than dependent on tokenization, and promoting identifier matches after fusion is what makes
the reranking stage do real observable work for exact-identifier trust (FR-90) at negligible cost.

**Accepted trade-off.** Section-level passages may be coarser than ideal for a long runbook. The
in-process scorer holds no index, so it rescans the filtered candidates on every query; that is
acceptable at this corpus size and would not be at a larger one. The bounds are engineering limits
chosen to keep context and cost predictable, not tuned values, and they are the first thing to
revisit if retrieval measurement shows recall loss.

**Rejected.** Routing reranking to the lower-cost deployment, which would put a model on an
evidence-touching path that D-002 keeps on the primary deployment or off the model entirely.

**Applies to.** `system-design.md` — "Knowledge retrieval and protocol transport";
`runtime-and-deployment.md` — "Retrieval and Structured-Query Realization"; `evaluation.md` —
"Retrieval Evaluation"; FR-89, FR-90, FR-91, FR-92.

### D-004 - MCP capability and realization

**Status:** Pending library inspection

**Decision.** Deployment and change history is the capability exposed through the protocol boundary.
It takes a service and a time window, returns one clearly typed observation, and carries no nested
result surface, so equivalence between the two paths is straightforward to assert and to test.

The realization is not settled. `runtime-and-deployment.md` already fixes where it runs: inside the
same container, as a companion process only where the selected library requires one. What remains is
which library, and the one concrete arrangement that follows from it.

**What inspection will settle.** Reading the candidate library's interface answers four questions,
and the answers determine the realization:

- whether the boundary can be served inside the application's existing asynchronous runtime, or the
  library requires a companion process;
- whether its transport works within a single container without a second ingress;
- whether the server can invoke the same registered capability implementation directly, rather than
  calling back into the application over the network;
- whether its request and result shapes carry the canonical two-axis outcome without a translation
  layer that could drift from the direct path.

The fourth is decisive. A library that forces its own result vocabulary would put a second
translation between the source and evidence admission, and parity would then rest on keeping two
translations aligned.

**Why.** A capability with a small stable parameter shape and one result type makes the boundary
demonstrable without making equivalence hard to assert. A larger result surface would add
demonstration cost without adding demonstration value.

**Accepted trade-off.** Parity is proven for one capability rather than across the surface, so a
divergence introduced in another adapter is not caught by this check. Leaving the realization pending
means the protocol boundary cannot be built until the library question is closed, though nothing else
depends on it.

**Applies to.** `system-design.md` — "Knowledge retrieval and protocol transport";
`runtime-and-deployment.md` — "Container Hosting and Cold Starts"; `evaluation.md` — "Tool,
Structured-Query, and Protocol Evaluation"; FR-104, NFR-44.

### D-005 - Evaluation judge configuration

**Status:** Accepted

**Decision.** The primary chat deployment acts as the single offline judge. Its rubric lives in a
versioned file in source control, and the rubric version is recorded on every evaluation run.

Output is one category per dimension, drawn from Meets, Partially meets, Misses, or Not applicable,
with a short rationale and the brief section or claim responsible for anything below Meets.

The judge runs offline only. It holds no runtime authority, never participates in a live turn, and
never influences an outcome shape. Where a deterministic check and the judge both bear on the same
property, the deterministic result stands.

**Why.** Judging output quality needs the stronger deployment, and a separate judge deployment would
add cost and configuration without changing what is judged. Categorical output keeps results readable
and stops a numeric score from becoming a target before a baseline exists.

**Accepted trade-off.** The judge and the system under evaluation share a model family, so a
systematic bias in that family is not independently detected. Deterministic checks and human sampling
are what mitigate it, and neither removes it.

**Applies to.** `evaluation.md` — "Model-Assisted Judge"; `runtime-and-deployment.md` — "Model
Connectivity"; NFR-25.

### D-006 - Evaluation scenario selections

**Status:** Accepted

**Decision.** The selection criteria were already settled; the corpus inspection this decision
waited on was performed on 2026-08-09, against a corpus whose repairs had landed and which is not
expected to change again. Each criterion now names real incident identifiers.

| Selection | Criteria | Selected |
| --- | --- | --- |
| Change-time scenario subset | One incident that reaches a supported conclusion through a short evidence path, chosen for the fastest end-to-end signal | inc-005 |
| Milestone set | All seven authored incidents | inc-001 through inc-007 |
| Repeatability subset | Three incidents covering one supported conclusion, one ambiguous or competing-hypothesis case, and one partial or inconclusive case | inc-005, inc-004, inc-006 |
| Further-evidence demonstration | One authored scenario or controlled fixture variant in which the RCA Analyst's further-evidence need fires and the Supervisor authorizes the cycle | inc-004, an authored scenario; no fixture variant is needed |
| Retrieval influence | One scenario in which retrieved knowledge materially influences the investigation: an authored scenario where the corpus naturally supports one, otherwise a controlled and credible fixture variant. If neither can demonstrate the influence, that is a corpus coverage gap requiring explicit resolution, never grounds to drop the demonstration | inc-007, an authored scenario; no fixture variant is needed |

**Why each.** inc-005 has the shortest supported path in the corpus (one log, three metrics, one
edge, and uniquely no deploy at all), so it reaches a conclusion with the fewest moving parts.
inc-004 is the only scenario carrying an authored `red_herring`, which is what makes it the
ambiguous case, and its externally unobservable third party is what leaves a question a first
evidence pass cannot close, which is what makes it the further-evidence case as well. inc-006 is
the corpus's only scenario where partial is a legitimate terminal shape rather than a failure:
establishing one of its two contributing conditions, and saying plainly that one does not explain
all signals, is a correct partial answer. inc-007 is a recurrence whose match is reached through a
postmortem's recurrence signature rather than through operational evidence, so retrieved knowledge
changes the investigation's path rather than decorating its result.

**One criterion is satisfied differently than its wording anticipates.** The repeatability subset
asks for "one partial or inconclusive case". No authored incident has partial or inconclusive as
its only acceptable outcome; all seven can reach complete. inc-006 is selected because its golden
record accepts complete or partial, making it the only scenario where a partial answer is correct
rather than a shortfall. Reading the criterion as requiring a scenario that can only fail would
have found nothing in this corpus and forced a fixture variant, which would demonstrate the
evaluation machinery rather than the system.

**Accepted trade-off.** inc-004 carries both the further-evidence and the ambiguous-case roles, so
a defect in that one scenario would weaken two demonstrations at once. It is selected for both
because it is genuinely the strongest candidate for each, and duplicating the roles onto a weaker
scenario to spread risk would make both demonstrations less convincing.

**Applies to.** `evaluation.md` — "Scenario Corpus and Coverage Audit"; `evaluation.md` —
"Repeatability and Before/After Comparison"; `evaluation.md` — "Evaluation Cadence".

### D-007 - Normalized incident-context contract

**Status:** Accepted

**Decision.** One typed, frozen contract, shared by both intake paths, carrying exactly five
fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `incident_id` | `str \| None` | The selected predefined RetailEase incident's id; `None` for free-text intake |
| `scope` | `str \| None` | The affected service or component, only when the intake source explicitly names one; `None` otherwise |
| `symptom` | `str` | The reported problem description: the incident's `short_description` for predefined intake, the engineer's literal input for free text |
| `time_anchor` | `datetime` | The operational anchor for initial evidence-window selection: the incident's `opened_at` for predefined intake, or the normalization/turn-start time for free text when no better incident time is known. Not asserted as the actual incident onset. |
| `supplied_context` | `str \| None` | Additional evidence or context the engineer supplies, seeding a new turn (FR-7); unpopulated by S-1's predefined-only intake |

No other field exists. In particular the contract carries no severity, priority, impact, urgency,
SLA, ownership, environment, ticket workflow state, or session/live-status field, and no evidence
reference: `system-design.md` §4.3's Evidence Investigator contract consumes normalized incident
context and "existing evidence and retrieved-knowledge references" as two separate, distinct
inputs, so seeding an initial evidence reference is not this contract's job: evidence exists only
through deterministic admission (`code-guidelines.md`), never through intake.

**`scope` for predefined intake, concretely.** The RetailEase `IncidentRecord`
(`tools/contracts.py`) carries no affected-service or component field, only `category` (e.g.
`"payment"`, `"datastore"`). `category` is a classification label, not a service/component
identity, and is not used to populate `scope`: putting a category into a component-shaped field
risks both semantic confusion and the corpus's own category-as-hint answer leakage. Consequently
`scope` is `None` for every predefined-intake turn until a source that actually names an affected
service or component exists.

**Why.** FR-1 through FR-3 require only that both intake paths converge on "the same structured
incident form" before investigation begins; nothing in FR-1 through FR-5, FR-7, or
`system-design.md`'s normalized-context boundary language calls for more than an anchor
identifier, an explicitly-known scope, the symptom itself, an operational time anchor for
retrieval and telemetry windowing, and optional supplied context. The raw predefined-incident
record (`IncidentRecord`, `tools/contracts.py`) carries `root_cause` and `resolution`, the
answer-key content the investigation exists to discover, so the contract deliberately excludes
them rather than deriving from the raw record directly; an investigation must reach its own
conclusion, never receive it as intake. It also excludes the record's ticket-workflow fields
(`priority`, `impact`, `urgency`, `made_sla`, `reassignment_count`, `state`, `number`,
`is_known_error`, `close_code`, `resolved_at`), none of which an accepted requirement reads at the
intake boundary. `time_anchor` is named and worded to keep a request-time fact from being read as
an incident-time fact: `opened_at` describes the incident, a free-text normalization timestamp
describes only the request, and collapsing both into one `observed_at`-style name would make the
free-text value look like evidence about when the incident occurred.

**Accepted trade-off.** Predefined intake discards most of the raw `IncidentRecord`'s operational
metadata even where a future feature might want it. Re-adding any of it is a revision to this
record, never a silent field addition.

**Rejected.** A general incident-intake schema mirroring the full ITSM ticket shape (severity
tiers, ownership, environment taxonomy, ticket metadata), and embedding session or workflow status
in the contract. Neither is required by `requirements.md`, and each would blur the intake boundary
with a concept owned elsewhere: live status is `workflow-design.md` §9's vocabulary, and
ticket-shaped fields belong to the operational-records tool surface a turn queries as evidence, not
to what a turn starts from. Also rejected: populating `scope` from `IncidentRecord.category`,
which conflates a classification label with a component identity and risks leaking the category as
an answer hint; and an `initial_evidence_refs` field, since the design keeps normalized context and
evidence references as two structurally separate inputs (see above) and evidence exists only
through deterministic admission, never through intake.

**Applies to.** `system-design.md`: "Investigation, Turn, and Live-Session Model";
`data-and-evidence.md`: "Identity and Reference Model"; FR-1, FR-2, FR-3, FR-5, FR-7.

### D-008 - Evidence and knowledge reference encoding

**Status:** Accepted

**Decision.** The reference grammar authored in `data/answer_key/README.md` becomes the canonical
encoding for both reference types. Eight prefixes exist, and the prefix is the declared static
discriminator for reference type.

| Reference type | Prefix | Key structure |
| --- | --- | --- |
| Evidence | `logs` | `logs:<service>:<event_id>` |
| Evidence | `metrics` | `metrics:<service or infra entity>:<metric>@<ts>` |
| Evidence | `deploys` | `deploys:<service>:<deploy_id>` |
| Evidence | `deps` | `deps:<from>-><to>` |
| Evidence | `absence` | `absence:<capability>:<operation_ref>` |
| Knowledge | `runbook` | `runbook:<doc_id>` |
| Knowledge | `architecture` | `architecture:<doc_id>` |
| Knowledge | `postmortem` | `postmortem:<incident_id>` |

Exactly one prefix-to-type map holds that classification, owned by the reference module, and it is
the only place the classification is stated. No component maintains its own prefix list, derives the
type from a source name, or infers it from which capability produced the reference. Because type
follows from the prefix alone, citation-role compatibility is decidable deterministically: an
evidence reference may occupy any citation role, and a knowledge reference only the historical or
contextual role, with no model judgment involved.

`postmortem:<incident_id>` is the canonical spelling for a historical incident document.
`past_incident:<incident_id>` is retired. Both spellings naming one underlying document would defeat
a single resolver and corrupt admission's duplicate check, so the two do not coexist beyond the
slice that deletes the runtime still emitting the retired form.

`absence:<capability>:<operation_ref>` names an authoritative empty result: the approved capability
executed successfully over the recorded scope and observed no matching item. A `succeeded` and
`empty` result is admitted as a positive observation, and every admitted observation carries an
evidence reference, so this form is what that observation is assigned. Without it the finding would
be uncitable, because the only identity available would be the operation reference, and a citation
never points only at an operation reference.

The two identities stay distinct. The operation reference names an attempt and remains preserved
separately as provenance; it is not a reference to an observation and is rejected on its own by the
evidence-reference parser. The absence form embeds it to make the admitted observation's identity
stable, and the embedding does not make the bare operation reference citable.

`absence:` classifies the reference as operational evidence and introduces no evidence type. The
evidence type of an authoritative absence continues to come from the static
capability-to-evidence-type mapping, so an empty log query remains the log evidence type its
capability observes; the reference uses `absence:` only because no concrete row exists to identify.
It resolves to the admitted absence observation, which carries the queried scope and the explicit
nothing-matched marker, rather than to a source row whose non-existence is the finding.

`architecture:` is a knowledge reference. It is retrievable and may orient an investigation, but the
citation-role rules keep it out of the roles reserved for current operational proof. That
restriction is expressed once, through the reference type and the citation-role contract, rather
than as special-case handling repeated at each call site.

A capability reports the provenance identifying what it returned. Admission assigns the evidence
reference. The two are not the same act, and the capability is not the owner of canonical reference
construction.

**Why.** The grammar already satisfies what the accepted design requires of a reference, which is
why it is adopted rather than replaced. Its keys are corpus row identities: event identifiers,
deployment identifiers, metric samples on an authored interval boundary, and edges that must exist
in the topology. A reference built from them resolves after the completed turn is persisted without
consulting turn-local state, which is what post-persistence resolution and deterministic citation
checking both need, and it gives admission a natural duplicate key at no additional cost.

What the grammar lacked is the explicit type axis, and that gap is the reason this record exists
rather than a note pointing at the answer key. Reference type is what makes role compatibility
decidable by inspection, so leaving it implicit in a prefix that no component authoritatively
interprets would push the decision into whichever code inspected the string first.

Making admission the assigner of the evidence reference follows from admission being the only door
into the evidence set. A capability that named its own evidence references would be creating
evidence identity outside admission, which inverts that boundary.

**Accepted trade-off.** The encoding is shaped around the bounded RetailEase corpus. A source with a
different identity scheme would require a new prefix and its resolver registered in the same central
map, which is a deliberate, visible change rather than an automatic accommodation. Deterministic
resolution and simple grounding are worth more here than source-agnostic abstraction.

**Rejected.** A generic URI scheme, an opaque identifier layer resolved through a stored lookup, and
any plugin or registration abstraction adopted to avoid the trade-off above. Each would add
indirection between a citation and the thing it names, and would move resolution from string
inspection to a runtime lookup that can fail. Also rejected: retaining both postmortem spellings
behind a normalization step, which would preserve the ambiguity rather than remove it.

**Applies to.** `data-and-evidence.md`: "Identity and Reference Model"; `data-and-evidence.md`:
"Evidence Admission"; NFR-3, NFR-12, NFR-15.

### D-009 - Evaluation artifact storage

**Status:** Accepted

**Decision.** Evaluation artifacts are files under the existing `eval/` tree, in three locations
separated by whether the artifact is authoritative.

| Location | Contents | Version control |
| --- | --- | --- |
| `eval/fixtures/` | Deterministic evaluation fixtures | Committed |
| `eval/reports/` | Reference reports and baselines retained for comparison | Committed |
| `eval/runs/` | Dated live-run outputs | Ignored |

Authored golden scenario truth stays under `data/answer_key/`. It is consumed by evaluation, not
produced by it, and it does not move into `eval/fixtures/`. Generated artifacts already under
`eval/` keep their existing generated-never-hand-edited semantics.

**Why.** The accepted design had already settled everything except the layout: artifacts are files
belonging to a run, retained alongside it and separately from the completed turns they reference,
and never held by the running system. Three directories separated by authority express that
directly. Committed fixtures and reports are the artifacts a reader compares against; run outputs
are working material.

Golden records stay with the corpus because the accepted design already places them there: a golden
scenario is authored alongside the corpus, which makes it an input to evaluation rather than one of
its outputs. Moving it under `eval/` would create a second home for information that already has
one.

**Accepted trade-off.** `eval/runs/` is not version controlled, so comparison across arbitrary
historical live runs depends on local retention. A run worth keeping is promoted deliberately into
`eval/reports/` and becomes a reference artifact. That cost is accepted because the alternative is a
durable run store, which the accepted design rejects.

**Rejected.** An evaluation database, a run-history service, a dashboard, a telemetry-backed
evaluation store, a warehouse, and any additional hosted resource. Each would make evaluation a
runtime component, which it is not.

**Applies to.** `evaluation.md`: "Evaluation Inputs and Artifacts"; `evaluation.md`: "Golden
Scenario Model"; `evaluation.md`: "Reporting"; NFR-55.

---
