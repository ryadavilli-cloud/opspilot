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
| D-003 Retrieval design | Accepted |
| D-004 MCP exposure | Accepted |
| D-005 Offline judge | Accepted |
| D-006 Evaluation scenario selections | Accepted |
| D-007 Normalized incident context | Accepted |
| D-008 Reference encoding | Accepted |
| D-009 Evaluation artifact storage | Accepted |
| D-010 Analysis-to-gathering return | Accepted |
| D-011 Nearest-history baseline | Accepted |
| D-012 Corpus identity on a run | Accepted |
| D-013 The analysis return on the record | Accepted |

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
serves every runtime model task; the offline judge's own model is covered by D-005, and no
routing exists between the two.

### D-003 Retrieval design

**Decision.** One retriever over the categorized Cosmos knowledge container: embed the question
with the embedding deployment; vector search over the collection the capability names; a lexical
term-overlap pass over the same category-filtered candidates; reciprocal-rank fusion of the two
ranked lists; stable promotion of passages whose extracted identifiers match identifier-like terms
in the question; truncation to a small passage budget. Passages carry text and reference. No model
reranker. Which identifiers a question matched is not recorded on the passage or in the completed
record: promotion is deterministic, so the answer is re-derivable from the passage and the question
it was retrieved for, and a stored copy would be a second answer free to disagree with the one the
retriever computes.

What a retrieval unit is, corpus preparation decides, and it decides by what the capability
searching will be asking. A runbook and an architecture note are indexed a section at a time,
because how something is handled is answered by the part that handles it and the rest of the
document is not the answer. A past incident is indexed whole, because whether this has happened
before is a question about an incident, and its cause, its impact and what settled it are one
account rather than alternatives to each other. Ranking then has one path over whatever preparation
produced, and nothing regroups or re-shapes results afterwards.

**Why.** Vector search carries meaning; the lexical pass carries operational tokens and exact
identifiers; reciprocal-rank fusion is a simple way to combine
differently-scaled lexical and vector rankings without score calibration; deterministic promotion is the smallest mechanism
that makes an exact service name, error code, or deploy id trustworthy near the passage cutoff. The
identifiers on the passage side already exist from corpus preparation; the query-side match is a
small deterministic helper and needs no record of its own.

The unit differs by collection because splitting a write-up puts its parts in competition for the
same result budget: the most quotable incident occupies slots the incidents it should be weighed
against would have taken, and a budget of five stops meaning five precedents. What comes back is
then whichever parts echoed the question, as likely an impact and a timeline as a cause and a
resolution, so the one thing a precedent is retrieved to say can be the thing left behind. Keeping
the write-up whole removes both problems and the machinery that would otherwise work around them.

**Cost.** The lexical pass rescans the filtered candidates on every query, acceptable at this corpus
size. The passage budget is an engineering limit, not a tuned value. A past incident brings its
whole text to a prompt, which is more than a section: that is watched during hosted validation
rather than assumed affordable, and if it bites the lever is a smaller budget of precedents rather
than a return to fragments. Identifier extraction is per unit, so a deploy id named anywhere in a
write-up promotes the write-up rather than one part of it, which is the coarser behavior and the
honest one for a unit that is the whole incident.

### D-004 MCP exposure

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

**Decision.** inc-005 is the fast change-time scenario. inc-004 is the ambiguous case, and is
authored to give the analysis-to-gathering return an opportunity to fire rather than to produce it
on demand: whether any given run returns stays the model's to decide. inc-006 is the correct-partial case and carries the
adaptive-versus-fixed-path comparison. inc-007 is the retrieval-influence controlled comparison. The
nearest-history baseline (D-011) runs on inc-004 and inc-007 and nowhere else.

inc-006 carries adaptive value on one condition, which the corpus must satisfy: its second
contributor lives on a target that is discoverable only through service-dependency lookup, named
neither by the incident, nor by the correlated alerts, nor by the alerting service's logs, nor by
anything else the fixed path reaches before it. Whether the analysis return fires on any given run
stays the model's to decide and is not forced.

**Why.** inc-004 carries an authored red herring and an externally unobservable third party, so a
first pass cannot close it. inc-006 is the only scenario where partial is correct rather than a
shortfall. inc-007's match is reached through a postmortem's recurrence signature rather than
operational evidence, so knowledge changes its path.

inc-006 is where adaptive value can be shown structurally rather than as a matter of ordering. The
fixed path is a predetermined sequence that ends at dependencies, so a target first learned there
can never be queried: the claim becomes that the fixed path cannot formulate the necessary query at
all, which no reordering of the same script would rescue. A contributor the fixed path can reach by
running its own steps proves only that one order was worse than another.

**Cost.** RetailEase carries a service that exists so that one contributor can sit somewhere the
alerting service's own telemetry does not reach, and the topology, its metrics and logs, the
architecture documents describing the graph, and the authored expectation all have to keep saying
the same thing about it. The condition is a property of the data rather than of any prose, so it is
held by tests over the incident record, the storm, and the alerting service's logs, metrics, and
deploys; without them a later edit could hand the target over early and nothing would notice. The
storm is kept off the worker by the scenario naming it as watched by no alert rule, which is
truthful and is also a second thing to keep true. What this record selects inc-006 for is still
measured rather than assumed: the comparison has to be run for the claim to hold.

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
partitioned by `run_id`, in the shape `evaluation.md` states: the configuration identity, which
carries the judge's and the corpus the run retrieved from, per-scenario results with deterministic
checks and judge categories in separate fields, and the comparisons. The application identity holds
read on that container and the principal running evaluation holds write, so the application reads
kept runs and never writes one.
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
rather than a formatter at its end. One return is enough for the scenario authored to offer one (inc-004),
and a second has no scenario, adds no concept, and turns a bounded edge into a loop. An ordinary
field on the proposal is smaller than a dedicated contract.

**Cost.** A question that a first return cannot close remains an unknown; there is no second
return.
### D-011 Nearest-history baseline

**Decision.** Evaluation reaches a conclusion the cheap way and reports it beside the
investigation's: a query derived from the incident, one search of past incidents, the top write-up
returned, and that write-up's recorded cause and resolution taken directly as the answer. It makes
no model call and holds nothing constant, because it runs no investigation. It runs on inc-004 and
inc-007 and nowhere else.

**Why.** The other two comparisons hold OpsPilot against itself, so neither answers the reader who
would not have built OpsPilot at all: the nearest past incident already carries a cause and a
resolution, and reasoning over current evidence has to be worth more than copying them. Keeping the
baseline thoughtless is what makes it the alternative anyone actually reaches for; one that weighed
a precedent against current evidence would be a second investigation, and beating that would say
nothing about whether retrieval alone suffices. Two scenarios, because the shortcut fails in two
ways and only one of them looks like failure: on the ambiguous incident it should land confidently
on the wrong cause, and on the recurrence it should land on the right one having verified nothing.

**Cost.** Two more arms in the evaluation runner. The baseline's value rests on the history being
authored to hold a convincing near-match for the ambiguous incident; where the corpus does not
supply one, the comparison shows nothing and is better not run than run and read as a pass.

### D-012 Corpus identity on a run

**Decision.** One deterministic fingerprint over the retrieval-relevant content of the prepared
corpus and the identity of the embedding that vectorized it, carried on the completed investigation
and in a kept evaluation run's configuration identity. Preparing the same corpus twice produces the
same value, and a change to passage text, metadata, or embedding identity changes it. It lands
before the corpus changes. Records written before it exists read as not recorded, which is a
different claim from a mismatch.

**Why.** Retrieval behavior moves with the corpus and needs no model or prompt change to do it, so
two records from either side of a corpus edit carry identical version identity and are not
comparable. Deployment and prompt versions already travel with a record for exactly this reason;
the corpus was the one input that could change underneath a comparison and leave no trace.

**Cost.** One field in two places, and a constraint on corpus preparation: anything that varies
between two preparations of the same corpus, such as a timestamp or a generated id, cannot
contribute to it. It says that two runs are not comparable, never why, and reading the difference
is still a matter of looking at what changed.

### D-013 The analysis return on the record

**Decision.** The completed investigation records whether the analysis-to-gathering return was
taken. One boolean. The unresolved question that routed it and the evidence kind naming what could
answer it are not persisted beside it.

**Why.** The return is what makes the RCA Analyst part of the investigation rather than a formatter
at its end, and R-17 asks that a run be understandable afterwards from its record, not only while
it is on screen. Without it a run that returned and one that never did persist identically. The
question is left out because the analyst already states the same matter in the assessment's
unknowns (D-010), and the field the Supervisor routes on is a proposal, which the record does not
take.

**Cost.** A reader who wants the question reads the unknowns and connects it themselves, and where
the analyst worded the two differently that connection is theirs to make. The boolean says a return
happened, never what it recovered.
