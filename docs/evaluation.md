# OpsPilot - Evaluation

**How do we demonstrate that OpsPilot works, remains grounded and bounded, and earns its agentic
complexity?**

## 1. Purpose and Document Boundaries

This document defines how OpsPilot is evaluated: what is checked, on which scenarios, against which
baselines, by which judge, at what cadence, and how results are reported.

It owns the evaluation posture, the golden scenario model, the evaluation layers, the deterministic
conformance checks, the scenario and judge rubrics, retrieval measurement, the fixed-script and
lexical baselines, the repeatability protocol, the cadence, the report contents, and the policy for
setting targets later.

It does not own what the system must do or mean. Required behavior and scenario classes belong to
`requirements.md`. Evidence meaning, citation roles, assessment and brief semantics, and tool-result
vocabulary belong to `data-and-evidence.md`. Outcome assignment, cancellation, bounds, and
failed-execution behavior belong to `workflow-design.md`. Deployed smoke verification and telemetry
realization belong to `runtime-and-deployment.md`. Settled choices such as the judge deployment and
the exact retrieval method belong to `decisions.md`.

Evaluation artifacts are this document's own. They are produced by offline evaluation, never by a
turn, so they are not the running system's persistence concern; what is retained is stated in §3.

The deployment-verification checks in `runtime-and-deployment.md` prove that a deployment works.
They are not repeated here, and this document does not evaluate infrastructure.

---

## 2. Evaluation Principles

**Evaluation is offline.** It reads completed-turn artifacts and correlated traces after the fact. It
never participates in a live turn, never confirms a diagnosis at runtime, never blocks delivery of a
brief, never routes agents, never changes an outcome, and never edits a brief. There is no judge
agent in the running system and no evaluation authority anywhere in the live chain.

**Evaluation is advisory.** The change-time signal informs; it does not gate merge (NFR-49).
Deterministic safety failures stay visible and are reported by name, but this suite is not a release
gate.

**The completed turn is the unit.** What is evaluated is one completed turn together with its
incident and objective, admitted evidence, retrieved knowledge, assessment and delivered brief where
produced, limitations, stop reason, outcome, trace, and usage. Isolated model messages are not the
product and are not scored as though they were. Subsystem checks may still exercise retrieval,
structured query, tools, and the protocol boundary directly where a requirement demands it. A turn
cancelled before any evidence was admitted carries neither an assessment nor a brief; that exception
belongs to `workflow-design.md`.

**A failed execution is not a completed turn.** It is recorded as such and is never scored as though
it had produced an investigation result. What a failed execution is belongs to
`workflow-design.md`.

**Deterministic before model-assisted.** Anything code can establish is established by code and
reported pass or fail. The judge runs afterwards and only where judgment is genuinely required. A
deterministic result overrides the judge.

**Baseline before targets.** Numeric thresholds are set from measured baseline runs, never invented
in advance (NFR-26, NFR-27). Until that baseline exists, values are recorded and reported as
observations.

**Named failures over aggregate scores.** Results are reported by scenario class with each failure
named (NFR-30). No composite score, weighted scorecard, or overall percentage stands in for the
detail.

---

## 3. Evaluation Inputs and Artifacts

Evaluation consumes what the system already retains and produces one report. It introduces no
runtime component, no service, no queue, and no database of its own.

| Artifact | What it is | Where it comes from |
| --- | --- | --- |
| Completed-turn artifact | The turn's identity and objective, terminal outcome, stop reason, admitted evidence, retrieved knowledge used, assessment and delivered brief where produced, limitations, and its trace reference | Retained by the system (NFR-22, NFR-55, NFR-58) |
| Trace | The correlated record of what the turn did: role activity, model and capability operations, evidence admission, grounding result, latency, calls, tokens, and approximate cost | Runtime telemetry (NFR-14, NFR-18) |
| Golden scenario | What a correct investigation of one authored incident must establish | Authored alongside the corpus (§5) |
| Evaluation run | One execution of a defined scenario set against one configuration, with its metadata and per-scenario artifacts | Produced by the evaluation suite (§15) |
| Evaluation report | The compact human-readable result of one run | Produced by the evaluation suite (§18) |

A turn cancelled before any evidence was admitted produces neither an assessment nor a brief; that
exception belongs to `workflow-design.md`.

**Evaluation artifacts reference completed turns, never the reverse.** Evaluation runs offline, after
the turns it examines already exist, so an evaluation artifact records its own run identity together
with the investigation and turn identities and references to the completed-turn and trace artifacts
it read. What a completed turn carries in return belongs to `data-and-evidence.md`.

**What is retained, and where.** Each evaluation run retains its run identity and metadata (§18),
the per-scenario artifacts it produced, and the report. These are retained alongside the run,
separately from the completed turns they reference, which NFR-55 permits. They are not held by the
running system. Physical layout is not settled here.

Hidden model reasoning is not an evaluation input and is not retained.

### What evaluation reuses rather than reimplements

An evaluation run aggregates results from three sources:

```text
deterministic implementation tests ─┐
deployed smoke verification ────────┼─→ evaluation report
evaluation-specific checks ─────────┘
```

Deterministic conformance (§7) is owned and implemented by `code-guidelines.md` as tests, and by
`runtime-and-deployment.md` as deployed smoke verification. Evaluation orchestrates and reports those
results; it does not independently reimplement citation resolution, read-only permission
verification, query validation, protocol parity mechanics, completed-turn artifact validation, or
bound enforcement.

Evaluation-specific implementation adds only what is unique to it: golden-scenario comparison,
categorical model-assisted judging, retrieval precision and recall, the lexical baseline comparison,
the fixed-script comparison, the small repeatability observations, and report assembly.

---

## 4. Scenario Corpus and Coverage Audit

The evaluation corpus is the seven authored RetailEase incidents. There is no second primary corpus,
and the corpus is not expanded to make evaluation look more rigorous.

Five scenario classes must be represented (NFR-29):

1. clear single-cause;
2. competing or ambiguous hypotheses;
3. multiple contributing failures;
4. sparse or unavailable evidence;
5. benign or transient condition.

An incident may satisfy more than one class, and a class may be satisfied by more than one incident.

### The audit

Before a milestone evaluation is reported, the corpus is audited against those five classes. The
audit asks three questions per class and nothing more:

- Is the class represented?
- Which authored incident represents it?
- Is the representation clear enough to evaluate against a golden scenario?

The audit produces one row per class recording the answer and, where a class is represented, the
incident that represents it.

Where a class is absent or too weakly represented to evaluate, the audit records **one bounded
corpus gap** naming the class and what a single representative incident would need to establish.
Closing a gap means authoring that one incident, not designing a scenario-authoring program and not
adding several incidents per class.

The audit must also identify the scenario that exercises the further-evidence cycle: an authored
scenario where the corpus naturally supports one, otherwise a controlled and credible fixture
variant of the §13 kind, in which the RCA Analyst states a further-evidence need and the Supervisor
authorizes the cycle. The demonstration is required either way; the absence of a naturally
occurring scenario selects the fixture variant and is not grounds to drop the requirement. Which
scenario or variant is used is pending corpus inspection (`decisions.md` D-006). Removing the
further-evidence capability or its demonstration would be an explicit later architecture revision,
never an evaluation-only cleanup.

This document defines the audit. It does not assert its result, because the result is a finding from
the corpus rather than a design decision.

---

## 5. Golden Scenario Model

One compact golden record accompanies each authored incident. It states what a correct investigation
must establish, not how the agents must reason or word it.

| Part | Content |
| --- | --- |
| 1. Scenario identity | Which authored incident this describes |
| 2. Scenario class or classes | Which of the five classes it exercises |
| 3. Expected cause | The correct cause, or the acceptable set where more than one answer is defensible |
| 4. Acceptable supporting alternatives | Alternatives a correct assessment may reasonably keep open, where relevant |
| 5. Required evidence | The evidence references or evidence groups a correct investigation must reach |
| 6. Contradicting or unavailable evidence | Material evidence that weakens a candidate, or that is deliberately absent |
| 7. Expected outcome shape | The acceptable terminal shape or shapes: complete, partial, or inconclusive |
| 8. Required behavior | Any limitation, discriminator, or recommendation the scenario specifically tests |

A golden record does not contain expected prose, a full expected brief, model reasoning, token
budgets, prompt-specific answers, per-agent expected messages, or an exact tool-call sequence. Two
different but valid evidence paths that establish the same required evidence are both correct.

---

## 6. Evaluation Layers

Four layers, and no more. Each is a distinct method, not a subject area.

| Layer | What it establishes | Result form |
| --- | --- | --- |
| 1. Deterministic conformance | Guarantees code can establish without judgment, including that the grounding gate refused what it should have | Pass, fail, or not exercised |
| 2. Scenario outcome | Whether each authored incident produced an appropriate assessment and brief against its golden record | Categorical, per dimension |
| 3. Comparative | Whether the selected complexity earns its place, against one fixed-script baseline and one lexical retrieval baseline | Named comparisons |
| 4. Measurement | Retrieval precision and recall, latency, model and capability calls, token use, approximate cost, and repeated-run stability | Recorded values, no threshold |

Layer 1 runs first and its results override later layers. Retrieval contributes to two of them: its
hard checks are deterministic and belong to layer 1, while its precision and recall are measured in
layer 4. Deterministic requirements are never converted into weighted scores, and layers are never
collapsed into a single number.

---

## 7. Deterministic Conformance

These behaviors are required, so each is pass or fail. None is an empirical performance target, and
none carries a threshold.

Two kinds of duplication are deliberately absent. Evaluation does not re-check the four grounding
checks one at a time, because the gate already performs them on every turn; it checks that the gate
did its job. And it does not repeat a deployed verification check from `runtime-and-deployment.md`,
whose results it reports (§3).

| Check | Confirms | Requirements |
| --- | --- | --- |
| Grounding-gate conformance | The gate ran on every delivered brief, and a brief that should have failed a check did fail it rather than being delivered or repaired | NFR-2 to NFR-5, NFR-35, FR-38, FR-62 |
| Read-only behavior | No prohibited write or unsupported operational action is reachable on any path, including an out-of-surface or mutating structured query | FR-75, FR-102, NFR-1, NFR-41 |
| Bounded termination | Every run terminates within its configured bounds, and no agent widened its own | FR-53, FR-54, FR-56, NFR-39 |
| Result vocabulary validity | Every capability result carries a legal execution-outcome and completeness pairing | NFR-7 |
| No fabricated observations | A failed, timed-out, unavailable, or rejected operation produced a limitation, never an observation | FR-68, FR-69, NFR-8 |
| Structured-query correctness | Normalized execution output matches the fixture golden result; owned as a deterministic test and aggregated here | NFR-43 |
| Retrieval floor and identifier survival | No evaluated incident retrieves none of its expected evidence, and designated exact identifiers are matched literally | NFR-32, NFR-33, FR-90 |
| Brief rendering fidelity | The delivered brief projects its assessment without loss; owned as a deterministic test over the projection path and aggregated here | FR-9, FR-38, FR-59, FR-60, FR-62, NFR-4, NFR-5 |
| Correction allowance | A turn spends at most one corrective model call, whether it went to a structurally unusable synthesis result or to a failed grounding check | FR-53, FR-54, NFR-10, NFR-39 |

A check that a given run did not exercise is reported as **not exercised** rather than as a pass.

Read-only behavior stays here despite being verified in the deployed environment as well, because
NFR-41 requires evaluation itself to establish it deterministically.

The correction allowance is countable from the trace. Corrective calls are emitted like any other
model call, so establishing that a turn made at most one is arithmetic over recorded events, and a
turn that made none passes. The rule it checks belongs to `workflow-design.md` §5.

Rendering fidelity and structured-query golden-result comparison are owned as deterministic tests
in `code-guidelines.md` ("Testing Expectations"); evaluation aggregates and reports their results
per §3 and does not reimplement them. Neither joins the gate's fixed set of four checks.

---

## 8. Scenario Outcome Evaluation

Each completed turn is evaluated against its golden record. Expectations differ by class.

**Clear single-cause.** The expected cause is leading; the required supporting evidence is present;
material contradicting evidence is disclosed; the brief does not manufacture unnecessary alternatives
(FR-59, FR-64).

**Ambiguous or competing hypotheses.** The expected cause remains among the meaningful candidates;
candidate ordering is supported by evidence rather than assertion; the useful discriminator is named;
unsupported certainty is avoided (FR-24, FR-60, FR-61).

**Multiple contributing failures.** The assessment recognizes that one cause does not explain all
material signals; contributing factors remain inside one authoritative assessment rather than
becoming competing conclusions; evidence attaches to the correct contributing factor (FR-65, FR-82).

**Sparse or unavailable evidence.** The result is honestly partial or inconclusive; missing evidence
is named; an unavailable source is not reported as an authoritative absence; no best guess is
presented as established; the next useful check is identified (FR-23, FR-40, FR-41, FR-62).

**Benign or transient condition.** The brief permits no immediate action or safe deferral where the
evidence supports it; history and generic caution do not force unnecessary intervention;
recommendations stay proportionate (FR-72).

### Categorical results

Scenario-quality dimensions are reported as one of:

- **Meets**
- **Partially meets**
- **Misses**
- **Not applicable**

There are no 0-100 scores, no weighted composites, and no per-scenario numeric grade. Every
*Partially meets* and every *Misses* carries a short named reason identifying what was wrong.

---

## 9. Model-Assisted Judge

One offline judge configuration exists. It runs after deterministic checks, over the completed brief
and assessment (NFR-25).

It scores only what deterministic checks cannot reach:

- usefulness;
- completeness;
- relevance;
- whether diagnosis and uncertainty are presented coherently;
- whether cited evidence appears to semantically support the claim it is attached to, where
  resolution alone cannot establish support (NFR-36, NFR-42);
- whether the stated causal ordering is coherent: a brief must not assert a cause occurring after
  the effect it explains, judged against the event times and observation windows the cited evidence
  carries (`data-and-evidence.md` defines those times).

The last two are the same kind of property. Both are judgments about meaning that no deterministic
check can reach, which is why they sit here rather than in §7.

It uses the same categorical scale as §8, and for each dimension returns one category, a short
rationale, and the specific brief section or claim that caused anything below *Meets*.

The judge is advisory. Deterministic results override it on whether a reference exists, whether a
query left the approved surface, whether a write was attempted, whether protocol permissions
differed, and whether a required field is absent.

The judge may use one of the already configured Azure OpenAI deployments; no separate deployment is
required for evaluation. Its exact deployment and prompt version are settled in `decisions.md` and
recorded on every run.

There is no judge ensemble, no majority voting, no judge debate, no multiple personas, no judge
confidence score, no judge service or database, and no judge anywhere in the live architecture.

---

## 10. Retrieval Evaluation

Retrieval cases derive from the authored incidents and their expected evidence. Each case carries the
retrieval question, the target collection where the case tests routing, the expected knowledge
references, the exact identifiers that must survive retrieval, and any available distractor
references. Cases are not multiplied into synthetic query variants.

### Measurements

Measured and recorded per case (NFR-31):

- precision;
- recall;
- whether at least one expected item was retrieved;
- exact-identifier success;
- collection-routing correctness (FR-92);
- whether the matched passage itself, rather than a document identifier, reached reasoning (FR-89);
- whether passages matching a designated exact identifier surface above their fused position after
  deterministic reranking (FR-90, FR-91).

Results are reported by query, by collection, and split between identifier-oriented and semantic
queries. They are not collapsed into one aggregate retrieval percentage.

### Hard checks

Three retrieval obligations are deterministic rather than measured. Two of them, the retrieval floor
and identifier survival, are checked in §7. The third is checked here, because it is a property of
how a brief cites rather than of what retrieval returned:

- retrieved knowledge is never cited as current operational proof (FR-67, FR-94).

### Lexical baseline

The single simpler baseline is **lexical-only retrieval**, run over the same cases as the selected
hybrid approach (NFR-34). The comparison tests whether hybrid retrieval earns its place.

There is no vector-only baseline, no fusion variants, no reranker comparison, no embedding-model
grid, no chunk-size sweep, and no retrieval ablation matrix. A targeted experiment is added later
only to diagnose a retrieval failure that actually occurred.

---

## 11. Tool, Structured-Query, and Protocol Evaluation

### Evidence-path behavior

Using traces and completed artifacts, check whether the investigation selected evidence sources
appropriate to the incident, avoided an identical universal tool sequence, let observations influence
later actions, preserved source failures as limitations, completed honestly when a noncritical source
failed, stopped within bounds, and retained successful results when a parallel action failed (FR-49
to FR-52, FR-57, FR-86, FR-87, NFR-37).

No golden tool call is required for every step. A different but valid evidence path is not marked
wrong merely because it differs from an authored trace; what is evaluated is the outcome and the
material evidence reached.

### Structured query

Structured-query behavior is judged by execution results, never by generated query text (NFR-43).
The comparison to fixture truth is implemented as deterministic tests (`code-guidelines.md`) and
aggregated here. For each case: define the approved schema surface, the natural-language question,
and the golden result set or count; execute the generated query through normal deterministic
validation; and compare normalized output against the golden result. Formatting, whitespace,
property order, and equivalent query syntax are not compared.

Also verified: an out-of-surface query is rejected before execution; a mutating query is rejected;
the result limit is enforced; a timeout produces a limitation rather than fabricated evidence; only
the Evidence Investigator can originate the path; and the RCA Analyst cannot reach it (FR-95 to
FR-102).

Enough cases to exercise a lookup or filter, one count aggregate, and one rejected query. Cases for
grouping, ordering, or non-count aggregates exist only if corpus inspection later promotes those
forms into the supported subset. No query benchmark is built.

### Protocol boundary

The one capability exposed through MCP is invoked once by each path and compared on normalized
result, evidence type, provenance, outcome and completeness, read-only permission, and admitted
evidence semantics. Only the recorded transport may differ (FR-104, NFR-44).

No protocol load testing, no evaluation of several MCP tools, and no certification harness.

---

## 12. Grounding, Provenance, and Recommendation Evaluation

### Grounding checks

Deterministic, and drawn from the semantics `data-and-evidence.md` defines rather than restated here.
Evaluation confirms that each ran and reports its result; what each inspects is that document's.

The four grounding checks the gate runs are verified by name: reference resolution,
unsupported-element rejection, recommendation-provenance presence, and required limitation
disclosure (NFR-2 to NFR-5, NFR-35, FR-38, FR-62).

Three further grounding properties are checked from completed artifacts rather than by the gate:

1. citations never cross investigation boundaries (NFR-12);
2. partial evidence stays labelled partial (NFR-7);
3. contradictory evidence stays represented (FR-63, NFR-6).

Whether retrieved knowledge stands as current operational proof is not re-checked here (FR-67).
Its structural case belongs to reference resolution, which a knowledge reference cannot pass in a
current-operational-support role, and gate conformance in §7 establishes that the gate performed it.
What survives a legal citation role is a question about meaning and belongs to the judge (§9).

Whether a cited passage semantically supports the element it is attached to is the judge's, not the
gate's. The gate resolves references; the judge assesses support. That division is why the judge's
assessment supplements resolution rather than replacing it, and why no separate citation-verifier
exists.

### Recommendations

Checked categorically (FR-34 to FR-38, NFR-40):

- Now, Soon, and Later horizons are present where applicable;
- immediate mitigation is distinct from longer-term prevention;
- a recommended mitigation states what should be observed to confirm it worked;
- recommendations connect to evidence or candidates;
- each names one permitted provenance category;
- no immediate action is permitted where the evidence supports that;
- no recommendation is executed, and none is described as something OpsPilot already performed.

Recommendation prose is not scored stylistically.

---

## 13. Degradation, Cancellation, and Failed Execution

These are demonstrated using existing scenarios with controlled source overrides, not by authoring
new incidents. Fault injection happens at the capability adapter boundary; there is no chaos-testing
platform.

Four controlled cases suffice. Each exercises a path the others do not:

| Case | What it must show |
| --- | --- |
| Source failure, run against a material and a nonmaterial source | The failure is visible and no observation is fabricated; a nonmaterial failure leaves the turn complete with the limitation disclosed, and a material one yields partial or inconclusive with the missing evidence named rather than a guess (NFR-38) |
| Engineer cancellation after evidence was admitted | A partial brief is returned where synthesis, delivery, and persistence remain possible (FR-46, FR-40) |
| Engineer cancellation before any evidence was admitted | The turn completes inconclusive with no brief synthesized, and no candidate cause or recommendation is asserted (FR-46, FR-41) |
| Bounded termination | The turn stops within bounds and reports its stop reason honestly (FR-53, FR-88, NFR-39) |

The two source-failure branches are one case because they exercise one path: a limitation is
recorded, nothing is fabricated, and the outcome follows materiality. The two cancellation branches
are two cases because they do not: one runs synthesis, the gate, and delivery, and the other skips
synthesis entirely. Both cancellation paths, the property that a lost or abandoned attempt persists
nothing, and commit-before-terminal ordering with its persistence-failure branches are owned as
deterministic tests (`code-guidelines.md`); this suite aggregates those results and adds only the
controlled source-override runs.

Separately, a failed execution must not be scored as a completed turn (`workflow-design.md`). Where
a trustworthy brief remains possible the turn completes with an outcome matching what its evidence
supports; where it does not, the attempt is recorded as a failed execution.

A brief that fails the grounding gate with the turn's correction allowance spent is one such case.
It is a failed execution, not a partial or inconclusive completed turn, and it is never scored as
scenario output. The evaluation records that the gate correctly refused delivery.

A first execution that fails must also leave no persisted investigation behind, and a completed turn
must exist only after its commit succeeded.

---

## 14. Fixed-Script Baseline

One deterministic baseline exists. It uses the same normalized incident input, the same evidence
capabilities, the same read-only permissions, the same execution bounds, the same corpus, and the
same assessment and brief contract as OpsPilot (NFR-45).

Its one material difference is that evidence checks run in a predetermined order rather than being
selected adaptively from what has already been observed. That isolates the value of adaptive routing
and nothing else. Each comparison uses a versioned predetermined evidence plan stored with its
evaluation fixture or golden scenario record, so the baseline is stable and comparable across runs.

The baseline reuses the same evidence and synthesis path wherever practical. It is not a second
application architecture, not a separate deployment, and not a second set of capability adapters.

**It runs on a subset, not the corpus.** The claim it supports is that adaptive routing beats a fixed
lookup order on at least one scenario, so the baseline runs on the smallest set that can show that:
the scenarios where the evidence path is genuinely contingent, which is where a fixed order has
something to miss. Running it across all seven would cost seven baseline executions to establish a
claim one scenario already carries. Which scenarios those are is settled in `decisions.md` with the
other scenario selections.

Within that subset, at least one authored incident must demonstrate one of the following within the
same bounds:

- adaptive routing reaches important evidence the fixed sequence misses;
- adaptive routing avoids work the fixed sequence performs uselessly;
- follow-up retrieval changes what the investigation examines;
- evidence weakens a hypothesis and redirects the investigation.

The comparison need not show adaptive investigation winning on every incident, and no overall
uplift percentage is computed. Where the fixed script matches or beats OpsPilot on a scenario, that
is reported as the result it is.

---

## 15. Repeatability and Before/After Comparison

### Full pass

A milestone evaluation runs each of the seven authored incidents once.

### Repeatability subset

Repeated runs are required but deliberately small (NFR-46). The subset is the smallest that covers
three behaviors:

- one scenario that reaches a supported conclusion;
- one ambiguous or competing-hypothesis scenario;
- one partial or inconclusive scenario.

Each selected scenario is run **one additional time**. That yields repeated observations without a
stochastic study.

There is no requirement for five or ten runs per scenario, no repeated runs across all seven
incidents, no confidence intervals, no significance testing, no temperature sweep, no prompt grid,
and no model-version grid. Further repetitions happen only to investigate a specific instability the
baseline actually revealed.

### Stability observations

For the repeated subset, record whether the leading candidate stayed the same, whether the outcome
shape stayed the same, whether material evidence references stayed substantially consistent, whether
recommendation direction changed materially, and whether latency, calls, token use, or cost changed
notably.

These are reported as observations. No universal stability score is computed, and no pre-baseline
stability threshold exists.

### Before and after

When a prompt or model changes, the same named evaluation cases run before and after, with corpus and
configuration identity preserved (NFR-48). The report names changed outcomes and named regressions
rather than relying on a single aggregate value.

---

## 16. Latency, Usage, and Cost Observations

For each evaluated completed turn, record end-to-end latency, major-step latency where the trace
already carries it, model call count, capability call count across tools, retrieval, structured
query, and the protocol path, input and output token use, approximate model cost, the outcome shape,
and the categorical quality result (NFR-18, NFR-46).

These are reported next to correctness, not in a separate performance appendix (NFR-47).

They are observations. There are no latency objectives, no cost budgets acting as gates, no
percentile dashboards, no capacity model, no load or throughput testing, and no concurrency
benchmark. Cold starts are not a metric, target, or comparison dimension; they may be noted
narratively where they occur. NFR-54 makes ordinary downtime something the environment tolerates
rather than something engineered around (`runtime-and-deployment.md`).

---

## 17. Evaluation Cadence

Two cadences.

**Change-time.** Runs the deterministic conformance checks relevant to the change, one fixed
compact change-time scenario subset end to end, retrieval checks where retrieval changed, and the
advisory judge over that subset's completed outputs. This signal informs and does not block merge
(NFR-49). The full seven-scenario suite does not run on every small change unless doing so is
already negligible.

Where the change is to a prompt or a model, the same named cases run on both sides of it with corpus
and configuration identity preserved (NFR-48, §15). That is this cadence with case identity held
constant, not a separate one.

**Milestone.** Runs all seven authored incidents once, together with deterministic checks, retrieval
measurements against the lexical baseline, the fixed-script comparison on its subset,
structured-query checks, protocol parity, the repeatability subset, and efficiency observations.
This is what produces a reportable result.

These two are not collapsed because they answer different questions. Change-time asks whether a
change broke something; milestone asks whether the system works. One cadence would either run seven
scenarios on every small change or report headline results from the change-time scenario subset.

The change-time scenario subset and the milestone scenario identifiers are settled in
`decisions.md` once chosen.

---

## 18. Reporting

One evaluation run produces one report, carrying what a reader needs to judge whether the system
works and whether a change helped:

1. Run identity and configuration
2. Scenario results by class, with every failure and regression named
3. Deterministic conformance, including the structured-query and protocol checks
4. Comparisons: retrieval against the lexical baseline, and the fixed-script comparison
5. Measurements: retrieval precision and recall, latency, calls, tokens, cost, and repeated-run
   stability
6. Conclusion and next corrective actions

Sections 2 through 5 are the four evaluation layers of §6, in the order a reader needs them.

The report names every individual scenario failure (NFR-30). No overall percentage, composite score,
or executive summary figure is permitted to stand in for that detail.

There is no evaluation dashboard, reporting service, warehouse, evaluation database, or metrics
pipeline. The report and its per-scenario artifacts are files or linked artifacts belonging to the
run.

### Run identity

A run retains enough metadata to be compared with another: run identity and timestamp, source
revision or build identity, corpus version or digest, the scenario set, the application configuration
relevant to evaluation, model deployment names or versions, prompt or contract versions,
execution-bound configuration, judge configuration, and per-scenario artifact references.

No physical schema or database key is defined here, and hidden reasoning is never persisted.

---

## 19. Target-Setting Policy

This document defines no numeric target for diagnosis accuracy, quality, groundedness, usefulness,
completeness, retrieval precision or recall, latency, token use, call counts, cost, candidate
stability, or adaptive improvement. Before a measured baseline exists, any such number would be
invented rather than evidence-based (NFR-26, NFR-27).

The absence of thresholds is not the absence of measurement. Every value listed in §10 and §16 is
recorded and reported from the first run onward.

Two kinds of check remain permanently distinct. The deterministic conformance checks in §7 are pass
or fail because the behavior itself is required, and they are not performance targets. Everything in
§8 through §16 that concerns quality or efficiency is measured and reported without an initial pass
threshold.

After the first fixed-script and early OpsPilot baseline runs:

- preserve the observed baseline as recorded;
- name the failures it exposed;
- identify only the smallest set of demonstration targets that would be genuinely useful;
- add those targets through an explicit later revision of this document, each with a stated reason
  why it suits a seven-incident corpus;
- never let a demonstration target become a service-level commitment (NFR-28);
- never let an aggregate figure conceal a named scenario failure (NFR-30).

This document therefore contains no placeholder threshold and no instruction for someone else to
invent one.

---

## 20. Requirement Traceability

| Evaluation area | Principal requirements |
| --- | --- |
| Scenario classes and reporting | NFR-25 to NFR-30 |
| Brief correctness expectations | FR-9 to FR-41 |
| Investigation and evidence behavior | FR-49 to FR-69, NFR-37 to NFR-42 |
| Agentic capability demonstrations | FR-77 to FR-88 |
| Retrieval measurement and baseline | FR-89 to FR-94, NFR-31 to NFR-34 |
| Structured query | FR-95 to FR-102, NFR-43 |
| Tool boundary and protocol parity | FR-103, FR-104, NFR-44 |
| Grounding and provenance | NFR-2 to NFR-6, NFR-35, NFR-36 |
| Fixed-script baseline | NFR-45 |
| Repeatability, efficiency, and comparison | NFR-46 to NFR-48 |
| Advisory change-time signal | NFR-49 |
| Completed artifacts and traces consumed | NFR-14, NFR-18, NFR-22, NFR-55, NFR-58 |
| Read-only boundary | FR-75, FR-102, NFR-1 |
