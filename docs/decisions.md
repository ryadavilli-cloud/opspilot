# OpsPilot Decisions

**Which concrete choices were made where the design left more than one reasonable answer, and
which materially constrain later work?**

This is the current decision set, not a history. A record exists only where a real choice was made
and later implementation is constrained by it. Routine implementation detail is not recorded here.
Retired records keep an identifier and one line so the number is never reused.

| Decision | Status |
| --- | --- |
| D-001 Orchestration | Accepted |
| D-002 Model routing | Retired |
| D-003 Retrieval realization | Accepted |
| D-004 MCP realization | Accepted |
| D-005 Offline judge | Accepted |
| D-006 Evaluation scenario selections | Accepted |
| D-007 Normalized incident context | Accepted |
| D-008 Reference encoding | Accepted |
| D-009 Evaluation artifact storage | Accepted |
| D-010 Analysis-to-gathering return | Accepted |

---

### D-001 Orchestration

**Decision.** The investigation runs as one small compiled in-process graph over typed
investigation state, compiled without a checkpointer. Nodes are ordinary functions: set objective,
gather with bounded continuation, synthesize, ground with one correction, persist, deliver, and one
conditional return from synthesis to gathering. No durable execution, replay, interrupt, pause or
resume, or framework agent abstraction is used.

**Why.** A short node sequence with conditional continuation and one back-edge is exactly the
shape a graph declares rather than assembles, and the three-role orchestration and adaptive flow
become visible as a graph. Investigation state stays typed and owned by application code.

**Cost.** Continuation and bounds are application code with direct tests; the runtime enforces
neither. A dependency and its state model sit in the execution path.

### D-002 Model routing

Retired. No requirement mandates routing between models inside the runtime. One chat deployment
serves every runtime model task; the offline judge's own model is D-005's business, and no
routing exists between the two.

### D-003 Retrieval realization

**Decision.** One retriever over the categorized Cosmos knowledge container: embed the question
with the embedding deployment; vector search over the collection the capability names; a lexical
term-overlap pass over the same category-filtered candidates;
reciprocal-rank fusion of the two ranked lists; stable promotion of passages whose extracted
identifiers match identifier-like terms in the question; truncation to a small passage budget.
Passages carry text and reference. No model reranker.

**Why.** Vector search carries meaning; the lexical pass carries operational tokens and exact
identifiers; reciprocal-rank fusion combines two differently-scaled lists without calibration and
is the clearest course-aligned hybrid technique; deterministic promotion is the smallest mechanism
that makes an exact service name, error code, or deploy id trustworthy near the passage cutoff. The
identifiers on the passage side already exist from corpus preparation; the query-side match is a
small deterministic helper and needs no record of its own.

**Cost.** The lexical pass rescans the filtered candidates on every query, acceptable at this corpus
size. The passage budget is an engineering limit, not a tuned value.

### D-004 MCP realization

**Decision.** The deployments capability is additionally exposed through an in-process MCP server
built on the official Python `mcp` SDK over stdio, dispatching to the same registered
`get_deployments` implementation. Only transport differs, and it is recorded on the activity event.

**Why.** Among useful read-only capabilities it has the smallest argument surface (three required
arguments, no optional filters), a flat five-field result, one direct-versus-MCP parity assertion,
no MCP-specific normalization, and no new evidence type. "Did anything change before the incident"
is a genuinely useful investigative question. The protocol is the demonstration, not the tool. The
SDK is already the project's dependency and already runs an in-process stdio server; nothing new is
introduced.

**Cost.** One capability only; a reviewer wanting to see a second tool over MCP does not get one.

### D-005 Offline judge

**Decision.** One offline judge and one authored rubric, returning a category for each of:
usefulness and coherence, appropriate uncertainty, explanation in context, recommendation fit.
Advisory, run after deterministic checks, never combined into one number, never a runtime
authority. The judge runs on its own model, Claude Opus 5 hosted in Microsoft Foundry, pinned
to a concrete model version, with adaptive thinking at a fixed medium effort; it does not use the
runtime's chat deployment, and nothing in a live investigation can reach it.

**Why.** A judge scoring the briefs the runtime model produced should not be the runtime model:
one model on both sides correlates the judge's blind spots with the system's and lets it prefer
its own phrasing. A different model family breaks that correlation, and the strongest available
model in that family is the right one to spend on, because the judge is asked for exactly the
semantic reading the deterministic checks deliberately cannot make. The version is pinned because
a judge is a measuring instrument, and the model changing underneath it breaks the history
silently.

**Cost.** A second model dependency: its own endpoint, deployment, and access to configure, and a
judge that cannot run where only the runtime deployment exists. Judge token figures are not
comparable with runtime ones, because the tokenizers differ. Judge output still varies with the
model; that is why it is advisory and reported beside the deterministic results.

### D-006 Evaluation scenario selections

**Decision.** inc-005 is the fast change-time scenario. inc-004 is the analysis-to-gathering return
demonstration and the ambiguous case. inc-006 is the correct-partial case. inc-007 is the
retrieval-influence controlled comparison. The adaptive-versus-fixed-path scenario is not
preselected: it is the authored incident on which the controlled comparison shows the adaptive path
reaching a meaningfully better result. inc-004 is the likely candidate because its evidence path is
contingent; it is a candidate until measured.

**Why.** inc-004 carries an authored red herring and an externally unobservable third party, so a
first pass cannot close it. inc-006 is the only scenario where partial is correct rather than a
shortfall. inc-007's match is reached through a postmortem's recurrence signature rather than
operational evidence, so knowledge changes its path.

### D-007 Normalized incident context

**Decision.** Four fields: `incident_id`, `scope` (the affected service or component where the
incident names one, else absent), `symptom` (the incident's short description), and `time_anchor`
(the incident's opened time, not asserted as onset). The answer-bearing and ticket-workflow fields
of the raw record are deliberately excluded.

**Why.** An investigation must reach its own conclusion, never receive it as intake, and nothing
downstream reads the ticket-workflow fields.

### D-008 Reference encoding

**Decision.** Prefixed reference strings, one parser, one resolver; the prefix decides whether a
reference is evidence or knowledge. Evidence: `logs:`, `metrics:`, `deploys:`, `deps:`, `alert:`,
`incident:`, `absence:`, `query:`. Knowledge: `runbook:`, `architecture:`, `postmortem:`. The
segment forms are stated once in `data-and-evidence.md`.

**Why.** It is the simplest way a citation resolves deterministically and the simplest way to
decide by inspection whether a reference may stand as current operational support.

### D-009 Evaluation artifact storage

**Decision.** A kept evaluation run is persisted as one document in its own Cosmos container,
partitioned by `run_id`, in the shape `evaluation.md` states: the configuration identity including
the judge's, per-scenario results with deterministic checks and judge categories in separate
fields, and both comparisons. The application identity holds read on that container and the
principal running evaluation holds write, so the application reads kept runs and never writes one.
A saved run is never edited or deleted, and a second save under one `run_id` is refused. The
report document the runner writes beside it is a convention.

**Why.** Kept runs are what the read-only view lists and reads, so where they live, how they are
keyed, what shape they take, and who may write them constrain the view, the runner, and the role
assignments alike. Holding the write grant away from the application is what keeps evaluation
offline once the view exists: no request can write a run.

**Cost.** A fourth container, a grant to a second principal, and a document shape the runner and
the view both depend on. Keeping a run is opt-in, which is a discipline on whoever runs evaluation.

### D-010 Analysis-to-gathering return

**Decision.** The RCA Analyst's assessment proposal carries one optional field,
`unresolved_question`, naming what remains unanswered and what evidence kind could answer it. It
is routing metadata; the same matter is stated in the assessment's `unknowns`. The Supervisor
authorizes a return to gathering only when no return has yet occurred, a registered capability
supplies that evidence kind, and the bounds have room. When the return is unavailable or already
spent, the Supervisor does not follow the edge and does not edit the assessment. At most one return
per investigation.

**Why.** Analysis-to-gathering feedback is what makes the RCA Analyst part of the investigation
rather than a formatter at its end. One return is enough for the authored demonstration (inc-004),
and a second has no scenario, adds no concept, and turns a bounded edge into a loop. An ordinary
field on the proposal is smaller than a dedicated contract.

**Cost.** A question that a first return cannot close remains an unknown; there is no second
return.
