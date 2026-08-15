# OpsPilot - Horizontal Execution Plan

**In what sequence is the gap between the design and the repository closed?**

This document sequences the work. It converts `status.md` - "Partially implemented and
missing capabilities" and `status.md` - "Temporary legacy and coexisting implementation" into
vertical slices, ordered
so that each horizontal layer is complete before the next begins, and it states what must be true at
the end of each slice and each layer.

It does not restate what is missing. `status.md` - "Partially implemented and missing
capabilities" is the canonical inventory of absence, and every slice below cites its rows by their
own wording. It does not restate why a choice was made; `decisions.md` owns that. It carries no
dates, no estimates, and no ordering beyond dependency.

References into `status.md` name headings rather than section numbers, so a citation survives
renumbering and stays greppable. A row is cited by its own wording for the same reason.

The gap it closes was measured at a commit an earlier revision of `status.md` named. The current
document no longer carries that measurement, so the citation this paragraph held stands as a
divergence: a stated citation without a counterpart. No verdict is re-derived here.

## How to read a slice

Each slice is one coherent behavior, reviewable in one sitting, and leaves the repository working. A
slice that cannot leave the tree green is too big. Nothing is committed until the local pass for
that slice is reviewed.

Each slice states what it makes true, what must already hold for the slice to begin, the required
behavior it closes and the Delete or Replace rows it retires, both cited by their own wording,
whether the change is new code or a rewrite, the tests whose necessity a reviewer would not predict,
its evaluation and observability obligations where it has them, what a deployed check proves
differently afterwards, and what must hold for the next slice to rely on it.

A slice states what it does, never whether it has been done: this document carries no completion
status, verification detail, dates, or change-request references, and what has been built is
recorded in `status.md`.

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
branch actually contains, and delete the rest. An earlier revision of `status.md` named the debris
(`out.txt`, `raw.txt`, two `.gitkeep` placeholders, a stray compiled test artifact) and the six
stale branches, together with the stale `README.md` and `.env.example` and the untracked `docs/`
and `.githooks/` that are committed here.

The unpushed WIP commit an earlier revision of `status.md` recorded on
`stage-5f-durable-dispatch` is confirmed as abandoned or cherry-picked, and then dropped. That
discharges the WIP-commit deletion (`dispatch.py`, `worker.py`, lease and epoch machinery, Service
Bus configuration) here rather than in any slice, so no slice below deletes the dispatch or worker
modules. It also clears the 31 failing tests and the two `mypy` errors that revision attributed to
the commit, so every slice starts from a green tree.

**Azure orphans.** Resources that no template declares and that are not part of OpsPilot are deleted
directly with the CLI. Bicep declares desired state; it does not remove what it never owned, so an undeclared resource is not removed by any template change in layer 8. The one such resource was
the live orphan `rytesting` (Microsoft.CognitiveServices/accounts, kind AIServices) with its
`rytesting/proj-default` project in `rg-opspilot`, which an earlier revision of `status.md`
recorded as the only live resource there outside the template. These deletions belong to no slice
and are not added to the template.

**Divergence.** The five citations this section carried named headings of an earlier `status.md`:
the stray-file and stale-branch debris, the repository-hygiene list, the unpushed WIP commit, the
failing tests and type errors attributed to it, and the live orphan resource. The current
`status.md` records none of these, because the preparation they describe is done and the document
carries no history. Each stated citation has no counterpart.

**Live containers the template will stop declaring.** A template that no longer mentions a container
does not delete it from the account either. The `checkpoints` and `investigation-index` containers
are therefore deleted with the CLI, not by Bicep, and they are deleted when the persistence slice
lands, which is 5.2. This is the one preparation item that is sequenced rather than done up front,
because the live containers cannot go before the code that reads them does. The checkpointer stack
itself is retired in 6.1, so `checkpoints` has no writer left after that slice either.

**Superseded (2026-08-09): both containers are already gone, by a different route.** Cosmos NoSQL
vector search requires an account capability that cannot be added to an existing account, verified
against the original account, which rejected every container vector policy and could not be updated
to accept one. The account was therefore deleted and recreated with `EnableNoSQLVectorSearch` set at
creation. That reset removed `checkpoints` and `investigation-index` as a side effect of the
rebuild rather than as a sequenced deletion, so the CLI-deletion sequencing described above no
longer has a subject. Their contents were inspected first and were entirely rejected-architecture
data: 1229 checkpointer documents, one idempotency-index document, and eight job records carrying
`pending_interrupt`, `publication_id`, and `decisions`.

Because the application recreated both containers at runtime through create-if-not-exists, removing
them from the template alone would not have held. The Bicep settings that selected the Cosmos
checkpointer and the Cosmos investigation repository were removed with them, so the application now
takes its own defaults and nothing recreates either container. The hosted smoke's durable-pause
check went at the same time and for the same reason: it asserted that an in-flight pause survives a
replica restart, which the accepted design does not claim, so leaving it would have failed the
deployment gate against correct behavior. What remains for 5.2 and 6.1 is the code deletion each
already owns; the live containers and the deployment settings are done.

---

## Layer 1 - Ground-truth corpus

**What it makes safe.** Everything above this layer is measured or queried against a fixed corpus.
Until the corpus is loaded where the design says it lives, carries the provenance and metadata that
admission filters and retrieval filters read, and has a golden record per authored incident, no
measurement above it means anything and no retrieval or capability slice can be verified.

**Definition of done.** The corpus defects are repaired, which `status.md` - "Data and evidence
state" records under "Authored corpus and repairs"; the seven authored incidents each carry a golden
scenario record of the shape `evaluation.md` §5 fixes; the coverage audit of `evaluation.md` §4 has
been run and its result recorded, with the scenario selections named only after the repairs land;
the knowledge and operational-records containers exist, are populated by the setup identity, and
carry collection category, provenance, extracted identifiers, and entity and time metadata; and the
application identity holds read-only access to both.

### 1.1 Corpus repairs

**Makes true.** The authored corpus tells a physically coherent story with no leaked answers, and
all five scenario classes are represented in what it contains.

**Requires.** Nothing.

**Closes.** `status.md` - "Data and evidence state": the chronology, answer-leakage, and closure
facts of "Authored corpus and repairs," and the class representation and controlled non-incident
fixture of "Scenario class coverage."

**Retires.** Nothing. The evaluation input surface the golden records replace is retired in 1.2 with
the records that replace it.

**Shape.** Repair, not replacement. The corrections are to generated telemetry and authored notes:
the contradictory series, the effect-before-cause orderings, and the answer leakage whose repair
`status.md` - "Data and evidence state" records under "Authored corpus and repairs". Coverage is
closed within the accepted seven-incident scope: "Scenario class coverage" records the
multi-contributor class carried by an authored incident and the benign or transient class by a
controlled non-incident fixture derived from the existing ambient events. Nothing here authors an eighth incident and nothing here
writes a golden record.

**Tests.** Two properties the existing closure gates do not catch belong here, because an earlier revision of `status.md` recorded both as failing, and `status.md` - "Data and
evidence state" now records both as asserted under "Authored corpus and repairs": a repaired series
must move in the direction its own postmortem narrates, and no tool-visible field may name the
answer. The gates that already pass must still pass after the repairs, so reference closure is
re-run rather than assumed: the same row records closure as holding, and a repair that breaks one
is a regression rather than a new finding.

**Evaluation.** Nothing is scored here. This slice exists so that what is scored later is scored
against a corpus that does not contradict itself.

**Done when.** The corpus defects are repaired, which `status.md` - "Data and evidence state"
records under "Authored corpus and repairs"; the multi-contributor and benign or transient classes
are represented; and reference closure still verifies.

**Complete.** `status.md` - "Data and evidence state" carries this slice's subject in two rows.
"Authored corpus and repairs" records the chronology and answer-leakage repairs landed and
asserted, with reference closure holding across the corpus. "Scenario class coverage" records the
multi-contributor and benign or transient classes represented, the second by the controlled
non-incident fixture this slice's shape names.

### 1.2 Golden scenario records, the coverage audit, and the D-006 selections

**Makes true.** Each authored incident carries one golden record stating what a correct
investigation must establish, the corpus has been audited against the five scenario classes, and the
scenario selections are named against real incident identifiers.

**Requires.** 1.1: the corpus defects repaired and the multi-contributor and benign classes
represented, since the audit and the selections read the repaired corpus. An earlier revision of `status.md` held the selections open ("D-006 evidence") until the required
repairs and the coverage audit were done; the current document has no counterpart for that hold,
and `decisions.md` D-006 is accepted, so the stated citation stands as a divergence whose question
is closed. The reason the hold existed was substantive rather than procedural: the repairs change
what there is to select from. A record authored against an
uncorrected series would state an expectation the repaired corpus no longer supports.

**Closes.** `status.md` - "Data and evidence state", "Golden scenario records."

**Retires.** The wild generalization probe: `eval/wild.py`, `record_wild.py`,
`wild_scorecard.json`, the manifest-less `wild_single_agent.json` cassette, and
`tests/fixtures/wild_ob/`. The probe is the evaluation input surface the golden records replace,
and `requirements.md` §12 defers the capability it demonstrates. The wild-probe test goes with it.
The probe alone is retired: the RCAEval profile is a live input to corpus generation and is
retained, and the profile-calibration pipeline is not this slice's subject. The deletion rows this
retirement cited belonged to an earlier `status.md`; the current document records nothing about the
probe, so the stated citation has no counterpart, while the retirement itself is performed.

**Shape.** New authored records beside the existing answer key. The answer key and its projection
are not rewritten; the golden record is the evaluation-facing artifact authored from them.

**Tests.** The closure discipline that already ties the answer key to the generated telemetry
extends to the golden records: every evidence reference a golden record requires must exist in the
repaired corpus. A golden record naming evidence the corpus cannot produce is a corpus gap, not a
test failure to tolerate.

**Evaluation.** This is the input every later scenario-outcome measurement reads. The scenario selections D-006 left pending are recorded here against the candidate mapping an
earlier revision of `status.md` supplied: the change-time subset, the milestone set, the
repeatability subset, the further-evidence demonstration, and the retrieval-influence scenario.
Naming them is a corpus lookup rather than a decision this plan makes. That mapping has no
counterpart in the current `status.md`, and the selections are accepted in `decisions.md` D-006, so
the stated citation stands as a divergence whose question is closed.

**Done when.** Every authored incident has a golden record of the shape `evaluation.md` §5 fixes;
the audit table has one row per scenario class, with the multi-contributor and benign classes
recorded as represented; and the scenario selections D-006 lists are named against real incident
identifiers.

**Complete.** `status.md` - "Data and evidence state" carries this slice's subject. "Golden
scenario records" records one record per authored incident, authored beside the answer key, every
required reference resolving, deliberately absent evidence held as prose, and all eight parts
present with classes and outcome shapes from the accepted vocabularies. "Scenario class coverage"
records the audit performed 2026-08-09 with one row per scenario class and both previously missing
classes represented. The selections are accepted in `decisions.md` D-006, and `status.md` - "Known
gaps and unresolved issues" records every decision record other than D-004 as accepted.

### 1.3 Corpus preparation into the RetailEase containers

**Makes true.** The corpus is loaded, chunked, embedded, and indexed into the containers the design
reads at runtime, by a setup identity separate from the application's.

**Requires.** 1.1: the repaired corpus, which is what is loaded.

**Closes.** `status.md` - "Implemented capabilities", "Offline corpus preparation", and
`status.md` - "Data and evidence state", "Cosmos data plane": the populated knowledge and
operational-records containers, embedding at load time, and the identifier and category metadata
the loaded passages carry.

**Retires.** Nothing. The corpus is authored, and the RCAEval profile the register carries under "No
accepted slot or explicitly deferred" as "External ITSM/RCAEval profile-calibration pipeline"
calibrates corpus generation, so it is a live input this slice retains rather than removes.

**Shape.** New offline preparation task with its own identity and its own data-plane access to the
containers it writes and the embedding deployment it calls (`system-design.md` §8.4, "Corpus
preparation"). It is not a component, participates in no turn, and is reachable from no runtime
code. The authored corpus files stay as the source it reads.

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

**Complete.** `status.md` - "Implemented capabilities" records "Offline corpus preparation": a
separate task with its own identity that loads, chunks, embeds, and indexes the authored corpus
and verifies by reading back what it wrote. `status.md` - "Data and evidence state" carries the
rest of the definition of done: "Cosmos data plane" records both containers populated; "Corpus
preparation idempotence" records a re-shaping producing identical passage ids and identifiers and
a re-run converging by upsert, read back byte-identical; "Corpus writer identity" records the
setup principal as the only writer, declared in the template. "Runtime and deployment state"
records the embedding deployment provisioned.

**Divergence.** The readiness obligation this slice's tests named, that absent preparation must
present as a deployment-time failure, was not implementable here: nothing read either container, so
the check would have gated deployment on data no code consumed. It is recorded against the two
slices that create the first readers.

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

**Requires.** Nothing.

**Closes.** `status.md` - "Implemented capabilities", "Two-axis capability results."

**Retires.** The binary tool-result status, and with it the status-envelope assertions in the
tool tests, which asserted the collapsed vocabulary the design prohibits. The retirement is
evidenced by `status.md` - "Implemented capabilities", "Two-axis capability results": the legal
pairings are enforced on construction, so the binary form cannot exist to be read.

**Shape.** Rewrite. The envelope in `tools/contracts.py` survives as a shape; its status field and
every adapter's use of it do not. Each adapter translates its provider outcome into the two axes
(`data-and-evidence.md` §4), and an invalid pairing is rejected at the adapter boundary as a defect
in that adapter (`code-guidelines.md` §6).

**Tests.** The distinction a reviewer would not think to protect is `succeeded` with `empty` against
`unavailable`. A source that answered authoritatively with nothing and a source that did not answer
must be separately representable, separately admitted, and separately visible downstream; collapsing
them turns an unreachable source into a clean bill of health.

**Evaluation.** Result-vocabulary validity becomes a deterministic conformance check
(`evaluation.md` §7).

**Observability.** The tool and capability boundary emits both axes, not a success flag.

**Done when.** No path can produce a result outside the legal pairings, and no code reads a tool
result as a boolean.

One temporary collapse to the old binary remains for the legacy runtime and is deleted with that
runtime; no new caller may use it.

**Complete.** `status.md` - "Implemented capabilities" records "Two-axis capability results": the
legal pairings are enforced where the envelope is constructed, so an illegal pairing cannot exist
to be read, and a source that answered with nothing stays distinguishable from one that did not
answer. That row carries this slice's subject.

The second half of this slice's own "Done when," that no code reads a tool result as a boolean, is
not a fact status records, so it is not derived here.

### 2.2 Capability adapters over the operational-records container

**Makes true.** The five operational capabilities read the operational-records container through the
registry, with validated parameters, scope limits, and the deadline they were given.

**Requires.** 1.3: the populated operational-records container. 2.1: the two-axis result contract
each adapter translates into.

1.3 left "absent preparation is a deployment-time failure and must present as one" unimplemented,
because nothing read the container and a readiness check would have gated deployment on data no code
consumed. This slice creates the first consumer, so the obligation attaches here: once these
adapters read the container, an empty or missing container must fail at deployment rather than at
turn time. The data is in place; the failure behavior is what is missing.

**Closes.** No required behavior. `status.md` - "Implemented capabilities", "Read-only
operational capabilities" records the registry and the operational capabilities as built.

**Retires.** Corpus path resolution, whose two owners disappear with the file-backed corpus
repository, and the read-only capability inventory, which collapses into the explicit static
capability registry. The deletion rows this retirement cited belonged to an earlier `status.md`
and already had no counterpart when the work landed, which the divergence below records; the
current document likewise carries none.

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

**Complete.** `status.md` - "Implemented capabilities" records "Read-only operational
capabilities": the operational capabilities read the operational-records container through the
registry with validated parameters and an explicit deadline, a request naming no deadline is
refused at dispatch, and a container that cannot answer reports unavailability rather than a
generic error. That row carries this slice's subject.

**Divergences the slice text did not anticipate.** First, its two named
retirements, "Corpus path resolution" and "Read-only capability inventory," have no counterpart in
the register: neither row exists in "Duplicated logic to collapse," which holds only citation
grounding, runtime implementation selection, and embedding and reranker model names. The work both
rows describe is done, and no row was authored to record it. Second, the container partitions on
`/kind` and a dependency edge carries a field of that name, so preparation had been overwriting each
edge's relationship kind with the partition value. Nothing failed at write time and the read side
found every edge claiming the same kind. Preparation now carries the edge's own kind as
`dependency_kind`; the live container was reseeded and read back against the shaping.

This slice's deployment verification has no counterpart of its own to build. The refusal it names
is check 4 of the eight in `runtime-and-deployment.md` §16, which 8.2 owns and which pairs it with
the write half this layer cannot yet perform. What belongs here is the posture that check will
assert, and it holds: inspected live, the application identity carries Data Reader on the
`retailease` database and Contributor only on its own investigations container, and the reader
definition contains no write action.

### 2.3 Evidence admission, limitations, and the operation ledger

**Makes true.** A normalized result becomes evidence only by passing deterministic admission, which
assigns its reference, and everything that did not answer becomes a limitation instead.

**Requires.** 2.1: both axes, which decide evidence against limitation. 2.2: normalized capability
results to admit.

**Closes.** `status.md` - "Implemented capabilities", "Evidence admission", together with the
authoritative-absence form "Evidence reference model" records as citable.

**Unmapped citation.** The sequence previously closed a separate entry for the evidence ledger, the
tool-operation history kept apart from cited evidence. No row of its own carried it at the time, so this slice treated it as part of the admitted-
evidence structures rather than dropping it. The gap has since closed: `status.md` -
"Implemented capabilities", "Evidence admission" now records the ledger kept separately.

**Retires.** The duplicated evidence-reference parsing, whose two parsers become one reference
model owned by admission, which `status.md` - "Implemented capabilities" records under "Evidence
reference model": one parser, one resolver, and one prefix-to-type map.

**Complete.** `status.md` - "Implemented capabilities" records "Evidence admission" as the only
door into the evidence set, assigning the reference and producing a limitation naming the
unanswered question for everything else, with the operation ledger kept separately. That row carries this slice's subject, ledger included.

**Divergence.** The design requires the acknowledgement
(`data-and-evidence.md` §4 and its invariant 5) but names no carrier for it, and the two candidates
were not equal: the citation is authored as a reference and a role and nothing else, so the
limitation is the carrier, which is also the word the design itself uses for what a partial
observation omits. The execution outcome keeps an incomplete answer separable from an operation
that did not answer, so nothing was added to a vocabulary.

**Shape.** New admission code inside the Evidence Access Layer, plus a rewrite of the evidence half
of turn state. The hash-keyed first-seen-wins merge that keeps contradictory observations separate
survives and is what the admitted set is built on; the existing admission module, which admits
model-proposed claims, is a different thing and is untouched here.

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

**Requires.** 2.1: the result contract. 2.3: admission, through which its results pass.

**Closes.** `status.md` - "Implemented capabilities", "Governed structured query": the approved
surface, the bounded structure, validation before anything executes, the mandatory limit, and the
unrepresentability of grouping, ordering, joins, writes, and non-count aggregates.

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

**Complete.** `status.md` - "Implemented capabilities" records "Governed structured query": a
bounded structure over an approved surface, validated before anything executes, translated into one
parameterized read-only query, and admitted through the same two axes as any other capability, with
no query text constructed from caller input. That row carries this slice's subject.

**Three divergences.**

First, the approved surface had no counterpart to cite. No accepted document names which
operational records the path may address, and the one place a selection appeared cited a section
that does not contain it and named JSON files that stopped being a runtime source. The surface was
therefore chosen rather than derived: `incident`, `deployment`, and `alert`. Its fields are
narrower than the stored records, because this is the only path on which a model selects its own
projection and the corpus carries its own answers; the incident root cause, resolution, and close
code, and deployment notes, are absent from the surface rather than trusted not to be requested.
That narrowing does not close the exposure, since the incident capability returns those fields
today and the old runtime reads the resolution for its known-issue path.

Second, a count cannot be row-bounded. Every form that tries is rejected by the source: a counted
subquery, aliased or not, projecting a literal or a field, and the OFFSET/LIMIT variant. The limit
remains mandatory in the structure, and the deadline is what bounds that form's work.

Third, the slice's fixture-truth obligation cannot be discharged by a test double. A stand-in that
filtered rows would have to be a query engine to disagree with the translator, so the two would be
wrong together. What the query says is asserted deterministically on the emitted text and its bound
values; what an outcome means is asserted against a stand-in that ignores the query entirely; and
that the query means what it appears to mean was established against the live container. The second
divergence above was found only by that last step, after a deterministic assertion had accepted the
broken form.

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

**Requires.** 1.3: the populated knowledge container and the embedding deployment. 2.1 and 2.3: the
result contract and admission, which retrieval results use like any other capability.

1.3 left "absent preparation is a deployment-time failure and must present as one" unimplemented,
because nothing read the container and a readiness check would have gated deployment on data no code
consumed. This slice creates the reading half, so the obligation attaches here alongside 2.2's. The
data is in place; the failure behavior is what is missing.

2.2 has since implemented its half: readiness counts every operational record kind and fails closed
on zero or unreachable. The knowledge half remains, and remains here. Knowledge continued to load
from files in the image through that slice, which deleted only the file-backed operational
repository, so the retrieval work this slice owns was not pulled forward.

The container's vector configuration is established by 1.3 and not re-verified here: a
1536-dimension cosine policy with a diskANN index, `/embedding` excluded from the normal index, and
`VectorDistance()` returning the semantically correct passage without a same-domain distractor
surfacing. One property is easy to get wrong and worth stating: a container's vector embedding
policy is not fixed at creation, and a path can be removed and re-added at a different dimension.
Only in-place modification is refused. The account capability is the creation-only part, and the
partition key is the immutable one.

**Closes.** The passage-bearing half of `status.md` - "Partially implemented and missing
capabilities", "Accepted retrieval."

**Retires.** The pointer-returning retrieval result, the local sentence-transformers embeddings,
and the local transformer vector-index stack, all of which `status.md` - "Partially implemented
and missing capabilities" records under "Accepted retrieval" as the superseded stack still
present. No retrieval test goes with them; the reranker cases are retired in 3.2.

**Shape.** Rewrite of the retrieval subsystem's storage and result shape. What survives is what the earlier register recorded as implemented and reusable, lexical
retrieval and reciprocal-rank fusion, together with the section-level chunking and metadata
filtering an earlier revision of `status.md` recorded as aligned with D-003; the current document
carries no per-design-area state, so that citation stands as a divergence. What changes is where passages live, what a
hit carries, and which embedder produces the query vector. Query-time embedding moves to the Azure
OpenAI embedding deployment, which is what leaves the local embedder with no consumer.

**Blocked detail.** An earlier revision of `status.md` recorded ("D-003 vector viability") that
no Cosmos vector-index configuration existed anywhere. The current document contradicts that:
"Data and evidence state", "Cosmos data plane" records the knowledge container live under a
1536-dimension vector policy, so the viability this slice was to verify is established and the
in-process cosine scan needs no recorded revision to D-003. The stated citation stands as a
divergence resolved in this slice's favor.

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

**Requires.** 3.1: passage retrieval. 1.2: the golden records the measurement run scores against.

**Closes.** `status.md` - "Partially implemented and missing capabilities": the deterministic
promotion and passage-budget truncation of "Accepted retrieval", and the lexical baseline within
"Categorical evaluation, judge, baselines, report."

**Retires.** The unreachable model reranker (`retrieval/reranker.py`, `Retriever.rerank()`,
`RERANK_CANDIDATES`, the `reranker` test marker, and the `bge-reranker` references), whose removal
pairs with this slice's deterministic promotion, together with the CrossEncoder reranker and the
duplicated embedding and reranker model names. `status.md` - "Partially implemented and missing
capabilities" records the stack under "Accepted retrieval" as superseded and still present.

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

**Requires.** 1.3: the embedding deployment, whose two chat siblings this slice adds.

**Closes.** `status.md` - "Runtime and deployment state": the lower-cost chat deployment it
records as not existing beside the one chat and one embedding deployment. The task-label and
usage-total row this slice also cited has no counterpart in the current `status.md`, whose only
task-label fact is the one labelled call "Implemented capabilities", "Model-proposes, code-admits
synthesis" records; the remainder of that citation stands as a divergence, with 9.1 owning the
totals.

**Retires.** The dead configuration: `PROD_MODELS`, `Tier`, `SEVERITY_TIER`, `resolve_tier`,
`ENABLE_OPUS_SEV1`, `JUDGE_MODEL` as-is, `MAX_TOOL_CALLS`, `CONFIDENCE_THRESHOLD`,
`LANGSMITH_ENABLED`, and the dispatch knobs, whose replacement is D-002 task-label routing. The
dispatch knobs went with the WIP commit in preparation. The severity-routing case in the scaffold
test goes with the table it asserts. The deletion row this retirement cited belonged to an earlier
`status.md`; the current document records nothing about the dead configuration, so the stated
citation has no counterpart.

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

**Requires.** 4.1: the model-access seam. 2.2, 2.4, and 3.1: the capability set it selects from.
2.3: the admitted evidence it observes.

**Closes.** `status.md` - "Partially implemented and missing capabilities":
"Observation-driven evidence selection", and the investigator half of "Supervisor, Evidence
Investigator, RCA Analyst as distinct roles", proposal contract included.

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
influenced it. The role is an ordinary function over turn state, with no orchestration awareness of
its own: it does not sequence itself, schedule the next stage, or call the RCA Analyst directly,
which D-001 leaves to the turn controller.

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

**Requires.** 2.3: admission-assigned references, which supporting and weakening citations resolve
to.

`status.md` - "Implemented capabilities" records "Assessment contracts" as built, and
"Partially implemented and missing capabilities" records "Further-evidence cycle" as missing. What
the first row carries is the candidate set with its three qualitative labels,
supporting and weakening references per candidate with a knowledge reference refused in either role,
the established-or-possible markers with an established element requiring current operational
support and an alternative and a historical comparison unable to be constructed as established,
recommendations carrying exactly one horizon and one provenance category checked together with the
reference that provenance implies, recorded limitations, and the ordered brief sections a
deterministic projection fills by traversal alone. No numeric value exists anywhere in it.

Two things remain. The further-evidence need has no representation in the assessment at all, so the
half of this slice's closure that names it is untouched. Neither retirement has been performed: the
superseded report object still carries its confidence float and the old console still renders that
value as a percentage, so the two contracts coexist rather than one replacing the other.

**Closes.** `status.md` - "Implemented capabilities": "Assessment contracts" and "Deterministic
brief projection", together with the representation half of what "Partially implemented and
missing capabilities" still records missing under "Further-evidence cycle."

**Retires.** The superseded result and report contracts and their numeric confidence, which
`status.md` - "Temporary legacy and coexisting implementation" records under "Report and claim
model" and, for the confidence rendering, "Approval console."

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

**Requires.** 4.1: the model-access seam. 4.2: the Evidence Investigator it is split from. 4.3: the
assessment contract it produces.

`status.md` - "Implemented capabilities" records "Model-proposes, code-admits synthesis" as
built, and "Partially implemented and missing capabilities" records "Supervisor, Evidence
Investigator, RCA Analyst as distinct roles" as missing. The synthesis behavior exists as a module
rather than as a role: one task-labelled call proposes
an assessment and deterministic code admits it against the admitted evidence set: a reference the
turn never admitted is dropped, a candidate left with no surviving support is dropped entirely, the
conclusion disposition follows from the evidence rather than from anything the model asserted about
its own certainty, and a response that cannot be read degrades to a thin assessment rather than
losing the turn. That module reaches no capability and no structured-query path, which is the
structural half of what this slice asserts.

What remains is the split. The fused planner still gathers and concludes, so the retirement this
slice owns is outstanding and no code path yet makes it impossible for one role to do both.

**Closes.** The analyst and investigator halves of `status.md` - "Partially implemented and
missing capabilities", "Supervisor, Evidence Investigator, RCA Analyst as distinct roles."

**Retires.** The fused planner that both gathers and concludes, which `status.md` - "Temporary
legacy and coexisting implementation" records under "Report and claim model", together with the
fallback pairing case in the composition test.

**Shape.** Rewrite of the synthesis path into a separate role. The model-proposes and code-admits
split survives, and so does template rendering; the fused module does not. After this slice no code
path lets one role both gather and conclude, and the implementation-selection fallback that paired a
planner with a triager has nothing left to select between. Like the Evidence Investigator, the role
is an ordinary function over turn state: it does not sequence itself, schedule the next stage, or
call the Evidence Investigator directly, which D-001 leaves to the turn controller.

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

**Requires.** 2.4: the deterministic validation that accepts or rejects the structure. 4.1: the
model-access seam.

**Closes.** The model-generation half of the governed structured-query path. `status.md` -
"Implemented capabilities", "Governed structured query" records the deterministic half built; no
current row records the generation task.

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

**Requires.** 2.2: the capability implementation the boundary shares. 2.3: the admission path it
shares.

**Closes.** `status.md` - "Partially implemented and missing capabilities", "Single accepted
protocol exposure", transport visibility included.

**Retires.** The three superseded exposures `status.md` - "Partially implemented and missing
capabilities" names under "Single accepted protocol exposure" (`get_incident`, `query_logs`,
`search_runbooks`), together with the three-tool surface cases in the parity test.

**Shape.** Heavy modification. What survives is the boundary the earlier register recorded as partial and promising, and the
delegation it recorded as implemented and tested: one `call` path, one validation, sanitized
errors, and a parity assertion. What changes is which capability is exposed and that only one is.

**Blocked detail.** `status.md` - "Known gaps and unresolved issues" records D-004 as the one
open decision, still pending library inspection and blocking this exposure alone. An earlier
revision also recorded that the current SDK usage answers much of the question while the explicit
inspection and final record remain required; that evidence note has no current counterpart. Moving
D-004 to accepted is a `decisions.md` change and a precondition of this slice; this plan does not
decide it.

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

**Requires.** 2.3: admitted evidence and limitations. 4.3: the assessment the artifact carries.

`status.md` - "Implemented capabilities" records "Investigation Record port and commit ordering"
as built over an in-memory backend, while "Partially implemented and missing capabilities" records
both "Completed-turn artifact" and "Durable completed-turn persistence" as missing. The port
therefore stands ahead of the artifact it stores. It fixes the commit success and failure
contract, carries a sanitized reason so a persistence problem is never indistinguishable from a
grounding or model one, and is structural over anything carrying an investigation and turn identity,
so the artifact can gain its fields without reopening it. Its in-memory backend refuses a second
commit of the same turn rather than overwriting, and brings the investigation into existence on the
first successful commit, which is what makes two of this slice's three named properties assertable
today: a turn that never completes leaves nothing persisted, and a failed first execution leaves no
investigation shell.

What remains is the artifact and every removal. The completed-turn type does not exist, so nothing
carries the terminal outcome, stop reason, admitted evidence, retrieved-knowledge references,
assessment and brief, follow-up context, or the trace reference and its version stamp, and the third
named property, that completed records stay readable after the code that wrote them changes, has
nothing to assert against because no persisted type carries version information. The job record, its
status machine, its leases, its idempotency index, the create-then-poll transport, and the decision
endpoint are all still present, so the removals this slice owns are outstanding in full.

**Closes.** `status.md` - "Partially implemented and missing capabilities": "Completed-turn
artifact" and "Durable completed-turn persistence", restart-safe citation resolution included,
of which this slice removes the index and worker machinery while 6.1 removes the checkpoints and
replay machinery.

Divergence: the live `investigation-index` container is already gone, removed 2026-08-09 when the
Cosmos account was deleted and recreated to gain the vector-search capability, which cannot be
added to an existing account. The Bicep declaration and the deployment setting that selected the
Cosmos investigation repository went with it, so nothing recreates it. What this slice still owns
is the code: the idempotency-index machinery in the repository modules, and the job-record
lifecycle around it. Entry into this slice does not need to delete a container or plan a live
deletion, and the "Live containers the template will stop declaring" preparation note above is
superseded for the same reason.

**Retires.** What `status.md` - "Temporary legacy and coexisting implementation" records under
the job API row: the create-then-poll transport and its status vocabulary, the decision endpoint
and committed decisions, the versioned idempotency machinery, publication identity and the
approval-bound report hash, and the leases and fencing, of which the `hitl_gate` and `apply_edit`
node members go in 6.1 and the console and `Approver` members in 7.4 with the console and
authorization rows. This slice also performs the removal half of the transport-and-console
replacement whose streaming half is 7.1. The tests that die with these subjects are the HITL and
decision suite, `test_report_binding.py`, and the investigations and investigations-API modules;
the test inventory an earlier `status.md` carried for them has no current counterpart.

**Shape.** Rewrite, and the largest slice in the plan. The persistence modules are replaced rather
than adapted: what persists is one logical artifact carrying identity, objective, terminal outcome,
stop reason, admitted evidence, retrieved-knowledge references used, assessment and brief where
produced, limitations, follow-up context, and the trace reference with its version stamp and usage
totals. The job record, its status machine, its leases, and its idempotency index have no
counterpart in that artifact and go with it. The ETag and publish-idempotency techniques an earlier revision of `status.md` recorded as
reusable carry into the completed-turn commit; the current document holds no per-component
reconciliation, so that citation stands as a divergence.

The endpoints those stores served are removed here, and their replacement arrives in layer 7. From
this slice until 7.1 the deployed application serves health and no turn surface. The tree stays
green, the tests and the evaluation harness drive turns in process, and the deployment smoke is
reduced to the checks that still have a subject until 8.2 replaces the suite. Two pairings split
across that gap: Replace: "`api.py` transport + console" is removed here and replaced in 7.1 and
7.4, and Replace: "Hosted smoke" loses its async and decision legs here and is replaced in 8.2,
because neither can survive the removal of the endpoints it calls.

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

**Requires.** 4.2 and 4.4: the roles it sequences. 4.1: the model-access seam. 2.3: admission.
5.2: the artifact it delivers to.

`status.md` - "Implemented capabilities" records "Turn and investigation identity" as built, and
"Partially implemented and missing capabilities" records "Explicit turn controller" as missing. Only
identity has landed. The investigation and turn identities are minted together
and carry the incident under study beside them, which is one input the state machine reads rather
than any part of the machine itself; because nothing persists yet, an investigation lives only for
the turn that opens it.

Everything else this slice names remains. There is no stage sequence, no Supervisor owning the
objective or authorizing continuation against computable conditions, no back-edge, and no
enforcement of the six bound mechanisms as a set rather than as scattered local limits. Every
retirement is outstanding: the superseded graph implementation with its nodes and routers, the
checkpointer stack and its dependency, and the old intent taxonomy and its known-issue path are all
still present. The
divergence recorded below discharges the container half of the checkpointer entry; the code half
stands.

**Closes.** `status.md` - "Partially implemented and missing capabilities": "Explicit turn
controller", the Supervisor half of "Supervisor, Evidence Investigator, RCA Analyst as distinct
roles", and the back-edge "Further-evidence cycle" records as missing.

**Unmapped citation.** The sequence previously closed an entry for the investigation, turn, and
live-session model itself. The current register names the state machine and the streaming request
but has no row for the model, so this slice carries it inside "Explicit in-process state machine."
That is a gap between the plan and the register.

**Retires.** What `status.md` - "Temporary legacy and coexisting implementation" records under
"Graph orchestration and its nodes, routers, and checkpointer" with its three dependencies,
together with the `postmortem` output path, the `hitl_gate` and `apply_edit` node members of the
approval surface, and the severity-scaled sufficiency stop rule and old intent taxonomy the
"Report and claim model" row carries. The tests that die with these subjects are
`test_checkpointer.py`, the sufficiency test, the triage and triager tests, and the escalate and
sufficiency routing cases of the diagnose test. The intent taxonomy is retired here because the
routing stage it lived in disappears with the stage sequence, while the required behavior it is
measured against, "Request-shape classification of follow-up, redirect, supplied context, handoff,
and read," is a transport behavior and lands in 7.2, so that pairing spans two slices.

Divergence: the `checkpoints` Cosmos container, both its Bicep declaration and the live container,
is already gone as of 2026-08-09, removed when the account was deleted and recreated to gain the
vector-search capability. The deployment setting that selected the Cosmos checkpointer went with
it, so the checkpointer has no live backing store and nothing recreates one. The hosted smoke's
durable-pause assertion was removed in the same change, because it tested that an in-flight pause
survives a replica restart, which the accepted design does not claim. What this slice still owns is
the code and the dependency: `checkpoint.py`, the `langgraph-checkpoint-sqlite` dependency, the
msgpack allowlist, and `test_checkpointer.py`. The "(Bicep + live)" half of that register entry is
discharged.

**Shape.** Rewrite. D-001 settles that the turn is an explicit five-stage state machine expressed as
a compiled graph over typed turn state, running in one process. The checkpointer stack and its
dependency retire; the graph build does not. The superseded graph implementation and its nodes are
still replaced rather than migrated, so its conditional edges and node bodies are rewritten, but what
survives from that implementation is the dependency the new graph compiles against, not the code.
Continuation conditions and bound enforcement remain application code covered directly by tests,
which is the trade-off D-001 accepts.

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

**Requires.** 6.1: the stage it runs in. 4.3: the assessment it checks. 2.3: the references it
resolves. 4.1: the one corrective call.

**Closes.** `status.md` - "Partially implemented and missing capabilities", "Grounding gate,
correction allowance, completed outcomes": the four checks, the shared correction allowance, and
no artifact after persistent failure, whose terminal-shape half closes in 6.3.

**Retires.** The one-check gate routing to escalation and the duplicated citation grounding,
which `status.md` - "Temporary legacy and coexisting implementation" records under "Two-policy
grounding"; the two occurrences become one gate at one stage over one object. The approval-routing
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

**Requires.** 6.1: the turn state that carries the outcome. 6.2: the gate failure that can end an
attempt.

**Closes.** `status.md` - "Partially implemented and missing capabilities": the outcome
vocabulary of "Grounding gate, correction allowance, completed outcomes", the safe-boundary and
both cancellation paths of "Explicit cancellation signal", and the terminal shape 6.2 left open.

**Retires.** The escalate cases in the diagnose test. The vocabulary that carried escalation as a terminal status is retired by rows other slices own:
the job API status vocabulary in 5.2 and the result and report contracts in 4.3, both recorded in
`status.md` - "Temporary legacy and coexisting implementation", which drops the escalation variant
of the result union. The `escalate` node itself goes with the graph orchestration in 6.1.

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

**Requires.** 6.1: the turn it terminates. 6.3: the assembled outcome. 5.2: the store it commits to.

`status.md` - "Implemented capabilities" records "Investigation Record port and commit ordering",
whose commit-ordering half is this slice's subject; "Partially implemented and missing capabilities"
records "Completed-turn artifact" as missing. The ordering is expressed in one place that commits
and
delivers only where that commit succeeded. A caller cannot deliver first by accident, and a caller
that ignores the returned result still cannot have delivered on a failed commit, because delivery is
unreachable on that path rather than merely discouraged. The failed-execution branch is
representable there, and the first successful commit is what creates the investigation.

What remains is a caller and what it would commit. No runtime path invokes the ordering, since
neither the assembled turn state nor the artifact type exists, so the property holds today only
where tests drive it directly. The persistence-failure branch has no terminal outcome to resolve
onto, the no-evidence cancellation path has no artifact whose omitted assessment and brief could be
shown to be representable, and neither the write nor the terminal outcome is emitted, because the
record modules carry no instrumentation.

**Closes.** The commit-before-delivery obligation on both sides of the seam: the ordering
`status.md` - "Implemented capabilities" records under "Investigation Record port and commit
ordering", gaining the runtime caller "Partially implemented and missing capabilities" records as
missing under "Durable completed-turn persistence."

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

**Requires.** 6.1 through 6.4: a turn that executes, validates, resolves an outcome, and commits
before delivery.

`status.md` - "Implemented capabilities" records "Streaming turn transport" and "Activity
projection" as built, while "Partially implemented and missing capabilities" records "Grounding
gate, correction allowance, completed outcomes" as missing. The transport therefore stands ahead of
the turn it exists to carry. One streaming request creates a turn,
emits the identities as its first event, streams activity as it happens, and ends with a closing
event, served as an ordinary streaming body with no create-then-attach pair, no reconnection, no
event buffering, and no sequence cursor. The activity projection is built at the same call site that
opens the telemetry span, from the same explicit facts, with no parameter through which a span's raw
attributes could reach the projected event. Both properties this slice named are asserted: the
projection carries no answer-key content, and turn isolation across concurrent investigations holds
structurally rather than as a convention about keys.

What remains depends on layer 6. The request is deliberately non-terminal, so no gate runs, nothing
is committed, and the closing event is a transport-ordering proof rather than a delivered outcome,
which leaves the deployment check that reads the persisted artifact for that turn without a subject.
Both retirements are outstanding: per-user and global concurrency admission and the deprecated
health alias are all still served. The surface sits beside the superseded job API rather than
replacing it, because the removal half 5.2 owns has not run.

**Closes.** `status.md` - "Implemented capabilities": "Streaming turn transport" and "Activity
projection," which together cover one live streaming request owning a turn, the identities as its
first event, activity streamed as it happens, a closing event, and the projection built at the same
call site that opens the telemetry span from the same explicit facts.

**Retires.** An earlier revision of `status.md` recorded, under "Deletion and Replacement
Register," that per-user and role-based concurrency admission and the deprecated `/health` alias
would retire here; the current document carries no counterpart row for either, and both remain
reachable in the tree, so neither retirement has been performed here. This slice does perform the
streaming half of the `api.py` transport-and-console replacement, whose removal half landed in 5.2.

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

**Requires.** 7.1: the turn surface a normalized incident opens. 5.2: the retained state a
follow-up, handoff, and read answer from. 4.1: the lower-cost deployment normalization routes to.

**Closes.** `status.md` - "Partially implemented and missing capabilities": "Free-text
normalization and clarification," missing entirely because only predefined intake exists today with
no clarification path of any kind; and "Follow-up, redirect, supplied context, handoff," missing its
classifier and its retained-state answering, though the five-kind interaction type already exists in
`intake/contracts.py`.

**Retires.** Nothing here. "Old intent taxonomy and known-issue fast path," which this
classification replaces, was retired in 6.1 with the routing stage it lived in.

**Shape.** New. Normalization is the one model task the interaction interface holds, on the
lower-cost deployment (D-002), and its proposal is admitted by deterministic code against the
normalized incident context contract. Classification is established from the request shape or the
explicit interface action, never by analyzing prose and never by a model call, and an ambiguous
ordinary follow-up defaults to a question. The handoff summary is a deterministic projection of
retained state that calls no model.

**Blocked detail.** `status.md` - "Known gaps and unresolved issues" records the stateless
clarification token as the one open question with no decision record: a short-lived normalization
token would need an explicit signing, expiry, and payload contract, and a simpler resubmission path
is preferred where it meets the requirement. That is still a decision for the design set, not for
this plan.

An earlier revision of `status.md` also blocked this slice on "Normalized incident context fields,"
the need for one typed contract for normalized input. The current document contradicts that:
`decisions.md` D-007 is accepted, and "Implemented capabilities," "Predefined intake normalization"
records the typed, frozen normalized incident context as built. That half of the block is closed.

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

**Requires.** 7.1: the streaming request it signals. 6.3: cancellation on both paths producing a
completed turn.

`status.md` - "Partially implemented and missing capabilities" records "Explicit cancellation
signal" as partial: disconnect detection exists, the explicit signal does not. The partial half is
not what this slice names.
The turn checks whether the client has left before each further unit of work and abandons the turn
by returning; nothing survives, because nothing on that path persists at all. That is the floor this
slice signals into.

The explicit cancellation signal remains, entirely. No request surface exists that would carry one,
the screen offers no control that would send one, and there is no map from active turn identity to a
signal. The difference bounds what can be shown: a departed client is observed between units of
work, so cancellation reaching the operation rather than only the stage boundary is not yet
demonstrable, and a completed turn on both paths waits on 6.3.

**Closes.** `status.md` - "Partially implemented and missing capabilities", "Explicit cancellation
signal": the disconnect-detection half it already records, together with the signalling half this
slice adds, closing the request surface, the client control, and the map from turn identity to a
signal that row lists as missing.

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

**Requires.** 7.1: the stream and brief it renders. 7.2: follow-up and handoff. 7.3: the
cancellation control.

`status.md` - "Partially implemented and missing capabilities" records "Brief rendering in the
client" as partial. One same-origin page carries predefined intake, a compact activity
feed rendered from the streamed events with its content escaped, a brief region, and one expandable
details area, and it does not reach the old console.

What remains includes the dominant element. The page handles the identity, activity, and closing
events and holds no branch for the brief, so a rendered brief arrives and is visible only inside the
details area while the brief region shows a transport message instead; the projection rule this
slice asserts against the presentation path consequently has nothing to assert against yet. No
follow-up, handoff, or cancellation control exists. Every retirement is outstanding: the old console
is still served with its approval controls and its numeric confidence rendering, the hand-rolled
role model still guards the superseded endpoints, and built-in authentication is absent, which
leaves the caller-authentication check without a subject.

**Closes.** `status.md` - "Partially implemented and missing capabilities", "Brief rendering in the
client": the one-screen shell it already records, closed by adding the brief branch the current
screen lacks. `status.md` - "Runtime and deployment state" records that platform built-in
authentication is not configured; this slice closes that.

**Retires.** `status.md` - "Temporary legacy and coexisting implementation": "Hand-rolled
three-role authorization," which guards only the superseded endpoints and is superseded by platform
built-in authentication; and "Approval console," the submit, poll, review, and approve surface with
its numeric confidence rendering, superseded by the one-screen client. An earlier revision of
`status.md` also listed the auth-role suites in a test inventory this slice was meant to retire with
them; the current document carries no such inventory, so that citation has no counterpart, and the
auth-role suites are retired here regardless.

**Shape.** Rewrite. An earlier revision of `status.md`, in its "Detailed State by Design Area"
section, found nothing in the current console survives as the designed interface: its approval controls have no
counterpart and its poll-a-job transport is replaced by the stream. The current document carries no
per-design-area state, so that citation has no counterpart, though the finding itself is not in
dispute. Caller authentication becomes Container Apps built-in authentication with one application
registration, which is the whole of the posture `runtime-and-deployment.md` §12 keeps; no roles,
groups, or authorization policy machinery replaces what is removed.

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

**Requires.** 1.3, 4.1, and 5.2: the containers and deployments the template declares. Every earlier
slice, whose removals this slice reconciles the template to.

**Closes.** `status.md` - "Runtime and deployment state": the replica range, 0 to 3 in the template
against an accepted 0 to 1; the missing Application Insights resource, whose exporter wiring follows
in 9.1; and the container set the template declares.

**Retires.** Nothing on its own. Each earlier slice removed the resources its own behavior owned;
this slice is where what remains is reconciled to the declared set. The live containers a template
change cannot remove are deleted by CLI under the preparation section rather than here.

**Shape.** Heavy modification of the template. What survives is what `status.md` - "Runtime and
deployment state" confirms live: one OIDC workflow and Bicep template, one image, one Container App,
one Dockerfile, keyless managed identity, and scale to zero. What changes is the container set, the
model deployment set, the addition of Application Insights, the replica maximum, which that section
records as 0 to 3 in the template against the accepted 0 to 1, and the removal of parameters that
provisioned machinery no longer present.

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

**Requires.** 8.1: the declared environment. 7.1 and 7.2: the surfaces the checks call. 5.2:
persistence.

**Closes.** An earlier revision of `status.md` recorded "Eight hosted smoke checks" as missing under
Azure and deployment. The current document carries no counterpart row: `scripts/smoke_deployment.py`
still asserts the superseded job and approval behavior, so this slice's closure remains outstanding.

**Retires.** An earlier revision of `status.md`, under "Deletion and Replacement Register,"
recorded "Hosted smoke" as a replacement pending here, its removal half having landed in 5.2 with the
endpoints its async and decision legs called. The current document carries no counterpart row, and
`scripts/smoke_deployment.py` still asserts the superseded behavior, so the replacement itself
remains this slice's to perform, sitting after the streaming and persistence slices as before.

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

**Requires.** 6.1: turn identity. 5.1, 2.3, 6.2, and 5.2: the boundaries that were silent. 8.1:
Application Insights declared.

**Closes.** `status.md` - "Implemented capabilities", "Telemetry emission seam" records the seam
this slice extends. `status.md` - "Runtime and deployment state" records the missing Application
Insights sink this slice adds. An earlier revision of `status.md` also named turn and agent identity,
the MCP, evidence-admission, grounding, and persistence spans, and usage totals as missing rows; the
current document carries no counterpart for any of the three, so those closures are recorded here
without a citation to re-point to.

**Retires.** Nothing.

**Shape.** Extension, not a rewrite. `status.md` - "Implemented capabilities", "Telemetry emission
seam" records it as built and reusable: one seam emitting once at shared primitives,
contextvar-nested parents, correlation identifiers, a swappable exporter, and an in-memory test
fixture. An earlier revision of `status.md`, in its "Detailed State by Design Area" section,
additionally judged it the most reusable subsystem in the repository; the current document carries no per-design-area
judgment, so that citation has no counterpart. What is added is the turn identity that had no model
to carry, the boundaries that had no instrumentation, the events for admission and grounding, cost
attribution, and the Application Insights exporter beside the existing set.

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

**Requires.** 1.2: the golden records. 5.2: completed turns. 9.1: traces with attribution. 3.2: the
retrieval measurement it aggregates.

**Closes.** `status.md` - "Partially implemented and missing capabilities", "Categorical
evaluation, judge, baselines, report": golden scenario records and cassette replay already exist as
inputs, and this slice closes the row's remaining gap, that scoring is still numeric and gate-shaped,
by adding categorical scoring, the judge, deterministic conformance aggregation, and the advisory
report.

**Retires.** `status.md` - "Temporary legacy and coexisting implementation": "Numeric evaluation
thresholds," `EvalTargets` and the scorecard gates it feeds, superseded by categorical scoring; and
the implementation-selection element of "Report and claim model," the runtime re-selection between a
planner and a triager, superseded once the evaluation scripts stop performing it. An earlier
revision of `status.md` also named a generic evaluator registry scaffold and empty package
placeholders under "No accepted slot or explicitly deferred"; the current document carries no
counterpart for either, so those two retirements are recorded here without a citation to re-point
to.

**Shape.** Rewrite. The scoring model changes from numeric scorecards against committed baselines to
one category per dimension drawn from Meets, Partially meets, Misses, and Not applicable, with a
short named reason for anything below Meets. The ratchet baselines and the up-front numeric targets
go with it, and the change-time signal informs a change without gating the merge.

**Blocked detail.** An earlier revision of `status.md`, in its "Implementation Clarifications
Exposed by the Repository" section, held "Evaluation artifact storage" open, pending a physical
repository location for
the report, fixtures, and historical runs. The current document carries no counterpart for that
hold, and `decisions.md` D-009 is accepted, fixing the location as files under the existing `eval/`
tree, so the stated citation stands as a divergence whose question is closed.

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

**Requires.** 9.2: the report both results appear in. 1.2: the subset the comparison runs on.

**Closes.** `status.md` - "Partially implemented and missing capabilities", "Categorical
evaluation, judge, baselines, report": the same row 9.2 closes for scoring and the judge, closed
further here for its baselines, by adding the fixed-script evidence-plan baseline and the
repeatability subset.

**Retires.** Nothing.

**Shape.** Heavy modification of what already exists behaviorally. An earlier revision of
`status.md` recorded the fixed-script baseline as partial deterministic behavior that is wrongly a
runtime fallback; the current document carries no counterpart for that characterization, though the
fact remains true of the code. What changes is that it stops being a runtime fallback tier and
becomes an evaluation baseline, using the same capabilities, permissions, bounds, corpus, and
assessment and brief contract as OpsPilot, with a versioned predetermined evidence plan stored
beside its fixture.

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

An earlier revision of `status.md`, in its "Test and Evaluation Gap Status" section, listed the
tests that die with their subjects as one group: the HITL and decision suite, `test_report_binding.py`,
`test_checkpointer.py`, the auth-role suites, the wild-probe tests, and the reranker-marked tests.
The current document carries no counterpart list, so that citation has no counterpart; the table
below is this plan's own fan-out, because the subjects are superseded in different slices and
`code-guidelines.md` §11 requires a superseded assertion to be retired by the slice that supersedes
it. Each named module retires in exactly one slice.

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

An earlier revision of `status.md`, in its "Implementation Clarifications Exposed by the
Repository" section, recorded six items blocking a slice from being fully specified; the current
document carries no counterpart section. Two survive as open: D-004 and the stateless clarification
token, both now recorded in `status.md` - "Known gaps and unresolved issues". The other four are
closed:
`decisions.md` D-006, D-007, D-008, and D-009 are accepted. None is decided here: each open item is
settled in its owning slice or by a small decision update before code invents an incompatible
answer.

| Blocks | What is unsettled | Item |
| --- | --- | --- |
| 2.3 | One owner for reference prefixes, keys, and parsing; the existing frozen grammar is a candidate to evaluate rather than copy | "Evidence and knowledge reference encoding" |
| 5.1 | The explicit library inspection and the final decision record, which repository evidence answers much of but does not close | "D-004 evidence" |
| 7.2 | One typed contract for normalized input; the current `Alert` shape is evidence, not automatic authority | "Normalized incident context fields" |
| 7.2 | The signing, expiry, and payload rules for a short-lived normalization token, where a simpler resubmission path does not meet the requirement | "Stateless clarification token" |
| 9.2 | A physical repository location for the report, fixtures, and historical runs, which must stay simple | "Evaluation artifact storage" |
| 1.2 | The scenario selections, which wait on the required corpus repairs and the coverage audit | "D-006 evidence" |

The last two are settled inside the slices that carry them rather than by a separate decision. The
D-006 selections are not a corpus read alone: 1.1 repairs the corpus first, and 1.2 then runs the
audit and records the selections against the candidate mapping an earlier revision of `status.md`
supplied; the current document carries no counterpart mapping, so that citation has no counterpart.
That dependency is why the repairs are a slice of their own and why the selections follow them.

