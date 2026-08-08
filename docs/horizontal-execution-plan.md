# OpsPilot - Horizontal Execution Plan

**In what sequence is the gap between the design and the repository closed?**

This document sequences the work. It converts `status.md` - "Deletion and Replacement Register" and
`status.md` - "Detailed Missing and Partial Implementation Register" into vertical slices, ordered
so that each horizontal layer is complete before the next begins, and it states what must be true at
the end of each slice and each layer.

It does not restate what is missing. `status.md` - "Detailed Missing and Partial Implementation
Register" is the canonical inventory of absence, and every slice below cites its entries by their
own wording. It does not restate why a choice was made; `decisions.md` owns that. It carries no
dates, no estimates, and no ordering beyond dependency.

References into `status.md` name headings rather than section numbers, so a citation survives
renumbering and stays greppable. A register entry is cited by its own wording for the same reason.

The gap it closes was measured at the commit `status.md` - "Document Status" names. No verdict is
re-derived here.

## How to read a slice

Each slice is one coherent behavior, reviewable in one sitting, and leaves the repository working. A
slice that cannot leave the tree green is too big. Nothing is committed until the local pass for
that slice is reviewed.

Each slice states what it makes true, the required behavior it closes and the Delete or Replace rows
it retires, both cited by their own wording, whether the change is new code or a rewrite, the tests
whose necessity a reviewer would not predict, its evaluation and observability obligations where it
has them, what a deployed check proves differently afterwards, and what must hold for the next slice
to rely on it.

Ordinary unit and integration tests are assumed and are not enumerated. The testing that is
enumerated is the agentic and evaluation testing the design has the most to say about.

Deletion happens inside the slice that supersedes the behavior. A Delete row carrying a Replacement,
and every Replace row, is a replaces-does-not-extend pairing: its replacement and its removal are
the same slice wherever the code allows it. Several rows span two slices, and each says where its
other half lands.

Evaluation is advisory and gates no merge (`evaluation.md` §2). No numeric target is set before a
measured baseline exists (`evaluation.md` §19).

## The layers

Nine layers. Each layer's definition of done is what makes the next layer safe to build on.

1. Ground-truth corpus
2. Deterministic tools
3. Retrieval
4. LLM behavior
5. Protocol boundary and persistence
6. Reasoning integrity
7. Transport
8. Infrastructure
9. Remaining features

A slice belongs to the layer whose safety it establishes, not to the document that owns its
contract. An Azure resource is provisioned inside the layer whose correctness depends on it: the
Cosmos containers and the embedding deployment in layer 1, the two chat deployments in layer 4.
Layer 8 owns what remains of deployment realization and all of operational verification.

Two consequences of this order are stated here rather than discovered later. An end-to-end turn is
first runnable in process at the end of layer 6, and first reachable by an engineer in layer 7.
Between slice 5.2 and slice 7.1 the deployed application serves health and no turn surface; the tree
stays green and the deterministic tests and evaluation harness drive turns directly.

---

## Preparation, before Layer 1

Repository and cloud state is settled before the plan runs, not inside it. The three items below are
preparation and not slices: they close no register entry, carry no tests, and have no definition of
done in the slice sense. They exist so that no slice below inherits a question about what is in the
tree or what is running in the subscription.

**Repository baseline.** Bring `main` to a known clean state and push it before anything is deleted.
The order matters and is the whole point of doing this first: a file deleted from `main` remains in
`main`'s history and can be recovered, while an unmerged branch deleted from the remote does not and
cannot. Anything worth keeping on a branch is therefore cherry-picked onto `main` before that branch
is deleted, and nothing is preserved by keeping a branch alive. Then confirm what each stale remote
branch actually contains, and delete the rest. `status.md` - "Deletion and Replacement Register",
Delete: "Stray/stale: `out.txt`, `raw.txt`, `infra/.gitkeep`, `data/.gitkeep`,
`tests/__pycache__/_scratch_proposed...pyc`, stale remote branches" names the debris and the six
branches; `status.md` - "Documentation and Repository Hygiene" records the same list together with
the stale `README.md` and `.env.example` and the untracked `docs/` and `.githooks/` that are
committed here.

The unpushed WIP commit `status.md` - "Document Status" records on `stage-5f-durable-dispatch` is
confirmed as abandoned or cherry-picked, and then dropped. That discharges Delete: "WIP commit
`0c3c175` (`dispatch.py` 349 ln, `worker.py` 183 ln, lease/epoch machinery, Service Bus config)"
here rather than in any slice, so no slice below deletes the dispatch or worker modules. It also
clears the 31 failing tests and the two `mypy` errors `status.md` - "Verification and Test Results"
attributes to that commit, so every slice starts from a green tree.

**Azure orphans.** Resources that no template declares and that are not part of OpsPilot are deleted
directly with the CLI. Bicep declares desired state; it does not remove what it never owned, so an
undeclared resource is not removed by any template change in layer 8. `status.md` - "Deletion and
Replacement Register", Delete: "Live orphan: `rytesting` (Microsoft.CognitiveServices/accounts, kind
AIServices) + `rytesting/proj-default` in `rg-opspilot`" is the one such resource, and `status.md` -
"Azure and Deployment Status" records it as the only live resource in `rg-opspilot` outside the
template. These deletions belong to no slice and are not added to the template.

**Live containers the template will stop declaring.** A template that no longer mentions a container
does not delete it from the account either. The `checkpoints` and `investigation-index` containers
are therefore deleted with the CLI, not by Bicep, and they are deleted when the persistence slice
lands, which is 5.2. This is the one preparation item that is sequenced rather than done up front,
because the live containers cannot go before the code that reads them does. The checkpointer stack
itself is retired in 6.1, so `checkpoints` has no writer left after that slice either.

---

## Layer 1 - Ground-truth corpus

**What it makes safe.** Everything above this layer is measured or queried against a fixed corpus.
Until the corpus is loaded where the design says it lives, carries the provenance and metadata that
admission filters and retrieval filters read, and has a golden record per authored incident, no
measurement above it means anything and no retrieval or capability slice can be verified.

**Definition of done.** The corpus defects `status.md` - "Data and Corpus Status" records as
blocking the affected demonstrations are repaired; the seven authored incidents each carry a golden
scenario record of the shape `evaluation.md` §5 fixes; the coverage audit of `evaluation.md` §4 has
been run and its result recorded, with the scenario selections named only after the repairs land;
the knowledge and operational-records containers exist, are populated by the setup identity, and
carry collection category, provenance, extracted identifiers, and entity and time metadata; and the
application identity holds read-only access to both.

### 1.1 Corpus repairs

**Makes true.** The authored corpus tells a physically coherent story with no leaked answers, and
all five scenario classes are represented in what it contains.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Corpus
preparation: "Credible chronology and mechanism-consistent telemetry," "No answer leakage,"
"Five-class evaluation coverage," and "Controlled variants clearly distinct from authored
incidents."

**Retires.** Nothing. The evaluation input surface the golden records replace is retired in 1.2 with
the records that replace it.

**Shape.** Repair, not replacement. The corrections are to generated telemetry and authored notes:
the contradictory series, the effect-before-cause orderings, and the answer leakage `status.md` -
"Data and Corpus Status" enumerates. Coverage is closed within the accepted seven-incident scope,
which that section records as revising one existing authored incident for the multi-contributor
class and representing the benign or transient class through a controlled non-incident fixture
derived from the existing ambient events. Nothing here authors an eighth incident and nothing here
writes a golden record.

**Tests.** Two properties the existing closure gates do not catch belong here, because `status.md` -
"Data and Corpus Status" records both as currently failing: a repaired series must move in the
direction its own postmortem narrates, and no tool-visible field may name the answer. The gates that
already pass must still pass after the repairs, so reference closure is re-run rather than assumed:
that section records all 42 evidence and 22 retrieval references as resolving today, and a repair
that breaks one is a regression rather than a new finding.

**Evaluation.** Nothing is scored here. This slice exists so that what is scored later is scored
against a corpus that does not contradict itself.

**Done when.** The corpus defects `status.md` - "Data and Corpus Status" records as blocking the
affected demonstrations are repaired; the multi-contributor and benign or transient classes are
represented; reference closure still verifies; and the corpus is not expected to change again for
the rest of the plan.

### 1.2 Golden scenario records, the coverage audit, and the D-006 selections

**Makes true.** Each authored incident carries one golden record stating what a correct
investigation must establish, the corpus has been audited against the five scenario classes, and the
scenario selections are named against real incident identifiers.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Evaluation:
"Golden scenario records of accepted shape."

**Retires.** `status.md` - "Deletion and Replacement Register", Delete: "`eval/wild.py`,
`record_wild.py`, `wild_scorecard.json`, `wild_single_agent.json` cassette (manifest-less,
unreplayable), `tests/fixtures/wild_ob/`, RCAEval profile dependence," which the same register lists
again under "No accepted slot or explicitly deferred" as "RCAEval wild generalization probe." The
probe is the evaluation input surface the golden records replace, and `requirements.md` §12 defers
the capability it demonstrates. The wild-probe test goes with it.

**Shape.** New authored records beside the existing answer key. The answer key and its projection
are not rewritten; the golden record is the evaluation-facing artifact authored from them.

**Why it follows 1.1.** The records and the selections are written against a corpus that no longer
moves. `status.md` - "Implementation Clarifications Exposed by the Repository", "D-006 evidence"
holds the selections until the required repairs and the coverage audit are done, and the reason is
substantive rather than procedural: the repairs change what there is to select from. The
multi-contributor class exists only after one incident is revised, the benign class only after the
controlled fixture exists, and a record authored against an uncorrected series would state an
expectation the repaired corpus no longer supports.

**Tests.** The closure discipline that already ties the answer key to the generated telemetry
extends to the golden records: every evidence reference a golden record requires must exist in the
repaired corpus. A golden record naming evidence the corpus cannot produce is a corpus gap, not a
test failure to tolerate.

**Evaluation.** This is the input every later scenario-outcome measurement reads. The scenario
selections D-006 leaves pending are recorded here against the candidate mapping `status.md` - "Data
and Corpus Status" already supplies: the change-time subset, the milestone set, the repeatability
subset, the further-evidence demonstration, and the retrieval-influence scenario. Naming them is a
corpus lookup rather than a decision this plan makes.

**Done when.** Every authored incident has a golden record of the shape `evaluation.md` §5 fixes;
the audit table has one row per scenario class, with the multi-contributor and benign classes
recorded as represented; and the scenario selections D-006 lists are named against real incident
identifiers.

### 1.3 Corpus preparation into the RetailEase containers

**Makes true.** The corpus is loaded, chunked, embedded, and indexed into the containers the design
reads at runtime, by a setup identity separate from the application's.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Investigation
Record and persistence: "One categorized `knowledge` container" and "One `operational-records`
container"; Retrieval: "Categorized `knowledge` container," "Azure OpenAI embeddings," and
"Identifier extraction and category metadata at load time"; Corpus preparation: "Categorized
knowledge metadata and embeddings" and "Operational-records seed process."

**Retires.** `status.md` - "Deletion and Replacement Register", "No accepted slot or explicitly
deferred": "External ITSM/RCAEval profile-calibration pipeline." The corpus is authored, and nothing
in the design derives telemetry proportions from an external dataset.

**Shape.** New offline preparation task with its own identity and its own write access
(`system-design.md` §8.4, "Corpus preparation"). It is not a component, participates in no turn, and
is reachable from no runtime code. The authored corpus files stay as the source it reads.

**Tests.** The preparation is verified by reading back what it wrote: one passage per document
section with no overlap, short documents whole, the collection category on every knowledge document,
the extracted identifiers field populated for the service names, error codes, and deployment
identifiers the golden records designate, and entity and time metadata present where retrieval
filters on them. Absent preparation is a deployment-time failure and must present as one.

**Observability.** Offline, outside the telemetry seam. Its result is verified by inspection, not by
runtime emission.

**Deployment verification.** Cosmos permissions become checkable: the application is refused a write
to either RetailEase container (`runtime-and-deployment.md` §16, check 4).

**Done when.** Both RetailEase containers are populated from the authored corpus, the embedding
deployment is provisioned and used at load time, the setup identity is the only writer, and a re-run
of the preparation produces the same passages and the same identifiers.

---

## Layer 2 - Deterministic tools

**What it makes safe.** Every layer above reasons over evidence. This layer makes it impossible for
anything to become evidence except through admission, impossible for a result to hide whether its
source answered, and impossible for a capability to be reached without passing dispatch. Until that
holds, a reasoning slice above cannot be trusted to fail closed.

**Definition of done.** Every capability result carries a legal execution-outcome and completeness
pairing; every observation in turn state arrived through admission with a stable reference, a type,
a completeness, and its provenance; every operation that did not answer produced a limitation and no
observation; the registry is the only path to a source; and the governed structured-query path
validates and executes deterministically against fixture truth.

### 2.1 The canonical two-axis result contract

**Makes true.** One result model covers every capability, answering separately whether the operation
executed and how complete its answer was.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Evidence Access
Layer and admission: "Two-axis result vocabulary," which that register records as scaffolded by the
existing envelope with the binary status to be replaced.

**Retires.** `status.md` - "Deletion and Replacement Register", "Misaligned implementations":
"Binary tool-result status."

**Shape.** Rewrite. The envelope in `tools/contracts.py` survives as a shape; its status field and
every adapter's use of it do not. Each adapter translates its provider outcome into the two axes
(`data-and-evidence.md` §4), and an invalid pairing is rejected at the adapter boundary as a defect
in that adapter (`code-guidelines.md` §6).

**Retires with it.** The status-envelope assertions in the tool tests, which assert the collapsed
vocabulary the design prohibits.

**Tests.** The distinction a reviewer would not think to protect is `succeeded` with `empty` against
`unavailable`. A source that answered authoritatively with nothing and a source that did not answer
must be separately representable, separately admitted, and separately visible downstream; collapsing
them turns an unreachable source into a clean bill of health.

**Evaluation.** Result-vocabulary validity becomes a deterministic conformance check
(`evaluation.md` §7).

**Observability.** The tool and capability boundary emits both axes, not a success flag.

**Done when.** No path can produce a result outside the legal pairings, and no code reads a tool
result as a boolean.

### 2.2 Capability adapters over the operational-records container

**Makes true.** The five operational capabilities read the operational-records container through the
registry, with validated parameters, scope limits, and the deadline they were given.

**Closes.** No required behavior. `status.md` - "Detailed Missing and Partial Implementation
Register", Evidence Access Layer and admission records "Closed static capability registry" as
implemented and reusable and "Read-only operational capabilities" as implemented and well tested;
this slice is the consumer half of the containers closed in 1.3.

**Retires.** `status.md` - "Deletion and Replacement Register", "Duplicated logic to collapse":
"Corpus path resolution," whose two owners disappear with the file-backed corpus repository, and
"Read-only capability inventory," which collapses into the explicit static capability registry.

**Shape.** Heavy modification of the existing adapters: same capability surface, different source.
The registry stays an explicit static mapping with no dynamic registration (`code-guidelines.md`
§6).

**Tests.** Deadline propagation is the non-obvious one. Every source operation must receive a
timeout no greater than the turn's remaining time, and a call that outlives its turn is a bound
violation even when it returns correct data (`code-guidelines.md` §7).

**Observability.** Capability execution emits through the tool boundary with the correlation context
attached where the work enters it.

**Deployment verification.** The read-only role assignment, not application convention, is what
refuses a write; a capability constructed to mutate must fail on the role.

**Done when.** No adapter reads the corpus from the image, no path reaches a source without dispatch
validation, and every capability carries a bounded timeout.

### 2.3 Evidence admission, limitations, and the operation ledger

**Makes true.** A normalized result becomes evidence only by passing deterministic admission, which
assigns its reference, and everything that did not answer becomes a limitation instead.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Evidence Access
Layer and admission: "Deterministic evidence admission," "Stable admitted-evidence and limitation
structures," and "`succeeded + empty` represented as a positive observation."

**Unmapped citation.** The sequence previously closed a separate entry for the evidence ledger, the
tool-operation history kept apart from cited evidence. The current register has no row of its own
for it, so this slice treats it as part of "Stable admitted-evidence and limitation structures"
rather than dropping it. That is a gap between the plan and the register, not a change of scope.

**Retires.** `status.md` - "Deletion and Replacement Register", "Duplicated logic to collapse":
"Evidence-reference parsing," whose two parsers become one reference model owned by admission.

**Shape.** New admission code inside the Evidence Access Layer, plus a rewrite of the evidence half
of turn state. The hash-keyed first-seen-wins merge that keeps contradictory observations separate
survives and is what the admitted set is built on; the existing admission module, which admits
model-proposed claims, is a different thing and is untouched here.

**Blocked detail.** `status.md` - "Implementation Clarifications Exposed by the Repository",
"Evidence and knowledge reference encoding" records that deterministic resolution needs one owner
for prefixes, keys, and parsing. This slice cannot assign a reference without that being settled.
The repository's frozen grammar is a candidate to be evaluated rather than copied, and choosing it
is a decision for `decisions.md`, not for this plan.

**Tests.** Two properties a reviewer would not predict. First, admission must refuse anything whose
execution outcome is not `succeeded`, including a result that carries plausible content alongside a
failure, so no path can construct an admitted observation outside admission. Second, a `partial`
observation stays marked partial wherever it travels, because a claim resting on it must be able to
disclose what it did not see.

**Evaluation.** "No fabricated observations" becomes a deterministic conformance check
(`evaluation.md` §7).

**Observability.** Evidence admission is emitted at the capability boundary, carrying the operation
reference, the assigned evidence reference, and the completeness.

**Done when.** Evidence exists in turn state only where admission put it, every non-answering
operation has a limitation naming the question it failed to answer, and the operation history is
separate from the admitted set.

### 2.4 The governed structured-query path

**Makes true.** A bounded query structure over an approved schema context is validated
deterministically and executed read-only under a limit and a timeout, and its result admits like any
other.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Governed
structured query: "Approved operational-records surface," "Canonical query structure with
predicates, projection, and COUNT," "Mandatory scope, result limit, and timeout," "Decode or
validation rejection before execution," "Fixture-truth and rejection tests," and "No grouping,
ordering, joins, writes, or non-count aggregates in baseline," which that register records as an
absence the future contract must preserve.

**Retires.** Nothing. The capability is absent, not misplaced.

**Shape.** New. The structure is the baseline subset `system-design.md` §8.2 fixes: one approved
collection, the listed predicate forms, a named projection or the count aggregate, and a limit
always present and at or below the ceiling. Grouping, ordering, and non-count aggregates have no
representable form.

**Tests.** The generation half is not present yet, so this slice is exercised with authored query
structures. The check that matters is the one a reviewer would expect to be redundant: a structure
that is well formed but references a surface the request was not granted must be rejected before
execution, and a rejected query must produce a limitation rather than an empty result. Fixture-truth
comparison over normalized output belongs here too, so the evaluation layer aggregates it rather
than reimplementing it (`evaluation.md` §11).

**Evaluation.** Structured-query correctness and the read-only behavior check both become measurable
against fixtures (`evaluation.md` §7).

**Observability.** Structured-query operations emit at the capability boundary with the same outcome
and completeness axes as any other.

**Done when.** No query text is constructed anywhere, an out-of-surface or mutating structure is
unrepresentable or rejected before execution, and results admit through 2.3.

---

## Layer 3 - Retrieval

**What it makes safe.** Reasoning above this layer must be able to read what was retrieved. A layer
that returns pointers gives the LLM behavior above it nothing to reason over, and every retrieval
measurement and the lexical baseline depend on the same path being the one the system actually runs.

**Definition of done.** A retrieval request returns the matched passage itself with its source,
collection, and provenance; routing selects a collection category; dense and lexical candidates are
fused and deterministically reranked within the passage budget; and retrieval precision, recall, the
no-zero-retrieval floor, and exact-identifier survival are measurable against the golden records.

### 3.1 Passage retrieval over the knowledge container

**Makes true.** Retrieval reads the prepared knowledge container and returns passages, not document
identifiers.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Retrieval:
"Passage-bearing semantic retrieval."

**Retires.** `status.md` - "Deletion and Replacement Register", "Misaligned implementations":
"Retrieval returns pointers without passages" and "Local sentence-transformers embeddings"; and "No
accepted slot or explicitly deferred": "Local transformer vector-index stack."

**Shape.** Rewrite of the retrieval subsystem's storage and result shape. What survives is what the
same register records as implemented and reusable: "Lexical retrieval" and "Reciprocal-rank fusion,"
together with the section-level chunking and metadata filtering `status.md` - "Detailed State by
Design Area", "Retrieval" records as aligned with D-003. What changes is where passages live, what a
hit carries, and which embedder produces the query vector. Query-time embedding moves to the Azure
OpenAI deployment provisioned in 1.3, which is what leaves the local embedder with no consumer.

**Blocked detail.** `status.md` - "Implementation Clarifications Exposed by the Repository", "D-003
vector viability" records that no Cosmos vector-index configuration exists anywhere. Viability is
verified before this slice chooses its implementation, and the alternative, an in-process cosine
scan, requires an explicitly recorded revision to D-003 rather than a runtime fallback. Neither the
verification result nor the revision is decided here.

**Retires with it.** Nothing in the retrieval tests yet; the reranker cases are retired in 3.2.

**Tests.** Collection routing is the property worth asserting deliberately: a request that names no
collection must route from the question shape, so procedural questions favor runbooks, structural
questions favor service knowledge, and precedent questions favor prior incidents. A
pointer-returning regression is invisible in every other assertion, so the retrieved element must be
asserted to carry the passage text itself.

**Evaluation.** Retrieval cases become runnable: precision, recall, whether at least one expected
item was retrieved, collection-routing correctness, and whether the passage rather than an
identifier reached reasoning (`evaluation.md` §10).

**Observability.** Retrieval operations emit at the capability boundary with the collection, the
outcome, and the completeness.

**Done when.** No retrieval result reaches reasoning as an identifier, no local embedding model is
loaded at runtime, and retrieval reads the container 1.3 populated.

### 3.2 Deterministic reranking and retrieval measurement

**Makes true.** Reranking performs real reordering deterministically, and retrieval measurement runs
against the lexical baseline.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Retrieval:
"Deterministic identifier and metadata promotion" and "Passage-budget truncation after promotion";
Evaluation: "Lexical-only baseline."

**Retires.** `status.md` - "Deletion and Replacement Register", Delete: "Unreachable model reranker:
`retrieval/reranker.py`, `Retriever.rerank()`, `RERANK_CANDIDATES`, `reranker` test marker,
`bge-reranker` references," which carries "Deterministic identifier/metadata promotion" as its
Replacement and so pairs its removal with this slice's build; "Misaligned implementations":
"CrossEncoder model reranker"; and "Duplicated logic to collapse": "Embedding/reranker model names,"
whose second definition goes with the reranker.

**Shape.** Rewrite of the reranking stage. After fusion, passages whose extracted identifiers match
the query's identifiers, or whose metadata matches a requested entity or window, are stably promoted
before the passage budget truncates the list (D-003). No model participates.

**Tests.** Reranking is the stage that can silently disappear, because plain truncation still
returns passages that look reasonable. The assertion must be that a passage matching a designated
exact identifier surfaces above its fused position, not merely that it is present.

**Evaluation.** The lexical retrieval baseline becomes runnable here, over the same cases as the
selected hybrid path (`evaluation.md` §10). This slice produces the first values worth recording:
retrieval precision and recall per case, by collection, split between identifier-oriented and
semantic queries. They are recorded as observations. No threshold is set from them (`evaluation.md`
§19).

**Done when.** Identifier promotion is observable in the ordering, the passage budget is the only
truncation, and one retrieval measurement run has been recorded against the lexical baseline.

---

## Layer 4 - LLM behavior

**What it makes safe.** The layers above coordinate agents and validate what they produce. That is
only meaningful once each model task is a named task on a named deployment, every model output is
proposed data admitted by code against a typed contract, and the roles are separated so that the
agent which gathers is not the agent which concludes.

**Definition of done.** Every model call carries its task label, role, investigation, and turn, and
records the deployment that served it; no model output reaches a decision without being parsed,
validated, and admitted; the Evidence Investigator selects sources and proposes continuation without
concluding; and the RCA Analyst is the sole producer of one structured assessment per turn carrying
no numeric confidence anywhere.

Every slice in this layer changes recorded model interactions. Cassette re-recording is a real cost
here and is incurred four times; slices are drawn so that no slice re-records for a change another
slice will re-record again.

### 4.1 The model-access seam and task-label routing

**Makes true.** All three agent roles and the interaction interface reach models through one
adapter, and routing selects a deployment from a fixed task label.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Azure and
deployment: "Primary, lower-cost, and embedding deployments," whose embedding member was provisioned
in 1.3; and Telemetry and activity: "Model task labels and usage totals," of which this slice closes
the task labels and 9.1 closes the totals.

**Retires.** `status.md` - "Deletion and Replacement Register", Delete: "Dead config: `PROD_MODELS`,
`Tier`, `SEVERITY_TIER`, `resolve_tier`, `ENABLE_OPUS_SEV1`, `JUDGE_MODEL` (as-is),
`MAX_TOOL_CALLS`, `CONFIDENCE_THRESHOLD`, `LANGSMITH_ENABLED`, dispatch knobs," which carries "D-002
task-label routing" as its Replacement and so pairs its removal with this slice's build. The
dispatch knobs in that row went with the WIP commit in preparation. The severity-routing case in the
scaffold test goes with the table it asserts.

**Unmapped citation.** The sequence previously retired the multi-provider chat abstraction beyond
Azure and the sampling-seed determinism machinery. The current register has no row for either: it
records the LLM client seam as reusable and lists no removal for the provider factory or the seed.
This slice therefore removes neither, and the two are reported as a gap between the plan and the
register rather than carried as silent work.

**Shape.** Heavy modification. The seam, its structured return, and the cassette and fake-model
machinery survive and are what `code-guidelines.md` §11 relies on for replaceability. The provider
branches, the tier tables, and the seed passing do not. Routing becomes the fixed task-to-deployment
table D-002 fixes, with no severity input, no confidence input, and no fallback chain.

**Tests.** The property worth asserting is that routing is by task label alone: no code path may
select a deployment from severity, model confidence, cost, or any runtime signal. The lower-cost
deployment is reachable by exactly one task.

**Evaluation.** The behaviour manifest that validates cassettes changes here, so every committed
cassette is re-recorded once against the configured deployments. This is the cheapest point in the
plan to pay that, because no prompt or role contract has changed yet.

**Observability.** Model access emits the task label, the selected deployment, latency, token usage,
and approximate cost, with the correlation context attached (`system-design.md` §10.1).

**Done when.** Both chat deployments are provisioned, every model call records its task label and
deployment, and no routing input other than the task label exists.

### 4.2 The Evidence Investigator

**Makes true.** One role selects the next evidence source from what has already been observed, holds
its working hypothesis as guidance that is never cited, and states its continuation proposal without
deciding it.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Evidence
Investigator: "Observation-driven capability selection," "Question/action/reason proposal contract,"
and "Optional informing-knowledge references."

**Unmapped citation.** The sequence previously closed a working-hypothesis contract. The current
register has no row for it, so it is carried here as part of the proposal contract rather than
dropped. That is a gap between the plan and the register.

**Retires.** Nothing on its own. The fused topology it is being split out of is retired in 4.4, when
the second half of the split lands and the module has no remaining role.

**Shape.** Heavy modification of the existing planner into a gathering-only role. The behavior the
same register records as "Partial and genuinely reusable in `LLMPlanner.plan`" survives: selection
from the full observation trail, no repeated call, and failing closed on a non-allowlisted
capability. What is added is the working hypothesis as a typed contract that cannot be represented
as an admitted observation or as a candidate (`code-guidelines.md` §4), and the proposal shape of
`workflow-design.md` §5: the unresolved material question, the permitted action, why the answer
could change the analysis, and the informing knowledge reference where retrieval genuinely
influenced it.

**Tests.** Two trajectory assertions belong here rather than in the evaluation layer, because they
are properties of this role. Different incidents must take demonstrably different evidence paths,
and the same capability must never be called twice for the same question within a turn. Both are
asserted over the operation history, not over prose.

**Evaluation.** Evidence-path behaviour becomes measurable from traces (`evaluation.md` §11), though
the paths are not yet driven by a turn controller.

**Observability.** The Evidence Investigator emits question selection, capability choice with its
reason, and the unresolved questions it carries forward (`system-design.md` §10.3).

**Done when.** The role produces proposals and requests and nothing else, a working hypothesis
cannot reach the engineer or the evidence set, and no synthesis path remains reachable from it.

### 4.3 The assessment contract

**Makes true.** The structured assessment can represent a candidate set with qualitative labels,
supporting and weakening references per candidate, established-or-possible markers, recommendations
by horizon with their provenance, and a further-evidence need.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", RCA Analyst and
assessment: "Candidate cause set," "Qualitative support labels," "Supporting and weakening evidence
per candidate," "Established and possible grounded elements," "Recommendation horizons and
provenance categories," "Recorded limitations and further-evidence need," and "Deterministic brief
projection."

**Retires.** `status.md` - "Deletion and Replacement Register", Replace: "Result/report contracts";
and "Misaligned implementations": "Numeric confidence."

**Shape.** Rewrite, not an adjustment. The current assessment object is one causal claim with report
claims and a 0-1 confidence float; the design's assessment is a different object
(`data-and-evidence.md` §12, §14). Describing this as widening the existing contract would
understate it. The deterministic rendering of statements from structured fields survives as the
mechanism by which the brief stays a projection.

**Tests.** Brief rendering fidelity is the assertion a reviewer would not predict is necessary: the
rendered brief must be derived from assessment fields by traversal alone, and must not drop,
reorder, re-rank, deduplicate, summarize, or truncate an analytical collection (`code-guidelines.md`
§3). A projection that quietly drops a weakening reference still renders a plausible brief.

**Evaluation.** Brief rendering fidelity becomes a deterministic conformance check the evaluation
layer aggregates (`evaluation.md` §7). Recommendation checks become expressible (`evaluation.md`
§12).

**Done when.** No numeric score, percentage, probability, or confidence value exists anywhere in the
assessment or the brief, every recommendation carries exactly one horizon and one provenance
category, and the brief is a traversal of the assessment.

### 4.4 The RCA Analyst as sole synthesis authority

**Makes true.** One role produces the assessment, reaches no source, and returns exactly one of a
supported assessment, an explicit insufficiency statement, or one further-evidence need.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", RCA Analyst and
assessment: "Distinct RCA Analyst as sole synthesis authority"; Evidence Investigator: "A distinct
investigator role."

**Retires.** `status.md` - "Deletion and Replacement Register", "Misaligned implementations": "One
planner gathers and concludes," together with the fallback pairing case in the composition test.

**Shape.** Rewrite of the synthesis path into a separate role. The model-proposes and code-admits
split survives, and so does template rendering; the fused module does not. After this slice no code
path lets one role both gather and conclude, and the implementation-selection fallback that paired a
planner with a triager has nothing left to select between.

**Tests.** The assertion that carries the design's weight is that the model proposes and code
authorizes: a synthesis result must be parsed and structurally admitted before anything reads it,
and a parse failure must be reported as a parse failure rather than as a grounding failure
(`code-guidelines.md` §5). Separately, the RCA Analyst must be structurally unable to reach a
capability or the structured-query path.

**Evaluation.** Scenario outcome evaluation becomes expressible against the golden records, though
it cannot run end to end until layer 6 closes.

**Observability.** The RCA Analyst emits synthesis start, assessment produced, insufficiency, and
the further-evidence need.

**Done when.** Exactly one authoritative assessment can exist per turn, no component other than the
RCA Analyst authors or supplements its analytical content, and the Evidence Investigator holds no
synthesis path.

### 4.5 Structured-query generation

**Makes true.** An investigative question becomes a bounded query structure drawn from the approved
schema context, which the deterministic validation of 2.4 then accepts or rejects.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Evidence Access
Layer and admission: "Governed structured-query capability."

**Retires.** Nothing.

**Shape.** New model task on the primary deployment, generating a structure rather than query text.
The model sees the approved surface and nothing wider.

**Tests.** The case worth asserting is the one that looks like a model failure and is not: a model
proposing grouping, ordering, or a non-count aggregate must fail structured decoding or validation
and be rejected before any source execution, producing a limitation. Only the Evidence Investigator
may originate the path, and the RCA Analyst must not be able to reach it.

**Evaluation.** The structured-query cases of `evaluation.md` §11 become runnable end to end: a
lookup or filter, one count aggregate, and one rejected query.

**Done when.** The path runs from question to admitted evidence without query text existing at any
point, and every rejection produces a limitation rather than fabricated content.

---

## Layer 5 - Protocol boundary and persistence

**What it makes safe.** The turn controller above this layer commits a completed turn and emits a
terminal outcome only after that commit succeeds. It cannot be built against a store that holds a
job-lifecycle record, and the protocol boundary must reach the capability surface layer 2 closed
rather than a second implementation added later beside it.

**Definition of done.** One approved capability is additionally reachable through a real MCP
boundary with identical semantics and permissions on both paths; the completed-turn artifact type
carries what `data-and-evidence.md` §17 fixes; the investigations container holds it; and no store,
endpoint, or queue that served the create-then-poll interaction remains.

### 5.1 The protocol boundary

**Makes true.** Deployment and change history is reachable through a real MCP boundary that shares
the capability implementation, the validation, the permission, the normalization, the provenance,
and the admission path with the direct call.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", MCP: "Only
deployment-and-change-history exposed" and "Transport visible in activity and telemetry."

**Retires.** `status.md` - "Deletion and Replacement Register", "Misaligned implementations": "MCP
exposes three wrong capabilities," together with the three-tool surface cases in the parity test.

**Shape.** Heavy modification. What survives is what the same register records against "One real MCP
boundary," partial and promising, and against "Same implementation and canonical result model as
direct access," implemented by delegation and tested: one `call` path, one validation, sanitized
errors, and a parity assertion. What changes is which capability is exposed and that only one is.

**Blocked detail.** `status.md` - "Detailed Missing and Partial Implementation Register", MCP:
"D-004 library questions resolved before implementation cutover" records the decision as still
pending, and "Implementation Clarifications Exposed by the Repository", "D-004 evidence" records
that the current SDK usage answers much of it while the explicit library inspection and final record
remain required. Moving D-004 to accepted is a `decisions.md` change and a precondition of this
slice; this plan does not decide it.

**Tests.** Parity is asserted on normalized result, evidence type, provenance, outcome and
completeness, read-only permission, and admitted evidence semantics, with only the recorded
transport differing. The failure this catches appears only in the case the direct path was never
exercised, so both paths are driven from the same case list.

**Evaluation.** Protocol parity becomes a deterministic result the evaluation layer aggregates
(`evaluation.md` §11).

**Observability.** The protocol boundary is one of the four instrumented boundaries: it emits the
operation with its transport recorded, carrying the same correlation context as the direct path.

**Done when.** Exactly one capability is exposed, it is the one D-004 settles, and no capability is
reachable through the boundary that is not reachable directly with the same permission.

### 5.2 The Investigation Record and the completed-turn artifact

**Makes true.** The only durable artifact is a completed turn, written once, by one writer, at turn
completion.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Investigation
Record and persistence: "Completed-turn artifact," "One `investigations` container for that
artifact," "Restart-safe citation resolution," and "No active-turn checkpoints, replay, index
container, or worker state," of which this slice removes the index container and the worker state
while 6.1 removes the checkpoints and replay machinery.

**Retires.** `status.md` - "Deletion and Replacement Register", Delete: "Async job status vocabulary
(`queued`/`running`/`awaiting_approval`/`degraded`/`escalated`...) and 202+poll transport," which
carries "Streaming turn endpoint + live statuses" as its Replacement; "`investigation-index`
container + versioned idempotency key machinery"; and the endpoint and record members of "HITL
surface: `hitl_gate`, `apply_edit` nodes, `POST /investigations/{id}/decision`, `CommittedDecision`,
decision idempotency, console approval UI, `Approver` role usage," whose node members go in 6.1, its
console member in 7.4, and its `Approver` member with the auth machinery in 7.4. Replace: "`api.py`
transport + console," of which this slice performs the removal half. "Out-of-scope wrappers around
otherwise valid concepts": "Job-idempotency index and workflow-version salt," "Multi-replica
transition machinery," "Publication identity and approval-bound report hash," and the repository
side of "Lease and fencing protocol for multi-replica workers." The tests that die with these
subjects are the HITL and decision suite, `test_report_binding.py`, and the investigations and
investigations-API modules `status.md` - "Test and Evaluation Gap Status" lists.

**Already discharged.** The queue seam, the worker, and the outbox were dropped with the unpushed
WIP commit in preparation, so this slice deletes no dispatch module. What remains of that machinery
here is only what the repository modules themselves carry.

**Shape.** Rewrite, and the largest slice in the plan. The persistence modules are replaced rather
than adapted: what persists is one logical artifact carrying identity, objective, terminal outcome,
stop reason, admitted evidence, retrieved-knowledge references used, assessment and brief where
produced, limitations, follow-up context, and the trace reference with its version stamp and usage
totals. The job record, its status machine, its leases, and its idempotency index have no
counterpart in that artifact and go with it. The ETag and publish-idempotency techniques `status.md`
- "Component Reconciliation Matrix" records as reusable carry into the completed-turn commit.

**Consequence stated plainly.** The endpoints those stores served are removed here, and their
replacement arrives in layer 7. From this slice until 7.1 the deployed application serves health and
no turn surface. The tree stays green, the tests and the evaluation harness drive turns in process,
and the deployment smoke is reduced to the checks that still have a subject until 8.2 replaces the
suite. Two pairings split across that gap: Replace: "`api.py` transport + console" is removed here
and replaced in 7.1 and 7.4, and Replace: "Hosted smoke" loses its async and decision legs here and
is replaced in 8.2, because neither can survive the removal of the endpoints it calls.

**Superseded risk note.** `status.md` - "Deletion and Replacement Register", Delete: "Async job
status vocabulary (`queued`/`running`/`awaiting_approval`/`degraded`/`escalated`...) and 202+poll
transport" carries the note that it be removed only after the streaming slice is demonstrable. The
layering decision supersedes that note, and the divergence is deliberate. The job record is the
persistence shape, so building the completed-turn artifact and retiring the job record are one piece
of work rather than two; holding the old surface until 7.1 would mean carrying two persistence
models through six slices, with every slice between them written against both. The window this opens
is the one stated directly above, and it is bounded by the tree staying green and turns staying
drivable in process.

**Tests.** Three properties that a green suite would otherwise hide. A turn that never completes
must leave nothing persisted, so a failed first execution leaves no investigation shell. A terminal
success must be impossible to emit before the commit succeeds. And completed records must remain
readable after the code that wrote them changes, which is what makes the persisted type carry
version information (`code-guidelines.md` §4).

**Evaluation.** The completed turn becomes the unit evaluation reads (`evaluation.md` §2). Until
layer 6 commits one, the artifact is exercised from fixtures.

**Observability.** The Investigation Record emits its read and write operations; the write carries
the turn identity and the outcome.

**Deployment verification.** Two checks change subject: the end-to-end streamed turn check has no
surface to run against until 7.1, and citation resolution after restart becomes checkable against
the new artifact (`runtime-and-deployment.md` §16, checks 5 and 6).

**Done when.** One container holds completed turns only, the Supervisor is structurally the only
writer, nothing is written mid-turn, and no queue, outbox, lease, or job record remains in the tree.

---

## Layer 6 - Reasoning integrity

**What it makes safe.** This layer is where the pieces below become a turn, and where the properties
that make the result trustworthy live: budgets code owns, continuation the Supervisor authorizes, a
gate of exactly four checks, one correction allowance, an outcome the turn state chooses, and a
commit that precedes delivery. Transport above it streams whatever this layer produces, so nothing
here may be left to the layer above.

**Definition of done.** A turn runs end to end in process: five stages with one bounded back-edge,
every assignment and result through the Supervisor, gathering that continues only on an authorized
proposal, a gate that refuses rather than repairs, one of three outcomes with a stop reason recorded
by the stage that detected it, and a completed-turn commit that precedes any successful terminal
outcome.

An end-to-end turn is first runnable at the end of this layer, driven by tests and the evaluation
harness rather than by an engineer.

### 6.1 The turn controller

**Makes true.** A turn executes as an explicit in-process state machine: intake and objective,
bounded investigation, synthesis, grounding and outcome validation, delivery and persistence, with
the one authorized further-evidence edge.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Supervisor: "Own
the turn objective," "Separate deterministic control from model judgments," "Authorize continuation
against computable conditions," and "Enforce the six bound mechanisms"; Evidence Investigator:
"Supervisor authorization before continuation" and "Parallel independent evidence actions inside one
authorized cycle"; Turn lifecycle, cancellation, follow-up, and handoff: "Explicit in-process state
machine" and "One possible further-evidence cycle."

**Unmapped citation.** The sequence previously closed an entry for the investigation, turn, and
live-session model itself. The current register names the state machine and the streaming request
but has no row for the model, so this slice carries it inside "Explicit in-process state machine."
That is a gap between the plan and the register.

**Retires.** `status.md` - "Deletion and Replacement Register", Replace: "LangGraph orchestration
(`graph.py` + nodes + routers)"; Delete: "Checkpointer stack: `checkpoint.py`,
`langgraph-checkpoint-sqlite` dep, `checkpoints` Cosmos container (Bicep + live), msgpack
allowlist," "`postmortem` node output path," and the `hitl_gate` and `apply_edit` node members of
"HITL surface: ..."; "Misaligned implementations": "Severity-scaled sufficiency stop rule" and "Old
intent taxonomy and known-issue fast path." The tests that die with these subjects are
`test_checkpointer.py`, the sufficiency test, the triage and triager tests, and the escalate and
sufficiency routing cases of the diagnose test.

**Shape.** Rewrite. D-001 settles that the turn is an explicit state machine in ordinary application
code with no orchestration framework, graph runtime, or checkpointing feature, so the graph build,
its conditional edges, its node bodies, and the checkpointer they were wired to are replaced rather
than migrated. Stage transitions, continuation conditions, and bound enforcement become hand-written
code covered directly by tests, which is the trade-off D-001 accepts.

**Pairing note.** The intent taxonomy is retired here because the routing stage it lived in
disappears with the stage sequence. The required behavior it is measured against, "Request-shape
classification of follow-up, redirect, supplied context, handoff, and read," is a transport behavior
and lands in 7.2, so that pairing spans two slices.

**Tests.** The bound properties are the ones a passing happy path hides. Every loop must be bounded
by two independent conditions, so a construct whose continuation depends only on model output must
be impossible to write; the Supervisor must authorize against computable conditions alone, without
re-deriving the judgment behind a proposal; and a second further-evidence cycle must be structurally
impossible within a turn rather than prevented by a counter. Deadline propagation is asserted into
every model and capability operation, not only between stages.

**Evaluation.** Bounded termination becomes a deterministic conformance check, and the
further-evidence demonstration the coverage audit selected becomes runnable (`evaluation.md` §7,
§4).

**Observability.** The Supervisor emits turn start and objective, each assignment, every
continuation decision with its reason, budget consumption, and the stop reason. Component dispatch
is one of the four instrumented boundaries and carries the investigation and turn identity into
everything below it.

**Done when.** A turn runs its five stages in process against an authored incident, no agent can
widen its own budget, at most one further-evidence cycle can occur, and no checkpoint, resume, or
approval path exists anywhere.

### 6.2 The grounding gate and the correction allowance

**Makes true.** Before delivery, exactly four deterministic checks run over the assessment, and a
failure spends the turn's one shared correction allowance or ends the attempt.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Grounding and
outcomes: "Citation resolution and role/type pairing," "Operational support for established grounded
elements," "Recommendation-provenance presence," "Limitation disclosure," "One shared correction
allowance," and "No artifact after persistent grounding failure"; Supervisor: the correction-
allowance half of "Own the shared correction allowance and terminal shape," whose terminal-shape
half closes in 6.3.

**Retires.** `status.md` - "Deletion and Replacement Register", "Misaligned implementations":
"One-check safety gate routing to escalation"; and "Duplicated logic to collapse": "Citation
grounding," whose two occurrences become one gate at one stage over one object. The approval-routing
cases in the guardrails test go with them.

**Shape.** Rewrite. The single check that exists is a real ancestor of reference resolution, and it
survives as that check's substance; the gate around it is new, and its routing to a terminal status
the design does not have is removed. The allowance is held as one piece of turn state that both the
model-output correction path and the gate read and spend (`code-guidelines.md` §7).

**Tests.** Four assertions a green gate cannot be distinguished without. Which check failed must be
observable, because a gate that silently passes everything looks identical to a strict one on good
input. A knowledge reference in a current-operational-support role must fail reference resolution on
its type alone. A parse or contract failure must never be reported as a grounding-check failure. And
a brief that still fails after its one correction, or that fails with the allowance already spent,
must not be delivered, downgraded, repaired, or persisted.

**Evaluation.** Grounding-gate conformance and the correction allowance become deterministic
conformance checks, the second countable from the trace as arithmetic over recorded model calls
(`evaluation.md` §7).

**Observability.** The gate result is emitted with the failed check named where it failed, and a
corrective model call is emitted like any other model call so that counting it is possible.

**Done when.** The gate holds exactly four checks with no configuration surface, no model call runs
inside it, a turn can spend at most one corrective call whichever failure reaches it first, and a
persistent failure produces a failed execution rather than a delivered brief.

### 6.3 Outcomes, stop reasons, and degradation

**Makes true.** The turn state chooses one of three outcomes, records why gathering stopped and why
it was inconclusive, and handles cancellation on both of its paths.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Grounding and
outcomes: "Exactly complete, partial, inconclusive completed outcomes" and "Failed execution outside
completed outcomes"; Turn lifecycle, cancellation, follow-up, and handoff: "Safe-boundary
cancellation," "Early no-evidence cancellation: inconclusive, no assessment, no brief," and "Later
cancellation with admitted evidence: honest partial or inconclusive result"; Supervisor: the
terminal-shape half of "Own the shared correction allowance and terminal shape."

**Retires.** The escalate cases in the diagnose test. The vocabulary that carried escalation as a
terminal status is retired by rows other slices own: `status.md` - "Deletion and Replacement
Register", Delete: "Async job status vocabulary
(`queued`/`running`/`awaiting_approval`/`degraded`/`escalated`...) and 202+poll transport" in 5.2,
and Replace: "Result/report contracts" in 4.3, which drops the escalation variant of the result
union. The `escalate` node itself goes with Replace: "LangGraph orchestration" in 6.1.

**Shape.** Rewrite of the status and outcome vocabulary. The live statuses, the three completed-turn
outcomes, the stop reasons, and the inconclusive reasons are the tables `workflow-design.md` §9
fixes; the current completed, degraded, and escalated set is replaced, and a failed execution is not
a fourth outcome.

**Tests.** Cancellation is the pair that ends in a tidy-looking outcome either way. With evidence
admitted, synthesis, the gate, delivery, and persistence must all still run and the brief is marked
partial. With no evidence admitted, synthesis must not run at all, no brief is produced, no
candidate cause or recommendation is asserted, and the turn still completes and still persists.
Separately, a reason must be recorded by the stage that detected it, never inferred later by another
stage.

**Evaluation.** Three of the four controlled degradation cases become runnable: source failure
against a material and a nonmaterial source, cancellation after evidence, and cancellation before
evidence (`evaluation.md` §13).

**Observability.** The terminal outcome or execution failure is emitted with its reason, and
degradation stays visible rather than absorbed.

**Done when.** No terminal status exists outside the design's set, a nonmaterial source failure can
leave a turn complete with its limitation disclosed, and both cancellation paths produce a completed
turn.

### 6.4 Commit before delivery

**Makes true.** The Supervisor commits the completed turn, and only then is a successful terminal
outcome emitted.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Supervisor:
"Commit completed turns before successful terminal delivery"; Investigation Record and persistence:
"Commit before successful terminal delivery."

**Retires.** Nothing; the store it writes to was replaced in 5.2.

**Shape.** New ordering code inside the Supervisor boundary, plus the write path from the turn state
assembled by 6.3 into the artifact type from 5.2.

**Tests.** The persistence-failure branch is the one that looks identical to success from outside: a
failed commit must emit a failed execution, leave no completed turn, and never report the turn as
completed. The no-evidence cancellation path commits an artifact carrying neither assessment nor
brief, and that omission must be representable rather than a validation error.

**Evaluation.** Commit-before-terminal ordering and its persistence-failure branches become
deterministic results the evaluation layer aggregates (`evaluation.md` §13).

**Observability.** The completed-turn write is emitted before the terminal outcome, and the artifact
carries the correlated trace reference.

**Done when.** No successful outcome can be emitted before a successful commit, a failed commit is a
failed execution, and the first successful commit is what creates the investigation record.

---

## Layer 7 - Transport

**What it makes safe.** The turn exists; this layer is how an engineer reaches it. It makes the
deployed application demonstrable, which is what the infrastructure and evaluation layers above it
verify and measure. Nothing here adds investigative behavior, and no decision belonging to layer 6
may be taken in it.

**Definition of done.** Two request shapes exist and no others: a streaming request that owns a
turn, and ordinary requests that do not. Activity is visible while a turn runs, cancellation reaches
the active request, follow-ups and handoff summaries are answered from retained state, and one
screen presents intake, activity, the brief, and one expandable details area.

### 7.1 The streaming turn request and activity projection

**Makes true.** One live streaming request creates a turn, emits the identities first, streams
activity as it happens, executes the turn, and ends by delivering a terminal outcome once the commit
has succeeded.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Turn lifecycle,
cancellation, follow-up, and handoff: "One live streaming request owns a turn"; Engineer Interaction
Interface: "Compact safe activity projection"; Telemetry and activity: "Activity projection emitted
from the same facts."

**Retires.** `status.md` - "Deletion and Replacement Register", "Out-of-scope wrappers around
otherwise valid concepts": "Per-user and role-based concurrency admission," of which the design
keeps only the one small configured concurrency limit that row names; and "No accepted slot or
explicitly deferred": "Deprecated `/health` alias." This slice also performs the streaming half of
Replace: "`api.py` transport + console," whose removal half landed in 5.2.

**Shape.** New surface replacing the removed job API. The response is an ordinary streaming HTTP
body that does not require the browser `EventSource` API, served by the same Container App as the
static client. There is no create-then-attach pair, no reconnection, no event buffering, and no
sequence cursor.

**Tests.** Activity projection fidelity is the assertion a reviewer would not predict: an activity
event must be produced at the same instrumentation point as the telemetry it mirrors, from the same
recorded facts, and must carry no prompt, hidden reasoning, provider-shaped content, or secret. A
stream-only fact that telemetry does not record is a defect even when the event looks ordinary.
Separately, turn isolation across concurrent investigations is asserted structurally rather than as
a convention about keys, because cross-contamination surfaces as a plausible but wrong brief.

**Observability.** The stream is a projection of the telemetry seam, not a second emitter.

**Deployment verification.** The end-to-end streamed turn check regains its subject: identities
arrive first, activity streams, a brief and an outcome arrive, and the persisted artifact for that
turn exists (`runtime-and-deployment.md` §16, check 5).

**Done when.** One request owns one turn from creation to terminal outcome, no work continues after
it returns, and no path can reattach to a running turn.

### 7.2 Ordinary requests: normalization, follow-up, handoff, and read

**Makes true.** Free text is normalized into the same structured form selection produces, with at
most one clarification, before any turn exists; and a later engineer message is classified into one
of five kinds and handled from retained state.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Engineer
Interaction Interface: "Predefined and free-text intake normalization," "At most one clarification,"
"Request-shape classification of follow-up, redirect, supplied context, handoff, and read," and
"Deterministic handoff rendering"; Supervisor: "Answer follow-ups from retained state with
deterministic validation"; Turn lifecycle, cancellation, follow-up, and handoff: "Retained-state
follow-up validation" and "Deterministic handoff with no model call."

**Retires.** Nothing here. "Old intent taxonomy and known-issue fast path," which this
classification replaces, was retired in 6.1 with the routing stage it lived in.

**Shape.** New. Normalization is the one model task the interaction interface holds, on the
lower-cost deployment (D-002), and its proposal is admitted by deterministic code against the
normalized incident context contract. Classification is established from the request shape or the
explicit interface action, never by analyzing prose and never by a model call, and an ambiguous
ordinary follow-up defaults to a question. The handoff summary is a deterministic projection of
retained state that calls no model.

**Blocked detail.** Two items in `status.md` - "Implementation Clarifications Exposed by the
Repository" bear directly on this slice. "Normalized incident context fields" records that the
implementation needs one typed contract for normalized input and that the current `Alert` shape is
evidence rather than automatic authority. "Stateless clarification token" records that a short-lived
normalization token needs an explicit signing, expiry, and payload contract, and that a simpler
resubmission path is preferred where it meets the requirement. Both are decisions for the design
set, not for this plan.

**Tests.** Follow-up answer validation is the check that reads exactly like a valid restatement when
it fails: every cited reference must resolve within retained investigation state, and the answer
must introduce no new evidence, no new candidate cause, no new conclusion, and no recommendation
presented as coming from retrieved guidance. It is not a grounding check, and the four-check gate
must stay exclusive to completed-turn delivery. The at-most-one-clarification limit must be enforced
in code the model cannot reach.

**Evaluation.** The change-time cadence becomes runnable from the engineer-facing entry point rather
than from a harness.

**Observability.** The interaction interface emits intake and the classification outcome.

**Done when.** No turn identity or durable state exists during clarification, a second clarification
is impossible, and a follow-up question, a handoff summary, and an investigation read all answer
from retained state without opening a turn.

### 7.3 Cancellation

**Makes true.** A small ordinary request signals the active turn, which stops at its next safe
boundary.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Turn lifecycle,
cancellation, follow-up, and handoff: "Disconnect discards active state," and the signalling half of
"Safe-boundary cancellation," whose floor closed in 6.3.

**Retires.** Nothing; the cancellation floor it signals was built in 6.3.

**Shape.** New, and deliberately minimal: one in-memory map from active turn identity to a
cancellation signal, alive only while the streaming request is, not durable, not a job registry, and
not used for recovery or reattachment.

**Tests.** The property worth asserting is that cancellation reaches the operation, not only the
stage boundary, and that a lost connection with the execution abandoned persists nothing.

**Deployment verification.** Both cancellation paths are environment-independent and stay owned by
deterministic tests rather than by the deployed suite (`runtime-and-deployment.md` §16).

**Done when.** Cancelling produces a completed turn on both paths, and the signal map disappears on
restart without leaving anything behind.

### 7.4 The engineer-facing surface

**Makes true.** One screen carries intake and follow-up control, a compact live activity feed, the
delivered brief as the dominant element, and one expandable details area.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Engineer
Interaction Interface: "One same-origin screen for intake, follow-up, activity, brief, and details";
Azure and deployment: "Container Apps built-in authentication" and "Static client served by same
app."

**Retires.** `status.md` - "Deletion and Replacement Register", Replace: "Auth machinery," and the
console half of Replace: "`api.py` transport + console"; "Misaligned implementations": "Hand-rolled
three-role authorization"; and the console approval UI and `Approver` role members of Delete: "HITL
surface: ...," whose other members went in 5.2 and 6.1. The auth-role suites `status.md` - "Test and
Evaluation Gap Status" lists as dying with their subjects go here.

**Shape.** Rewrite. `status.md` - "Detailed State by Design Area", "The six components" finds
nothing in the current console survives as the designed interface: its approval controls have no
counterpart and its poll-a-job transport is replaced by the stream. Caller authentication becomes
Container Apps built-in authentication with one application registration, which is the whole of the
posture `runtime-and-deployment.md` §12 keeps; no roles, groups, or authorization policy machinery
replaces what is removed.

**Tests.** Progressive disclosure is presentation and may vary; what may not is the brief's content.
Holding a section behind disclosure is permitted, and removing, reordering, or rewriting what the
assessment holds is not, so the presentation path is asserted against the same projection rule as
the rendering path.

**Deployment verification.** Caller authentication becomes checkable as the design states it: an
unauthenticated caller is refused and an authenticated one admitted, with no role in the check
(`runtime-and-deployment.md` §16, check 2).

**Done when.** One screen serves the whole interaction, no approval or decision control exists in
it, and no role or group governs access.

---

## Layer 8 - Infrastructure

**What it makes safe.** Everything below runs somewhere. This layer makes the declared environment
match the design and proves a deployment works, which is what the evaluation layer above needs
before a recorded result means anything about the deployed system.

**Definition of done.** The template declares exactly the six services and the containers and
deployments the design names and nothing else; the application refuses to start with an undefined
authorization posture or an unapproved capability enabled; and the eight verification checks run
against a deployed revision.

### 8.1 The declared environment

**Makes true.** The infrastructure template and the startup configuration describe the system the
design describes, with nothing left from what the earlier layers removed.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Azure and
deployment: "Target three Cosmos containers," "One Container App, one image, zero-to-one replicas,"
and "Application Insights," whose exporter wiring follows in 9.1.

**Retires.** Nothing on its own. Each earlier slice removed the resources its own behavior owned;
this slice is where what remains is reconciled to the declared set. The live containers a template
change cannot remove are deleted by CLI under the preparation section rather than here.

**Shape.** Heavy modification of the template. What survives is what the same register records as
implemented and reusable, "One OIDC workflow and Bicep," together with the one image, one Container
App, one Dockerfile, keyless managed identity, and scale to zero that `status.md` - "Azure and
Deployment Status" confirms live. What changes is the container set, the model deployment set, the
addition of Application Insights, the replica maximum, which that section records as 3 in both the
template and the live app against the accepted 0-1, and the removal of parameters that provisioned
machinery no longer present.

**Tests.** Configuration validation at startup is the behavior worth asserting rather than assuming:
the application must refuse to start with an undefined authorization posture or an unapproved
capability enabled, and secret values must appear in no configuration dump or health output.

**Deployment verification.** Repeatable deployment from declared infrastructure becomes provable
(`runtime-and-deployment.md` §16, check 8).

**Done when.** The declared containers are the investigations container plus the two RetailEase
containers, the declared model deployments are the primary chat, the lower-cost chat, and the
embedding deployment, the replica range is zero to one, Application Insights is declared, and no
other resource is declared.

### 8.2 The verification suite

**Makes true.** Eight environment-dependent checks prove a deployed revision, and the behavior the
environment does not change stays owned by deterministic tests.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Azure and
deployment: "Eight hosted smoke checks."

**Retires.** This slice performs the replacement half of `status.md` - "Deletion and Replacement
Register", Replace: "Hosted smoke," whose removal half landed in 5.2 with the endpoints its async
and decision legs called. That row's own migration note records that the new script runs only after
the streaming and persistence slices, which is where this slice sits.

**Shape.** Rewrite of the smoke script into the eight checks `runtime-and-deployment.md` §16 names.
Cancellation on both paths, a lost request leaving nothing persisted, structured-query rejection,
and protocol parity stay with the deterministic tests and are deliberately not repeated here.

**Evaluation.** The deployed verification results become one of the three sources an evaluation run
aggregates (`evaluation.md` §3).

**Done when.** All eight checks run against a deployed revision, each reports pass or fail by name,
and no check duplicates a deterministic test.

---

## Layer 9 - Remaining features

**What it makes safe.** Nothing above depends on this layer; it is what makes the system explicable
and its results reportable. It comes last because every property it observes or scores must already
exist to be observed or scored.

**Definition of done.** A turn can be reconstructed end to end from telemetry with its usage and
cost attributed; an evaluation run reads completed turns and traces, reports by scenario class with
every failure named, and gates nothing; and the fixed-script comparison is runnable on its subset.

### 9.1 Telemetry completion

**Makes true.** Every emission carries the turn it belongs to, the boundaries that were silent emit,
and traces reach a real sink.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Telemetry and
activity: "Turn and agent identity," "MCP, evidence-admission, grounding, and persistence spans,"
"Application Insights sink," and the usage-totals half of "Model task labels and usage totals,"
whose task labels closed in 4.1.

**Retires.** Nothing.

**Shape.** Extension, not a rewrite. The same register records "Shared span seam" as implemented and
reusable, and `status.md` - "Detailed State by Design Area", "Telemetry" records it as the most
reusable subsystem in the repository: one seam emitting once at shared primitives, contextvar-nested
parents, correlation identifiers, error status reflection, a swappable exporter, and an in-memory
test fixture. What is added is the turn identity that had no model to carry, the boundaries that had
no instrumentation, the events for admission and grounding, cost attribution, and the Application
Insights exporter beside the existing set.

**Tests.** The in-memory exporter fixture is what keeps these assertions deterministic. The property
worth asserting is attribution: an operation that cannot be attributed to an investigation and a
turn is not adequately instrumented, and context must be attached where work enters a boundary
rather than reassembled by inference at read time.

**Evaluation.** Latency, model and capability call counts, token use, and approximate cost become
recordable per completed turn (`evaluation.md` §16).

**Observability.** This slice is the observability obligation for all four instrumented boundaries:
component dispatch, capability execution, model access, and the protocol boundary.

**Deployment verification.** One investigation and turn can be followed end to end with its usage
reported (`runtime-and-deployment.md` §16, check 7).

**Done when.** No emission lacks its investigation and turn identity, secret and raw source content
are filtered before anything is emitted, and telemetry is unreachable as evidence about the
incident.

### 9.2 The evaluation suite

**Makes true.** One run aggregates deterministic results, scores scenario outcomes categorically
against the golden records, runs the offline judge, and produces one report.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Evaluation:
"Categorical scenario scoring," "One judge with versioned rubric," "Deterministic conformance
aggregation," "Advisory report rather than merge-gating numeric ratchet," and "Retrieval-influence
and further-evidence demonstrations," which that register holds until the corpus repairs 1.1 closes
and the D-006 selection 1.2 records.

**Retires.** `status.md` - "Deletion and Replacement Register", Replace: "Evaluation suite";
"Misaligned implementations": "Numeric evaluation ratchets gate CI"; "No accepted slot or explicitly
deferred": "Generic evaluator registry scaffold" and "Empty package placeholders"; and "Duplicated
logic to collapse": "Runtime implementation selection," whose second occurrence goes when the
evaluation scripts stop re-selecting a planner and triager.

**Shape.** Rewrite. The scoring model changes from numeric scorecards against committed baselines to
one category per dimension drawn from Meets, Partially meets, Misses, and Not applicable, with a
short named reason for anything below Meets. The ratchet baselines and the up-front numeric targets
go with it, and the change-time signal informs a change without gating the merge.

**Blocked detail.** `status.md` - "Implementation Clarifications Exposed by the Repository",
"Evaluation artifact storage" records that the report, fixtures, and historical runs need a physical
repository location before this slice, and that it must stay simple rather than becoming another
telemetry platform. Where a run retains them is a decision for the design set, not for this plan.

**Tests.** The judge is the part that must be structurally unable to matter at runtime: it runs
after deterministic checks, never participates in a live turn, never influences an outcome shape,
and a deterministic result overrides it wherever both bear on the same property. Its dimensions are
semantic support, causal-order coherence, usefulness, completeness, and relevance, and it never
gates delivery.

**Evaluation.** This slice produces the first result worth recording as a baseline: one milestone
run over the seven authored incidents, reported by scenario class with every failure named, with no
threshold set from it. Layer 1's scenario selections decide which subset the change-time cadence
runs.

**Done when.** A run reads completed turns and traces and writes one report, no aggregate figure
stands in for a named scenario failure, and no evaluation result blocks a merge.

### 9.3 The fixed-script baseline and repeatability

**Makes true.** The comparison that tests whether adaptive routing earns its place is runnable on
its subset, and the repeatability subset has been run a second time.

**Closes.** `status.md` - "Detailed Missing and Partial Implementation Register", Evaluation:
"Fixed-script evidence-plan baseline" and "Repeatability subset."

**Retires.** Nothing.

**Shape.** Heavy modification of what already exists behaviorally. The same register records the
fixed-script baseline as partial deterministic behavior that is wrongly a runtime fallback; what
changes is that it stops being a runtime fallback tier and becomes an evaluation baseline, using the
same capabilities, permissions, bounds, corpus, and assessment and brief contract as OpsPilot, with
a versioned predetermined evidence plan stored beside its fixture.

**Tests.** The baseline must not become a second application. It reuses the same evidence and
synthesis path, and a divergence in bounds, permissions, or contract makes the comparison
meaningless rather than merely inaccurate.

**Evaluation.** The comparison runs on the smallest subset that can carry the claim, and reports the
result it gets, including where the fixed script matches or beats the adaptive path. The
repeatability subset records whether the leading candidate, the outcome shape, the material evidence
references, the recommendation direction, and the usage figures held across one repeat. No uplift
percentage and no stability score is computed.

**Done when.** The fixed-script comparison and the repeatability observations both appear in the
report, and no runtime path selects the fixed script.

---

## Retired tests

`status.md` - "Test and Evaluation Gap Status" lists the tests that die with their subjects as one
group: the HITL and decision suite, `test_report_binding.py`, `test_checkpointer.py`, the auth-role
suites, the wild-probe tests, and the reranker-marked tests. That grouping is a fan-out by
construction, because the subjects are superseded in different slices and `code-guidelines.md` §11
requires a superseded assertion to be retired by the slice that supersedes it. Each named module
retires in exactly one slice.

| Test module | Retired in |
| --- | --- |
| Status-envelope assertions in the tool tests | 2.1 |
| Rerank cases in the retrieval test | 3.2 |
| Severity-routing case in the scaffold test | 4.1 |
| Composition fallback-pair test | 4.4 |
| Three-tool surface cases in the parity test | 5.1 |
| Report-binding test | 5.2 |
| Investigations test | 5.2 |
| Investigations-API test | 5.2 |
| Async, decision, and approval paths of the API test | 5.2 |
| Checkpointer test | 6.1 |
| Sufficiency test | 6.1 |
| Triage and triager tests | 6.1 |
| Escalate and sufficiency routing cases of the diagnose test | 6.1, 6.3 |
| Approval-routing cases in the guardrails test | 6.2 |
| Authorization test | 7.4 |
| Scenario-gate and single-agent-gate tests | 9.2 |
| Wild-slice test | 1.2 |

## What blocks a slice

Seven items block a slice from being fully specified. All seven are recorded in `status.md` -
"Implementation Clarifications Exposed by the Repository", and each is cited below by its item name.
None is decided here: each is settled in its owning slice or by a small decision update before code
invents an incompatible answer.

| Blocks | What is unsettled | Item |
| --- | --- | --- |
| 2.3 | One owner for reference prefixes, keys, and parsing; the existing frozen grammar is a candidate to evaluate rather than copy | "Evidence and knowledge reference encoding" |
| 3.1 | No Cosmos vector-index configuration exists anywhere; viability is verified before the implementation is chosen, and an in-process cosine scan requires the recorded explicit revision | "D-003 vector viability" |
| 5.1 | The explicit library inspection and the final decision record, which repository evidence answers much of but does not close | "D-004 evidence" |
| 7.2 | One typed contract for normalized input; the current `Alert` shape is evidence, not automatic authority | "Normalized incident context fields" |
| 7.2 | The signing, expiry, and payload rules for a short-lived normalization token, where a simpler resubmission path does not meet the requirement | "Stateless clarification token" |
| 9.2 | A physical repository location for the report, fixtures, and historical runs, which must stay simple | "Evaluation artifact storage" |
| 1.2 | The scenario selections, which wait on the required corpus repairs and the coverage audit | "D-006 evidence" |

The last two are settled inside the slices that carry them rather than by a separate decision. The
D-006 selections are not a corpus read alone: 1.1 repairs the corpus first, and 1.2 then runs the
audit and records the selections against the candidate mapping `status.md` - "Data and Corpus
Status" already supplies. That dependency is why the repairs are a slice of their own and why the
selections follow them.

