# OpsPilot - System Design

**Which components realize the architecture, what does each own, and how do they interact?**

## 1. Purpose and Document Boundaries

This document is the component-level high-level design. It owns the component and subcomponent
catalogue, each component's responsibility and authority, the conceptual interfaces between them,
the investigation and turn model, conceptual external operations, persistence responsibilities, the
internal design of the Evidence Access Layer, the shared model-access and telemetry seams, and the
technology responsibility map.

`requirements.md` governs required behavior and `architecture.md` fixes the top-level shape. This
document realizes them; it does not reinterpret either.

Detail belongs to its owner. Stages, routing rules, adaptive-cycle behavior, continuation logic,
stop points, retries, timeouts, and terminal transitions belong to
`workflow-design.md`. Information categories, tool-result vocabulary, evidence and operation
identities, citation rules, candidate and assessment fields, the brief contract, and handoff
semantics belong to `data-and-evidence.md`. Processes, network topology, concrete Azure resources,
API and activity-stream transport, physical persistence layout, identity realization,
configuration, telemetry products, deployment, and smoke tests belong to
`runtime-and-deployment.md`. Corpus, ground truth, metrics, judges, baselines, and ablations belong
to `evaluation.md`. Final settled technology choices belong to `decisions.md`, implementation and
merge enforcement to `code-guidelines.md`, and build state to `status.md`.

---

## 2. Design Constraints Inherited from Requirements and Architecture

These constraints bind every decision below.

- **Six top-level runtime boundaries, no more.** Three are agent roles (Supervisor, Evidence
  Investigator, RCA Analyst); three are not (Engineer Interaction Interface, Evidence Access Layer,
  Investigation Record). Nothing else is promoted to a runtime authority (FR-77 to FR-79, FR-83).
- **One coherent application.** Agent roles are logical responsibilities inside one deployed
  application, not independently deployed services.
- **Supervisor-mediated coordination.** Every assignment, result, and continuation decision passes
  through the Supervisor; there is no peer-to-peer path between agents (FR-80).
- **Read-only operational access on every path,** including through the protocol boundary (FR-75,
  FR-102, NFR-1).
- **Deterministic bounds.** Budgets are owned by code, and no agent may widen its own (FR-53,
  FR-56, NFR-10).
- **Completed-artifact persistence only.** Completed turns, their briefs, and the evidence needed to
  resolve citations persist. In-flight turn state is ephemeral and is not checkpointed, replayed, or
  recovered (NFR-55, NFR-57).
- **No review, approval, publication, finalization, or recovery machinery** exists anywhere in the
  component model.
- **Observability and evaluation are non-authoritative.** Neither is a component, and neither may
  route, gate, delay, or decide anything in a live turn (FR-83, NFR-14).

---

## 3. Component Model

```text
                                   Engineer
                                      │
                        intake ·      │      brief · handoff · activity
                        follow-up     ▼
                  ┌───────────────────────────────────┐
                  │   Engineer Interaction Interface   │  deterministic
                  └───────────────────┬───────────────┘
           normalized incident context │ ▲ delivered brief · activity events
           classified follow-up        ▼ │
     ┌─────────────────────────────────────────────────────────────────┐
     │                    Supervisor                          [agent]   │
     │  turn objective · assignment · bounds · continuation ·           │
     │  grounding gate (deterministic) · terminal turn shape            │
     └──┬─────────────────┬───────────────▲──────────────┬───────▲─────┘
 evidence │       synthesis │    assessment │   completed  │ retained │
 assignment│      assignment │ further-evid │      turn    │  context │
           ▼                 ▼         need │              ▼          │
 ┌───────────────────┐ ┌──────────────────────────┐ ┌──────────────────────┐
 │ Evidence          │ │   RCA Analyst    [agent]  │ │ Investigation Record │
 │ Investigator      │ │ sole synthesis authority  │ │ passive · completed  │
 │           [agent] │ │                           │ │ artifacts only       │
 └─────────┬─────────┘ └──────────────────────────┘ └───────────┬──────────┘
  evidence │ access requests                                     │ read
           ▼                                                     ▼
 ┌────────────────────────────────────────────────┐        Evaluation
 │            Evidence Access Layer                │     (offline reader,
 │  dispatch · operational tools · retrieval ·     │      outside the live
 │  governed structured query · MCP adapter ·      │      authority chain)
 │  normalization and evidence admission           │
 └──────────────────────┬─────────────────────────┘
                        │ read-only
 ═══════════════════════│═══════════ OpsPilot boundary ═════════════════════
                        ▼
 ┌────────────────────────────────────────────────┐
 │  RetailEase: incidents · logs · metrics ·       │
 │  deployments · topology · structured tables ·   │
 │  runbooks · postmortems · prior incidents       │
 └────────────────────────────────────────────────┘

 Seams, not components: the model-access seam is reached by all three agents;
 the telemetry seam is emitted through by all six boundaries.
```

| Component | Kind | Owns in one line | May call |
| --- | --- | --- | --- |
| Engineer Interaction Interface | Non-agent boundary | Engineer interaction, incident selection, follow-up classification, presentation | Supervisor |
| Supervisor | Agent | Turn objective, orchestration, bounds, continuation, grounding gate, terminal shape | Evidence Investigator, RCA Analyst, Investigation Record, Engineer Interaction Interface, model seam |
| Evidence Investigator | Agent | Investigative questions, adaptive source selection, working hypotheses | Evidence Access Layer, model seam |
| Evidence Access Layer | Deterministic boundary | Governed read-only access mechanics, normalization, evidence admission | RetailEase sources |
| RCA Analyst | Agent | The structured assessment and the brief's analytical content | Model seam |
| Investigation Record | Passive persistence | Completed investigation artifacts | Nothing |

---

## 4. Component Responsibilities and Authority

### 4.1 Engineer Interaction Interface

**Purpose.** The engineer-facing boundary. It is not an agent and holds no investigative authority.
It reaches no model; every decision it makes is deterministic code.

**Owns.** Predefined-incident intake; classification of later engineer input; presentation of live
activity, briefs, and handoff summaries.

**Consumes.** Engineer input; the current investigation summary and retained completed-turn state;
activity events; delivered briefs; handoff summaries.

**Produces.** Normalized incident context; classified follow-up; turn-start request; presentation
views.

**May call.** The Supervisor. It reaches no other component, and no model use is permitted to it.

**May decide.** How to classify one engineer message into a supported interaction kind.

**What stays deterministic.** The normalized incident context is resolved from the selected
incident by deterministic code. Classification of later engineer input is established by the request
shape or explicit interface action the engineer used, never by analyzing prose and never by a model
call; an ambiguous ordinary follow-up defaults to a question.

**Must not.** Gather evidence; call operational tools; form a candidate cause; decide investigation
readiness; synthesize the brief; admit evidence; own persisted investigation state.

**State responsibility.** None persisted. It holds only presentation state for the live session.

**Requirements.** FR-1, FR-3, FR-6, FR-43, FR-106 to FR-119, NFR-53.

Later engineer input is classified into exactly two interaction kinds: question and
handoff-summary request. Detailed classification and routing behavior belongs to
`workflow-design.md`.

The engineer-facing surface is one screen: intake and follow-up control, a compact live activity
feed, the delivered brief as the dominant element, and one expandable details area for deeper
evidence and technical detail. That expandable area is the whole realization of the developer view
FR-118 permits; no separate diagnostics application exists.

### 4.2 Supervisor

**Purpose.** The orchestration agent, and the only component that sequences work.

**Owns.** Interpreting the current turn objective; assigning work; controlling agent sequencing;
enforcing deterministic execution budgets; deciding whether bounded continuation is permitted;
reading retained investigation context; deciding the terminal turn shape; applying the deterministic
grounding gate; coordinating delivery.

**Consumes.** Normalized incident context; classified follow-up requests; retained investigation
state; Evidence Investigator results; RCA Analyst assessments and further-evidence needs; stop
requests; deterministic budget state.

**Produces.** Evidence-investigation assignments; synthesis assignments; bounded-continuation
decisions; the terminal outcome; the admitted delivered brief; completed-turn write requests;
answers and handoff summaries derived from retained state.

**May call.** Evidence Investigator; RCA Analyst; Investigation Record; the Engineer Interaction
Interface through a response or presentation boundary; the model-access seam where model-assisted
interpretation is required.

**May decide.** The turn objective; whether another bounded evidence cycle is permitted within the
existing budget; when gathering stops; the terminal turn shape that the turn state supports; whether
a proposed brief passes the grounding gate.

**Must not.** Call operational tools, retrieval, or structured query directly; create evidence;
author candidate causes or brief narrative; override a failed grounding check; widen a budget; edit
a completed turn.

**State responsibility.** Owns ephemeral turn working state during a turn; authorizes the
completed-turn write at its end.

**Requirements.** FR-5, FR-6, FR-42, FR-44, FR-49 to FR-56, FR-71, FR-74, FR-77, FR-80, FR-85,
FR-88, NFR-2 to NFR-5, NFR-10.

#### The grounding gate

The grounding gate is deterministic code inside the Supervisor boundary. It is not an agent, a
service, a separate component, an evaluation judge, or a review stage. It executes exactly four
grounding checks before a brief may be delivered: reference resolution, unsupported-element
rejection, recommendation-provenance presence, and required limitation disclosure. Each is a test
over structure; no model call runs inside the gate, and no fifth check exists. What each check
inspects is defined in `data-and-evidence.md` ("Claims, Citations, and Grounding"). When the gate
runs, the correction allowance it draws on, and what follows a persistent failure belong to
`workflow-design.md` ("Grounding Gate and Outcome Validation").

None of the four asks whether cited evidence semantically supports what it is attached to; that
judgment is entailment, cannot be computed, and belongs to the offline judge in `evaluation.md`,
which never gates delivery. Contract validity is a prerequisite settled before the gate runs, not
one of its checks. The gate validates that the proposed brief faithfully and safely represents the
outcome the turn state supports; the Supervisor, not the gate, decides that outcome shape.

#### Follow-up answers and handoff summaries

A follow-up question is answered by the Supervisor from retained completed-turn state, as one named
model task on the primary deployment (§10.2). The task's input is the question and retained state,
and its answer may cite only retained evidence and knowledge references. Deterministic code applies
a follow-up answer validation before delivery: every cited reference must resolve within the
retained investigation state, and the answer may introduce no new evidence, no new candidate cause,
no new investigation conclusion, and no recommendation presented as coming from retrieved guidance.
This validation is not a grounding check; the four-check gate remains exclusive to completed-turn
delivery. Where retained state cannot answer the question, the answer states that plainly and
recommends a new investigative turn where appropriate. An answer is not a completed turn and is not
persisted as one.

A handoff summary is a deterministic projection of retained structured state: the latest objective
and outcome, what happened, candidate causes with their support labels, key supporting and
contradicting evidence, limitations, and the Now, Soon, and Later recommendations, carrying only
references already present in retained state. Producing it calls no model, creates no new synthesis
or evidence, and changes no candidate ordering. Its content semantics belong to
`data-and-evidence.md` ("Handoff Summary").

### 4.3 Evidence Investigator

**Purpose.** The evidence-gathering agent, and the only agent that reaches the Evidence Access
Layer.

**Owns.** Choosing the next useful investigative question; adapting source selection to what has
already been observed; working hypotheses that guide gathering and are never authoritative;
selecting approved Evidence Access capabilities; requesting independent evidence actions together
where appropriate.

**Consumes.** A bounded Supervisor assignment; normalized incident context; relevant prior
completed-turn context; existing evidence and retrieved-knowledge references; remaining budget
information; approved capability descriptions.

**Produces.** Evidence-access requests; evidence-gathering results; unresolved questions; explicit
source limitations; a recommendation on whether another useful evidence action remains.

**May call.** The Evidence Access Layer and the model-access seam.

**May decide.** Which permitted capability to use next and why; when no further useful action
remains within the current assignment.

**Must not.** Call the RCA Analyst or the Engineer Interaction Interface; write to the Investigation
Record; fabricate evidence; create an authoritative candidate cause; produce the brief; alter
budgets; treat retrieved knowledge as current proof.

**State responsibility.** Ephemeral only. Its working hypotheses and in-progress requests do not
persist.

**Requirements.** FR-49 to FR-52, FR-57, FR-61, FR-62, FR-68, FR-69, FR-78, FR-84, FR-86, FR-87,
FR-94, NFR-8, NFR-9.

Independent evidence requests may be grouped. Concurrency rules and shared-deadline behavior belong
to `workflow-design.md` and `runtime-and-deployment.md`.

### 4.4 Evidence Access Layer

**Purpose.** The single governed boundary between investigative reasoning and RetailEase
information sources. It holds no investigative or causal authority.

**Owns.** The mechanics of read-only operational tools, knowledge retrieval, governed structured-data
querying, and one real MCP tool exposure; request validation; source-specific adapters; result
normalization; provenance capture; deterministic evidence admission; canonical result return.

**Consumes.** Validated requests from the Evidence Investigator; source configuration; permitted
schema information; read-only identity context; the current deadline and request bounds; correlation
context.

**Produces.** Normalized tool results; retrieved passages; structured-query results; admitted
evidence references; operation outcomes; source limitations; provenance; activity and telemetry
events.

**May call.** Approved RetailEase operational sources, knowledge indexes, and the structured-data
source; the MCP-exposed tool path.

**May decide.** Only whether a proposed request is valid against the approved surface. That decision
is deterministic.

**Must not.** Mutate RetailEase or expose any write capability; make investigative decisions; choose
the next question; propose candidate causes; write the brief; broaden a request it received; return
fabricated substitute content after a failure; expose broader semantics or permission through MCP
than through the direct path.

**State responsibility.** The Evidence Access Layer produces admitted evidence into the current
ephemeral turn state. It holds no durable investigation state and writes nothing directly to the
Investigation Record.

**Requirements.** FR-57, FR-75, FR-89 to FR-104, NFR-1, NFR-3, NFR-7, NFR-8.

Internal capabilities are detailed in section 8. They are capabilities of one boundary, never
independently deployed services.

### 4.5 RCA Analyst

**Purpose.** The synthesis agent and the sole synthesis authority.

**Owns.** The structured assessment: candidate ordering, qualitative labels, the leading candidate,
supported alternatives, supporting and weakening evidence relationships, contradictions, unresolved
discriminators, historical interpretation, recommendations, limitation statements, and the
analytical content rendered into the brief.

**Consumes.** A Supervisor synthesis assignment; normalized incident context; admitted operational
evidence; retrieved knowledge; source limitations; relevant completed-turn context; the turn
objective.

**Produces.** One structured assessment; brief content derived from it; an explicit
insufficient-evidence result where appropriate; at most one clearly named further-evidence need
returned to the Supervisor.

**May call.** The model-access seam only.

**May decide.** How to weigh and order candidates; which evidence supports or weakens each; when the
evidence is insufficient to support a cause.

**Must not.** Call the Evidence Access Layer or any tool; admit evidence; alter execution bounds;
deliver directly to the engineer; bypass the grounding gate; present several authoritative causal
conclusions; convert historical comparison into a current-cause probability.

**State responsibility.** Ephemeral draft assessment during synthesis; the accepted assessment
becomes part of the completed-turn artifact written by the Supervisor.

**Requirements.** FR-9, FR-13 to FR-41, FR-58 to FR-67, FR-70, FR-72, FR-79, FR-81 to FR-82,
NFR-2, NFR-4 to NFR-6.

**The further-evidence need** is advisory. It calls no tool, creates no new authority and no new
budget, returns through the Supervisor, and can be acted on only inside the turn's existing bounds.
Routing and the number of permitted feedback cycles belong to `workflow-design.md`.

**Assessment and brief are distinct.** The assessment is the structured internal synthesis the RCA
Analyst owns. The investigation brief is the concise, progressively disclosed rendering derived from
it. There is no separate supported-causal-claim object: a supported causal conclusion is the leading
candidate once the evidence and the grounding gate permit it to be presented that way. Candidate,
citation, brief, and recommendation semantics belong to `data-and-evidence.md`.

### 4.6 Investigation Record

**Purpose.** Passive persistence for completed investigation artifacts.

**Owns.** Storage and retrieval of investigation identity and summary; completed turns and their
outcomes; admitted evidence needed for citation resolution; retrieved-knowledge references needed
for traceability; structured assessments; delivered briefs; follow-up history; retained handoff
summaries; references to traces.

**Consumes.** Completed artifacts from authorized writers.

**Produces.** Retained context to the Supervisor, to the Engineer Interaction Interface through the
Supervisor, to offline evaluation, and to runtime diagnostics.

**May call.** Nothing. It is passive.

**May decide.** Nothing.

**Must not.** Route workflow; make any decision; synthesize a cause; validate grounding; answer an
engineer directly; serve as a mid-turn checkpoint; reconstruct lost in-flight reasoning; restart an
interrupted turn; hold a reference to an evaluation run or result.

**State responsibility.** All persisted state, and only completed state.

**Requirements.** FR-44, FR-45, FR-71, FR-74, NFR-12, NFR-22, NFR-55, NFR-58.

Prefer one logical investigation record with subordinate completed-turn records over several loosely
coordinated stores. Physical containers, partitions, indexes, and document layout belong to
`runtime-and-deployment.md`.

---

## 5. Investigation, Turn, and Live-Session Model

```text
Investigation
├── completed turn
├── completed turn
└── follow-up history

active turn working state → ephemeral
completed turn artifacts  → persisted
```

**Investigation.** Represents one incident under study. It carries the durable identity, contains
zero or more completed turns, retains follow-up history and supporting artifacts, and is the unit
across which conversational context is reconstructed.

**Turn.** One bounded evidence-gathering and synthesis cycle belonging to exactly one investigation.
It has its own objective and its own ephemeral working state, ends as complete, partial, or
inconclusive (FR-55), and produces one assessment and one investigation brief. It becomes durable
only as a completed-turn artifact. A delivered brief is never edited in place; a later change in
analysis appears as a later completed turn.

**Live session.** The current conversational interaction over one investigation. It has no separate
durable identity, reads its context from the investigation and its completed turns, may lose the
in-flight turn on process restart (NFR-57), and never contains several investigations.

### Ephemeral turn working state

The current objective; remaining bounds; the temporary plan; working hypotheses; active assignments;
pending evidence requests; tool results before completion; the draft assessment; activity events.

This state may be lost on restart. No persistence, checkpoint, or replay machinery is designed for
it.

### Completed investigation state

Completed-turn identity and objective; terminal outcome; admitted evidence and required source
references; the final assessment and the delivered brief; limitations; follow-up entries; and the
correlated trace reference.

This state persists. The Investigation Record is not an event store or a workflow engine.

---

## 6. Conceptual Interfaces

These are logical interfaces, described only to the depth that component interaction requires. Field
lists belong to `data-and-evidence.md`; transport belongs to `runtime-and-deployment.md`.

Retrieval, direct tools, structured query, and the protocol boundary differ in transport, not in
result meaning, so they share one request group and one result group. Their common semantics are
defined in `data-and-evidence.md`.

| Interface group | Between | Carries | Authority restriction |
| --- | --- | --- | --- |
| Incident and follow-up input | Engineer Interaction Interface to Supervisor | A normalized incident, or a follow-up classified as question or handoff-summary request | Engineer text travels as untrusted data; classification carries no investigative decision |
| Turn assignment and bounds | Supervisor to Evidence Investigator | The turn objective, incident context, prior evidence and knowledge references, unresolved questions, permitted capabilities, remaining budget | Set by the Supervisor alone; must not request a causal conclusion, and no agent may alter its budget |
| Evidence request | Evidence Investigator to Evidence Access Layer | A capability to invoke with validated parameters, scope, and governing deadline, whether operational, retrieval, structured-query, or protocol-borne | Read-only capabilities only; only the Evidence Investigator may originate one |
| Normalized operation result | Evidence Access Layer to Evidence Investigator | One canonical result for every capability: the observation with its provenance, or the reason none was produced. Retrieval carries the matched passage itself | Never a fabricated substitute after failure; provider syntax and errors never escape the boundary |
| Evidence-investigation result | Evidence Investigator to Supervisor | Evidence gathered, sources unavailable or incomplete, questions answered and outstanding, whether another useful action remains | Carries no authoritative cause |
| Synthesis input | Supervisor to RCA Analyst | Incident context, admitted evidence, retrieved knowledge, limitations, prior-turn context, the turn objective, and why gathering stopped | Carries only admitted material |
| Assessment or further-evidence need | RCA Analyst to Supervisor | One structured assessment, or one named question whose answer could materially change it | Exactly one authoritative assessment per turn; a further-evidence need is advisory and grants no new budget |
| Grounding result | Supervisor internal | Pass, or fail with the failed check identified and a correction requested where the turn's allowance remains | Deterministic, not overridable, and never selects the turn's outcome shape |
| Delivered output and activity | Supervisor to Engineer Interaction Interface | The delivered brief or handoff summary, and the activity events streamed while a turn runs | The brief is delivered only after the gate admits it; activity is observational and carries no decision |
| Completed-turn read and write | Supervisor and Investigation Record | Read: retained investigation summary, completed turns, briefs, evidence references, follow-up history. Write: the completed turn with its outcome, admitted evidence, assessment and brief, limitations, follow-up context, and its trace reference | The Supervisor is the only writer; nothing is written mid-turn, the write precedes terminal delivery, and the Record answers no one directly |

---

## 7. External Interaction Concepts

These are conceptual operations available to the engineer. Paths, methods, status codes, streaming
mechanism, and authentication protocol belong to `runtime-and-deployment.md`.

| Operation | Effect |
| --- | --- |
| Start from predefined intake | Creates the investigation and begins its first bounded turn immediately |
| Observe live turn activity | Streams investigation progress, tool and retrieval activity, evidence arrival, and bounded-stop conditions while a turn runs |
| Retrieve the investigation | Returns the investigation summary and its completed turns and briefs from retained state |
| Submit a follow-up question | Answered from retained state; opens no evidence-gathering turn |
| Request a handoff or status summary | Derived from retained state; opens no evidence-gathering turn |

---

## 8. Evidence Access Layer Design

The Evidence Access Layer carries four internal responsibilities. All belong to one boundary. None
is an agent, an independently deployed module or service, or a separate authority.

### 8.1 Capability validation and dispatch

A registry describes the approved capabilities available to the Evidence Investigator: what each one
answers, the parameters it accepts, its scope limits, and its deadline discipline. Dispatch validates
an incoming request against that description before anything executes, then routes it to the owning
adapter.

The registry is the single place a capability becomes reachable. A capability absent from it is
unreachable by any path, which is what makes the read-only guarantee checkable rather than
conventional (FR-102, NFR-1). Adding a capability means adding a registry entry, not a component.

The registry is a closed, statically known set. The approved capabilities are fixed at build time
and dispatch to them is explicit; no capability is discovered, loaded, or registered at runtime.
That closure is what keeps the property above checkable: a set that cannot change underneath the
system cannot acquire a path the boundary never approved.

### 8.2 Operational and structured access

The operational surface is grouped by stable evidence capability, not by scenario or query shape.
The smallest set that reaches the required RetailEase evidence surface is:

| Capability | Answers |
| --- | --- |
| Incident and alert lookup | What was reported, when, and against which entity |
| Log query | Discrete log records for a service over a window |
| Metric query | Values, series, or aggregates for an entity over a window |
| Deployment and change history | Releases, rollbacks, and configuration changes for a service |
| Service and dependency topology | Which services depend on which, and how |

Alongside these sits the governed structured-query path, which answers tabular operational questions
the others answer poorly:

```text
investigative question
→ approved schema context
→ generated structured query
→ deterministic validation
→ bounded read-only execution
→ normalized result
→ semantic evidence admission
```

Only the Evidence Investigator may originate a request on this path (FR-95, FR-101). Only approved
containers, fields, predicates, projections, and aggregate forms are exposed as schema context, so
the model sees the approved surface and nothing wider (FR-97). Validation is deterministic and runs
before execution, so a query that fails it never reaches the source (FR-98). Execution is read-only
and carries a mandatory result limit and timeout (FR-99). Provider syntax, provider errors, and
provider status never escape the boundary.

**What a generated query is.** The model does not emit query text. It emits a bounded structure whose
every part is drawn from the approved surface, and that structure is what validation checks and what
execution translates. A query names the single approved collection it reads, the projection it wants
back, the predicates that narrow it, an optional count aggregate, and a result limit. Nothing else
is representable, so an unapproved field or an unsupported operation has no expressible form rather
than being caught after the fact.

The supported operations are deliberately narrow:

| Element | Supported forms |
| --- | --- |
| Source | Exactly one approved collection per query; no joins across collections |
| Predicates | Equality and inequality on an approved field; membership in a supplied set; a bounded range on a numeric or temporal field; presence or absence of a value. Predicates combine with conjunction, and with disjunction only within one field |
| Projection | A named subset of approved fields, or the count form below. No wildcard projection and no computed expressions |
| Aggregates | Count only; at most one per query |
| Limit | Always present, always at or below the configured ceiling |

Negation of a whole predicate group, subqueries, unions, joins, free-text fragments, and any
construct that could widen the read surface are absent from the structure and therefore
unrepresentable. Grouping, ordering, and the minimum, maximum, sum, and average aggregate forms are
likewise outside the baseline supported subset and have no expressible form; any of them may be
promoted into the subset only when an authored scenario requires it.

**What validation checks.** Validation runs over that structure, not over text. It confirms that the
collection, every predicate field, and every projected field are present in the approved schema
context; that each operation is one this element permits; that predicate value types match their
field; and that the limit is present and within the ceiling. It rejects anything failing one of
these, and it rejects a structure that is well formed but
references a surface the current request was not granted. A rejected query produces a limitation and
no evidence, exactly as any other operation that did not answer.

The requirement is natural-language-to-structured-query, not natural-language-to-relational-SQL. The
approved operational-records surface it queries is selected in `runtime-and-deployment.md`. The
result normalizes through the same discipline as any other capability and admits with the same
provenance (FR-100); its evidence type reflects what the observation means, never the path that
fetched it.

Every capability here is read-only and carries a bounded timeout.

### 8.3 Knowledge retrieval and protocol transport

Retrieval runs over three routed knowledge collections: runbooks and operational guidance,
architecture and service knowledge, and postmortems and prior-incident history. The collections are
logical categories; whether they share one physical container or several belongs to
`runtime-and-deployment.md`. A request may name a target collection; where it does not, routing
selects from the question's shape, so procedural questions favor runbooks, structural questions
favor service knowledge, and precedent questions favor prior incidents (FR-92).

Each selected collection is searched two ways. Dense search carries semantic similarity, so a
question phrased unlike the source still matches. Lexical search carries exact operational
identifiers, so a service name, error code, or deployment identifier matches literally rather than
approximately (FR-90). Metadata filters narrow either path by service, entity, or time before
ranking; the two candidate sets are fused; and reranking narrows the result to the passages actually
supplied for reasoning (FR-91).

What returns is the matched passage itself with its source, collection, and provenance. A result
reduced to a document identifier is not admissible, because reasoning cannot use a pointer.
Retrieval runs before and during gathering rather than after synthesis, so what is retrieved changes
what the investigation checks (FR-93), and it never independently establishes the current cause
(FR-94).

One approved capability is additionally reachable through a real MCP boundary (FR-104). That path
uses the same logical capability, request and result semantics, read-only permission, validation,
normalization, and provenance, and admits evidence through the same path. Only the recorded
transport differs. A capability reachable through MCP but not directly, or reachable there with
wider permission, is a defect by construction. There is no second implementation and no MCP-specific
evidence concept.

Evaluation distractor content is corpus material, never a runtime component. Collection storage,
embedding and reranking method, chunking, fusion, MCP hosting, and which capability MCP exposes are
selected in `runtime-and-deployment.md` and `decisions.md`.

### 8.4 Normalization and evidence admission

Two deterministic steps close every path above, and neither repeats the other.

Normalization sits at the adapter boundary. It translates source-specific outcomes into the
canonical form, retains provenance, and distinguishes an operation that answered with nothing from
one that returned a partial answer and from one that did not answer at all (NFR-7).

Admission then decides whether a normalized result may become evidence. It admits into ephemeral
turn state, assigns stable evidence references, and records a limitation for any operation that
produced no evidence (FR-68, FR-69, NFR-8). It takes the canonical outcome as established rather
than deriving it again.

It writes nothing durable. There is no separate admission service. The canonical outcome vocabulary,
evidence types, identity rules, and full evidence semantics belong to `data-and-evidence.md`.

### Corpus preparation, which no component owns

Retrieval and structured query both read a corpus that must already be loaded, chunked, embedded, and
indexed. That preparation belongs to no component in §4 and is not a fifth responsibility of this
layer. It is a separate offline concern, named here so it has an owner rather than being assumed.

It runs before any turn, as a setup task with its own identity and its own write access to the
RetailEase collections, which `runtime-and-deployment.md` places outside the application's own
permissions. It produces the three routed knowledge collections §8.3 searches and the approved
operational-records surface §8.2 queries, each carrying the provenance and metadata that retrieval
filters and evidence admission depend on.

It holds no runtime authority. It participates in no turn, is reachable from no component, and is not
a runtime component of any kind. Nothing in the live path invokes it, and its absence is a
deployment-time failure rather than a turn-time one. The application's own identity holds read-only
access to everything it writes, so the live system cannot alter the corpus it observes (NFR-1).

Chunking method, embedding method, and where the prepared collections live are selected in
`runtime-and-deployment.md` and `decisions.md`.

---

## 9. Investigation Record and Persistence Responsibilities

Only completed artifacts persist, and the Supervisor is their single writer:

| Artifact | Written by | When |
| --- | --- | --- |
| Investigation identity and summary | Supervisor | With the first completed-turn commit |
| Completed turn, its identity, objective, and terminal outcome | Supervisor | At turn completion |
| Admitted evidence and required source references for that turn | Supervisor | At turn completion |
| Structured assessment for the turn | Supervisor | At turn completion |
| Delivered investigation brief and its limitations | Supervisor | At turn completion, after the gate passes |
| Follow-up history | Supervisor | As follow-ups arrive |
| Retained handoff summaries | Supervisor | When produced |
| Trace reference | Supervisor | At turn completion |

No other component writes. The Engineer Interaction Interface, the Evidence Investigator, the RCA
Analyst, and the Evidence Access Layer never write to the Record.

Investigation and turn identities are created ephemerally when a turn starts and may be exposed on
the live stream, but starting a turn persists nothing. The first successful completed-turn commit
creates the investigation record together with that turn. What a failed first execution leaves behind
belongs to `workflow-design.md`.

While a turn runs, the Evidence Access Layer normalizes results and deterministic admission assigns
stable evidence references, but admitted evidence stays in ephemeral turn working
state. Nothing is durably written until the Supervisor commits the completed-turn artifact, which
carries the admitted evidence with it. No cleanup, pending-record, or provisional storage is
required, because nothing provisional is ever written. What an incomplete turn leaves behind belongs
to `workflow-design.md`.

**Persistence precedes delivery.** The Supervisor coordinates terminal delivery only after the
completed-turn commit succeeds; the ordering and what follows a failed commit belong to
`workflow-design.md`. The Investigation Record itself holds no delivery authority.

What the completed-turn artifact carries, including that evaluation artifacts are not part of it,
belongs to `data-and-evidence.md`.

The Record holds no mid-turn workflow state, no pending-turn marker, no snapshot, and no replay log.
Nothing in the design reconstructs a lost in-flight turn; the turn is simply run again (NFR-57).

---

## 10. Shared Model and Telemetry Seams

Both are seams reached through by components. Neither is a component.

### 10.1 Model-access seam

All three agents reach models through one shared adapter. It carries role, investigation, turn, and
task context on every request, returns model output as structured proposed data, and records model
identity, latency, token usage, and approximate cost (NFR-18).

Deterministic code admits or rejects that proposed output. Models own no permissions, no bounds, no
persistence, no evidence admission, and no terminal outcome (NFR-10). Prompts and output contracts
remain role-specific and live behind the seam so a test can replace them wholesale.

### 10.2 Model routing

One deliberate, visible routing decision is required (FR-105), satisfied by one lightweight routing
seam rather than a router component.

The posture is one primary model deployment handling substantive evidence interpretation and RCA
synthesis, and one lower-cost deployment handling a clearly bounded simple task. The routing
decision and the selected model are visible in diagnostics.

That bounded simple task is the Supervisor's objective interpretation, which reads the selected
incident and states what the turn is trying to establish (§4.2). Anything that interprets evidence
or produces an assessment stays on the primary deployment, as does the Supervisor's follow-up answer
task (§4.2). Classification of later engineer input is deterministic and is not routed to a model at
all.

Which deployment serves which task is settled in `decisions.md`. No severity tiers, policy engine,
fallback chain, or multi-provider abstraction is introduced.

### 10.3 Telemetry seam

Every top-level component emits structured activity through one shared seam, carrying correlation
context across every boundary.

| Component | Emits |
| --- | --- |
| Engineer Interaction Interface | Intake, classification outcome, presentation and stream events |
| Supervisor | Turn start and objective, assignments, continuation decisions, budget consumption, grounding-gate result, terminal outcome, completed-turn write |
| Evidence Investigator | Question selection, capability choice and reason, gathering result, unresolved questions |
| Evidence Access Layer | Tool, retrieval, structured-query, and MCP operations with outcome and latency; evidence admission; source limitations |
| RCA Analyst | Synthesis start, assessment produced, insufficiency, further-evidence need |
| Investigation Record | Read and write operations |

Correlation must be sufficient to reconstruct an investigation and turn end to end, attribute every
step to a role, and expose degradation, latency, model and tool call counts, token usage, and
approximate cost (NFR-14, NFR-18, NFR-20). Errors stay legible and attributable.

Telemetry products, event schemas, metric names, retention, and health endpoints belong to
`runtime-and-deployment.md`. Instrumentation rules belong to `code-guidelines.md`. Quality scoring
belongs to `evaluation.md`.

### 10.4 Activity projection

The live activity feed the Engineer Interaction Interface presents is a small display projection of
the same workflow facts the telemetry seam records, produced at the same instrumentation points. It
is not a second event model, not an event platform, and not a copy of telemetry.

An activity event carries only what the compact feed consumes: a sequence position; the active
phase or actor; the action; its status; a short safe display detail; and, where they apply, the
capability or source, the transport, the canonical outcome, and existing operation, evidence, or
knowledge references. Shared identifiers correlate an event with its telemetry. Telemetry may carry
richer diagnostic detail; the engineer-facing surface receives only this projection and never
queries the telemetry store. No model call generates activity narration, and no event carries
chain-of-thought, prompts, raw model output, provider content, or secrets.

A typical turn should read as a compact feed of meaningful events rather than a debug log, so
repeated low-level operations may be grouped or summarized. Activity events are ephemeral: they are
streamed while the turn runs and are not persisted or replayed; after completion, the retained
completed turn is what remains visible. Which component emits which fact is the §10.3 table's
assignment and is not restated here. When events are emitted belongs to `workflow-design.md`
("Activity events"); stream transport belongs to `runtime-and-deployment.md`.

---

## 11. Technology Responsibility Map

This map names the responsibility and where its concrete choice is settled. It does not restate
runtime design.

| Responsibility | Posture at this altitude | Where the choice is settled |
| --- | --- | --- |
| Model reasoning and routing | Azure OpenAI, reached through one narrow adapter, with one primary deployment plus one lower-cost bounded path | `runtime-and-deployment.md`; the routing signal in `decisions.md` |
| Orchestration and turn state | Explicit stateful orchestration holding ephemeral turn state in process | `decisions.md` |
| Knowledge retrieval | Dense plus lexical search over three routed collections, with metadata filtering, fusion, and bounded reranking | `runtime-and-deployment.md`; method in `decisions.md` |
| Structured-data querying | A governed, validated, read-only query path over an approved operational-records surface | `runtime-and-deployment.md` |
| Operational tools | Read-only RetailEase adapters registered as capabilities | `runtime-and-deployment.md` |
| Protocol boundary | One approved capability additionally reachable through a real MCP boundary, hosted inside the application boundary rather than as a separate service | `runtime-and-deployment.md`; which capability in `decisions.md` |
| Investigation Record persistence | Document persistence for completed artifacts only | `runtime-and-deployment.md` |
| Application hosting | One container-hosted Azure application, startable on demand | `runtime-and-deployment.md` |
| Identity, secrets, and caller authentication | Scoped data-plane access for stored data, a held deployment secret for the model connection, and the smallest credible caller authentication | `runtime-and-deployment.md` |
| Activity streaming | A live activity stream to the engineer-facing surface | `runtime-and-deployment.md` |
| Telemetry | Structured correlated logs, traces, health, and usage through one seam | `runtime-and-deployment.md` |
| Evaluation integration | Offline consumer of completed artifacts and traces | `evaluation.md` |

Azure is the fixed hosting environment and Azure OpenAI is the selected model provider. Every other
product choice, including the store behind the Investigation Record, the knowledge collections, and
the operational-records surface, is settled in `runtime-and-deployment.md` rather than here. How many
application replicas run is a runtime realization and creates no additional boundary.

---

## 12. Requirement Traceability

| Design element | Principal requirements realized |
| --- | --- |
| Engineer Interaction Interface | FR-1, FR-3, FR-6, FR-43, FR-106 to FR-119, NFR-53 |
| Supervisor | FR-5, FR-42, FR-44, FR-49 to FR-56, FR-71, FR-74, FR-77, FR-80, FR-85, FR-88 |
| Grounding gate | FR-23, FR-38, FR-62, NFR-2 to NFR-5, NFR-10 |
| Evidence Investigator | FR-49 to FR-52, FR-57, FR-61, FR-78, FR-84, FR-86, FR-87, FR-94 |
| Evidence Access Layer | FR-57, FR-75, FR-103, NFR-1, NFR-7, NFR-8 |
| RCA Analyst | FR-9, FR-13 to FR-41, FR-58 to FR-67, FR-70, FR-72, FR-79, FR-81 to FR-82 |
| Investigation Record | FR-44, FR-45, FR-71, FR-74, NFR-12, NFR-22, NFR-55, NFR-58 |
| Knowledge retrieval subsystem | FR-89 to FR-94, NFR-31 to NFR-34 |
| Governed structured-query subsystem | FR-95 to FR-102, NFR-43 |
| MCP boundary | FR-104, NFR-44 |
| Normalization and evidence admission | FR-68, FR-69, NFR-3, NFR-7, NFR-8 |
| Investigation, turn, and live-session model | FR-8, FR-42, FR-45, FR-55, NFR-12, NFR-56 to NFR-58 |
| Completed-artifact persistence | NFR-22, NFR-55, NFR-57, NFR-58 |
| Model-access seam and routing | FR-76, FR-105, NFR-10, NFR-18 |
| Telemetry seam | FR-109 to FR-117, NFR-14, NFR-18, NFR-20 |
| External interaction concepts | FR-1, FR-3, FR-5, FR-6, FR-71, FR-73, FR-74, NFR-53 |
| Read-only boundary across every path | FR-75, FR-102, NFR-1 |
| Bounded execution | FR-53 to FR-56, NFR-10 |
