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
| D-006 | Evaluation scenario selections | Pending corpus inspection |
| D-007 | Normalized incident-context contract | Accepted |

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

---

## 4. Pending Corpus Item

### D-006 - Evaluation scenario selections

**Status:** Pending corpus inspection

**Decision.** The selection criteria are settled. Which authored incident satisfies each is not,
because no design document names the authored incidents.

| Selection | Criteria |
| --- | --- |
| Change-time scenario subset | One incident that reaches a supported conclusion through a short evidence path, chosen for the fastest end-to-end signal |
| Milestone set | All seven authored incidents |
| Repeatability subset | Three incidents covering one supported conclusion, one ambiguous or competing-hypothesis case, and one partial or inconclusive case |
| Further-evidence demonstration | One authored scenario or controlled fixture variant in which the RCA Analyst's further-evidence need fires and the Supervisor authorizes the cycle |
| Retrieval influence | One scenario in which retrieved knowledge materially influences the investigation: an authored scenario where the corpus naturally supports one, otherwise a controlled and credible fixture variant. If neither can demonstrate the influence, that is a corpus coverage gap requiring explicit resolution, never grounds to drop the demonstration |

**What inspection will settle.** Reading the authored corpus assigns an incident identifier to each
criterion above, and confirms that an incident satisfying each criterion exists. The coverage audit
in `evaluation.md` is what surfaces a criterion no authored incident currently meets.

**Why.** The criteria are what implementation needs in order to wire the evaluation runs; the
identifiers are a corpus lookup. Naming identifiers without reading the corpus would invent them, and
a wrong identifier here is worse than an absent one because it would silently select the wrong
scenario.

**Accepted trade-off.** Evaluation runs cannot be wired to specific scenarios until the lookup is
done. Nothing else waits on it.

**Applies to.** `evaluation.md` — "Scenario Corpus and Coverage Audit"; `evaluation.md` —
"Repeatability and Before/After Comparison"; `evaluation.md` — "Evaluation Cadence".

---
