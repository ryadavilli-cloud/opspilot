# OpsPilot Requirements

**What must OpsPilot do, preserve, demonstrate, constrain, defer, prefer, and exclude?**

OpsPilot is an agentic incident-investigation assistant for on-call engineers. This document defines
the required product behavior, the domain it supports, the output it must produce, the capabilities
it must demonstrate, the quality it must hold to, what it accepts as proof that it works, and the
boundaries that keep it achievable.

It states observable behavior and commitments, not mechanisms. Top-level system shape, component
structure, execution mechanics, data and evidence semantics, runtime and deployment realization,
evaluation method, settled technical choices, and implementation rules are each owned by their own
document. Requirements names no library, framework, model, database, cloud service, query language,
or transport, with a single exception: Azure is named as the fixed hosting environment, because that
commitment is made at requirements level and portability is not a goal.

---

## 1. Purpose and Value

When an operational alert occurs, an on-call engineer often spends the first fifteen to twenty
minutes gathering context before meaningful diagnosis can begin. They inspect metrics and logs,
check recent changes, review dependencies, search runbooks, and look for similar incidents and prior
remediation work.

The same alert or visible symptom may have several underlying causes. The engineer must determine
which explanation best fits the current evidence, what remains uncertain, and what can be done
immediately without confusing temporary mitigation with permanent prevention.

OpsPilot must prepare the equivalent of this initial investigation and present it as a concise,
evidence-supported brief the engineer can explore conversationally. It targets avoidable
evidence-gathering and early-diagnosis overhead. It does not replace the engineer, guarantee the
root cause, or operate as a production incident-management platform.

### Why bounded adaptive investigation is required

Many common incidents can be handled by deterministic alerts, dashboards, and known-signature
lookups. OpsPilot does not replace those simpler mechanisms.

Adaptive investigation is required where the correct evidence path cannot be fully known in advance,
where one observation changes what should be checked next, and where a conclusion requires
correlating structured and unstructured information from several sources. OpsPilot must focus on
bounded scenarios where adaptive investigation provides visible value over a fixed script.

A simple fixed-sequence baseline must remain available for comparison, and at least one authored
scenario must show why adaptive routing, follow-up retrieval, or hypothesis revision beats running
the same lookups in the same order.

---

## 2. Product Posture and Scope

OpsPilot is a bounded, repeatable incident-investigation environment. It must work coherently end to
end on the RetailEase domain and must demonstrate a set of agentic AI capabilities working together.
Its value is judged by how well those capabilities combine, not by the number of agents, frameworks,
services, protocols, or infrastructure components used. Every specialist responsibility must serve a
distinct purpose, and any additional complexity must earn its place.

OpsPilot recommends actions but remains read-only against the environment it investigates. It
observes; it never changes what it observes.

The project must remain suitable for one developer, incremental vertical slices, a bounded schedule,
and an individual-scale runtime budget. Safety, grounding, bounded execution, provenance,
traceability, reproducible deployment, and repeatable evaluation must be real. Production-scale
availability, throughput, tenancy, compliance, and operational breadth are outside its ambitions.

---

## 3. Supported Domain and Corpus

OpsPilot operates against **RetailEase**, a synthetic e-commerce microservices environment.
RetailEase provides the service topology, operational knowledge, incident history, deployment
records, dependency relationships, and post-incident narrative used by the primary flow.

The existing authored corpus must be reused rather than replaced by a second primary environment.

### Current authored corpus

The corpus contains seven authored incidents spanning five overlapping incident families:

- resource saturation or capacity exhaustion;
- downstream or external dependency failure;
- deployment regression;
- cache failure or stale-data behavior;
- queue backlog or consumer failure.

These families share alerts and visible symptoms deliberately. OpsPilot must distinguish causes by
evidence and must never assume that one alert name maps to one cause.

### Evidence surface

Investigation must be able to reach:

- logs;
- metric observations;
- deployment records;
- service dependencies;
- runbooks;
- postmortems;
- prior incidents and remediation records;
- structured operational tables.

Evidence references must use stable typed identifiers so that citations and answer-key references
can be checked automatically. Evidence must be typed by the meaning of the observation, not by the
access path that returned it.

### Corpus completeness before final evaluation

Before final evaluation can run, the corpus must contain at least one clear example of each of:

- a well-supported single-cause incident;
- an incident with competing hypotheses;
- an incident with multiple contributing failures;
- an incident where important evidence is unavailable;
- a transient or low-impact condition where immediate action is not justified.

Some of these may already be represented among the seven authored incidents. Coverage must be
audited rather than assumed, and any gap closed before final results are reported.

Corpus structure, answer-key generation, and ground-truth schema are owned by `evaluation.md`.

---

## 4. Authoritative User Journey

An **investigation** is one incident under study. A **turn** is one bounded evidence-gathering and
synthesis cycle within that investigation, producing one **investigation brief**. A **live session**
is the ephemeral conversational surface over an investigation; it is not a separately persisted
entity.

**FR-1** The primary entry path is selection of a predefined RetailEase incident. **FR-2** A
secondary free-text path normalizes a symptom description into the same structured incident form.
**FR-3** All intake paths must converge before investigation begins. **FR-4** A genuinely
underdetermined free-text input may trigger at most one clarifying question before normalization;
there is no further clarification mechanism for later messages.

**FR-5** The authoritative flow is:

1. The engineer selects an incident or describes a symptom.
2. Free text, when used, is normalized into the same structured incident form as selection.
3. Investigation begins immediately; structured intake requires no blocking confirmation.
4. The interface streams investigation activity, tool use, and evidence arrival while a turn runs.
5. The turn runs adaptively within its configured bounds, or the engineer stops it.
6. One coherent investigation brief is produced for that turn, unless the turn was cancelled
   before any evidence was gathered; that turn completes as inconclusive without a brief.
7. The engineer asks about reasoning, evidence, alternatives, or unknowns.
8. The engineer may redirect the next turn toward a named candidate cause, or supply additional
   evidence or context for it.
9. A revised brief is produced when the added evidence or new direction changes the analysis.
10. The engineer may request a concise handoff or status summary.

**FR-6** A follow-up question or a handoff-summary request must be answered from retained
investigation state without opening a new evidence-gathering turn. **FR-7** A redirect or supplied
evidence seeds a new bounded turn.

**FR-8** New evidence does not alter a turn already executing. Between-turn updates demonstrate
adaptive behavior without requiring mid-flight cancellation and state merging.

Every completed turn has exactly one outcome: **complete**, **partial**, or **inconclusive**.

An execution attempt that cannot produce, validate, persist, and deliver a trustworthy brief fails
without creating a completed turn. Failed execution is not a fourth investigation outcome.

---

## 5. Investigation Brief Requirements

**FR-9** The investigation brief is the authoritative user-facing result of a turn. **FR-10** A
handoff or status summary is a secondary output derived from the same investigation state.

### 5.1 Presentation

**FR-11** The brief must be concise enough to use during an active incident. **FR-12** It must lead
with the most useful current conclusion and next action, while detailed evidence, alternate causes,
history, diagnostics, and agent activity remain available through progressive disclosure.

### 5.2 What happened

**FR-13** The brief must be able to summarize what happened: the incident or alert and its timing;
the affected service, component, dependency, or user impact; the triggering metric, log, trace, or
event; related symptoms and affected components; and whether the evidence is consistent with one
issue or suggests multiple contributing failures.

### 5.3 What may be causing it

The brief must provide:

- **FR-18** the leading candidate cause, the evidence that supports it, and the evidence that weakens
  or contradicts it where available;
- **FR-21** other plausible candidate causes;
- **FR-22** the most useful next check when additional evidence could distinguish candidates;
- **FR-23** an explicit statement when the available evidence is insufficient.

**FR-24** Candidate causes must be ordered and assigned qualitative support labels such as
**Leading**, **Plausible**, or **Weakly supported**. **FR-25** A supported causal conclusion may be
stated only when the evidence supports one.

**FR-26** Historical frequency must be shown separately from current support and must never be
converted into a probability for the current incident. OpsPilot does not produce calibrated
root-cause probabilities.

### 5.4 What history says

The brief must be able to summarize relevant previous occurrences:

- **FR-27** what caused them, what mitigation or follow-up action was recorded, whether a longer-term
  fix, change, ticket, or remediation item exists, whether the current evidence differs materially
  from the historical pattern, and whether a plausible current cause has no prior occurrence in the
  available history;
- **FR-28** how often each known failure mode appeared, with actual counts where useful.

**FR-33** History must inform the current investigation without overruling current evidence.

### 5.5 What to do

**FR-34** Recommendations must be separated into three horizons:

| Horizon | Purpose |
| --- | --- |
| **Now (approximately 5 minutes)** | Reduce immediate impact, confirm whether intervention is needed, or explain why no immediate action is justified |
| **Soon (approximately 1 hour)** | Stabilize the service, verify mitigation, gather remaining evidence, and determine escalation or coordination needs |
| **Later (approximately 24 to 48 hours)** | Reduce recurrence through code, configuration, capacity, resilience, observability, alerting, runbook, or follow-up improvements |

**FR-35** Recommendations must connect to observed evidence and candidate causes. **FR-36** Temporary
mitigation and longer-term prevention must remain distinct. **FR-37** Where an immediate mitigation
is recommended, the brief must state what should be observed to verify it worked.

**FR-38** Each recommendation must identify its provenance where practical: retrieved runbook
guidance, an action recorded in a prior incident, or general operational practice generated by the
model.

### 5.6 Outcome forms

**FR-39** A **complete** brief presents a supported analysis for the turn's objective.

**FR-40** A **partial** brief presents what was established before the turn stopped, states plainly
that it is incomplete, and names what was not reached.

**FR-41** An **inconclusive** brief states that the available evidence cannot support a cause, names
what is missing or contradictory, and does not present a best guess as an established finding.

---

## 6. Functional Requirements

### 6.1 Intake and Investigation Control

OpsPilot must:

- **FR-42** establish one incident as the active investigation;
- **FR-43** accept predefined selection or normalized natural-language input;
- **FR-44** retain findings, tool results, questions, and engineer corrections across the turns of
  one investigation;
- **FR-45** keep unrelated investigations isolated from one another;
- **FR-46** allow the engineer to stop a turn and receive the result available at that point;
- **FR-47** allow the engineer to redirect the next turn toward a named candidate cause;
- **FR-48** update the analysis when new evidence materially changes it.

### 6.2 Adaptive and Bounded Investigation

OpsPilot must:

- **FR-49** select evidence sources based on the incident and the findings so far;
- **FR-50** avoid running every tool in the same sequence for every incident;
- **FR-51** use one observation to decide whether another check is useful;
- **FR-52** revise direction when evidence weakens the current explanation;
- **FR-53** operate within configurable deterministic limits on steps, tool calls, retries, elapsed
  time, context, and model use;
- **FR-54** prevent runaway execution and its cost;
- **FR-55** give every completed turn exactly one outcome: complete, partial, or inconclusive.

**FR-56** No agent may extend, reset, or otherwise widen its own limits. The system must be adaptive
without being open-ended.

### 6.3 Evidence, Diagnosis, and History

OpsPilot must:

- **FR-57** gather evidence from a controlled subset of the RetailEase evidence surface;
- **FR-58** distinguish observations, inferences, and recommendations;
- **FR-59** produce a leading candidate cause and retain supported alternatives;
- **FR-60** show evidence that supports or weakens each meaningful candidate;
- **FR-61** identify a useful discriminator when one additional check could separate candidates;
- **FR-62** state when evidence is sparse, contradictory, missing, or unavailable;
- **FR-63** preserve contradictory evidence rather than resolving it away silently;
- **FR-64** avoid manufacturing alternatives merely to appear comprehensive;
- **FR-65** recognize multiple contributing failures within one incident;
- **FR-66** retrieve and compare relevant historical occurrences;
- **FR-67** never treat history as proof of the current cause.

**FR-68** Tool failures and unreachable sources must be exposed as explicit limitations. **FR-69**
They must never be fabricated into observations.

### 6.4 Multi-Turn Conversation and Outputs

OpsPilot must:

- **FR-70** produce the investigation brief defined in section 5 for every completed turn, with
  one exception: a turn cancelled before any evidence was gathered completes as inconclusive with
  no assessment and no brief, and its retained result states the cancellation and the
  insufficiency of evidence plainly;
- **FR-71** answer follow-up questions from retained investigation state rather than starting over;
- **FR-72** allow "no immediate action required" or "safe to defer pending follow-up" when supported;
- **FR-73** expose the supporting sources and tool outcomes behind its conclusions;
- **FR-74** produce a concise handoff or status summary from existing investigation state;
- **FR-75** remain read-only against the target environment throughout.

---

## 7. Required Agentic Capability Commitments

**FR-76** These are required capabilities, not preferences. Each must be genuinely present and
visibly demonstrable end to end.

### 7.1 Agent responsibilities

Three logical agent responsibilities are required:

- **FR-77** a **Supervisor** that interprets each turn's objective, coordinates the work, and
  enforces bounds;
- **FR-78** an **Evidence Investigator** that gathers evidence adaptively through approved sources;
- **FR-79** an **RCA Analyst** that is the sole authoritative owner of analysis and synthesis.

**FR-80** Coordination must be Supervisor-mediated and inspectable rather than open-ended peer
conversation.

**FR-81** The RCA Analyst's analysis may contain one leading candidate, supported alternatives,
qualitative support labels, supporting and contradicting evidence, unresolved discriminators, and a
supported causal conclusion where the evidence permits one.

**FR-82** Ranked candidates do not become multiple authoritative conclusions.

**FR-83** The engineer-facing interface, evidence access, retrieval, tools, deterministic controls,
persistence, evaluation, and observability are not agents.

### 7.2 Adaptive investigation behavior

Required:

- **FR-84** a reason-act-observe style investigation loop, with the selected loop style and its
  trade-off stated in the design documentation;
- **FR-85** conditional routing, such that different incidents take demonstrably different evidence
  paths;
- **FR-86** adaptive evidence-source selection driven by what has already been observed;
- **FR-87** parallel execution of independent evidence-gathering work;
- **FR-88** bounded termination that reports a partial result honestly.

### 7.3 Retrieval

**FR-89** An end-to-end retrieval capability is required. It must:

- **FR-90** handle both semantic similarity and exact operational identifiers well enough to be
  trusted on service names, error codes, and deployment identifiers;
- **FR-91** combine dense and lexical retrieval with result fusion and reranking;
- **FR-92** use separate knowledge collections or indexes with routing between them;
- **FR-93** demonstrably influence what the investigation checks and concludes, rather than
  decorating a finished result.

**FR-94** Retrieved knowledge informs interpretation. It can never independently establish the cause
of the current incident.

### 7.4 Governed structured-data access

**FR-95** A bounded natural-language-to-structured-query capability is required, available to the
Evidence Investigator only. It must be:

- **FR-96** governed, and never a general-purpose database assistant;
- **FR-97** bounded to an approved schema and query surface;
- **FR-98** deterministically validated before execution;
- **FR-99** executed read-only, under explicit limits and a timeout;
- **FR-100** normalized into evidence with provenance;
- **FR-101** unavailable directly to the RCA Analyst;
- **FR-102** incapable of mutating operational data under any configuration.

### 7.5 Tool boundary and protocol interoperability

Required:

- **FR-103** read-only operational tools with explicit, structured outcomes;
- **FR-104** one real external protocol boundary, exposing at least one tool with no broader
  permission and no different semantics than the direct path.

### 7.6 Model routing

**FR-105** One deliberate model-routing decision is required, such as using a lower-cost path for a
simple or low-severity task, with the routing signal visible.

### 7.7 Observable investigation surface

**FR-106** The engineer-facing surface must demonstrate both the incident-assistance experience and
the agentic system producing it. **FR-107** Production polish is not required; a plain chat screen
that hides the workflow is insufficient.

While a turn runs and afterwards, the engineer must be able to see:

- **FR-108** incident selection and free-text intake;
- **FR-109** live investigation activity;
- **FR-110** the announced next investigation action and the evidence checks already completed;
- **FR-111** specialist-responsibility activity;
- **FR-112** tools invoked and their outcomes;
- **FR-113** retrieved documents and structured query results;
- **FR-114** evidence connected to the conclusions it supports;
- **FR-115** qualitative candidate labels and changes in candidate ordering after follow-up evidence;
- **FR-116** missing sources, retries, failures, cancellation, and bounded-stop conditions;
- **FR-117** handoff-summary generation.

During a live turn this activity is streamed as it happens. After the turn completes, the retained
completed turn satisfies this visibility through its brief, evidence, limitations, and outcome;
durable replay of the complete live activity sequence is not required.

**FR-118** A developer or diagnostics view may additionally expose model and prompt metadata,
structured model outputs, detailed tool requests and responses, latency, token use, approximate cost,
trace identifiers, and evaluation results. **FR-119** Raw model responses may be available for
debugging or demonstration, but the primary interface must emphasize structured evidence and
operationally useful output rather than hidden reasoning transcripts. The developer view may be
realized as progressive disclosure within the primary interface; a separate diagnostics application
is not required, and the interface must not expose chain-of-thought or other hidden model
reasoning.

---

## 8. Quality and Non-Functional Requirements

### 8.1 Trust, safety, and correctness

- **NFR-1** Operational access remains read-only on every path and under every configuration.
- **NFR-2** Material claims must resolve to admitted evidence; unsupported claims must never be
  presented as established facts.
- **NFR-3** Citations must resolve to stable evidence references.
- **NFR-4** Recommendation provenance must be available.
- **NFR-5** Missing, contradictory, sparse, or unavailable evidence must be disclosed rather than
  smoothed over.
- **NFR-6** Contradictory observations must be preserved rather than overwritten.
- **NFR-7** Tool results must preserve the observable distinction between a source that returned
  evidence, a source that successfully found no matching evidence, a source that returned an
  incomplete result, and a source that could not execute or answer.
- **NFR-8** Degradation must be graceful: a failed or unavailable source produces a stated
  limitation, never a fabricated observation.
- **NFR-9** Retrieved content, tool output, and engineer-supplied text are untrusted data, never
  instructions.
- **NFR-10** Deterministic controls must be enforced in code and must not be overridable by an agent.
- **NFR-11** Working or scratchpad state must remain separate from user-facing output.
- **NFR-12** Unrelated investigations must remain isolated.
- **NFR-13** Identity and secret handling must be sound at a basic level, with approved data access
  only.

### 8.2 Operability and evidence of correctness

- **NFR-14** Agent, tool, and model activity must be traceable end to end for one investigation.
- **NFR-15** Tools and evidence references must be deterministically testable.
- **NFR-16** Evaluation must be repeatable, and changes must be regression-comparable.
- **NFR-18** Per-investigation latency, token use, and approximate cost must be visible.
- **NFR-19** The application must report basic health and fail in controlled, legible ways.
- **NFR-20** The deployed application must be diagnosable from its logs and telemetry without
  redeployment.
- **NFR-21** Prompts, tools, and configuration must remain maintainable behind stable seams.
- **NFR-22** Completed investigation records and traces must persist.

### 8.3 Depth of treatment

**NFR-23** The concerns in section 8.1 must be fully demonstrated. **NFR-24** Of those in section
8.2, a practical baseline is sufficient for latency and token and cost visibility, basic application
health and controlled errors, diagnosability of the deployed application from its logs and telemetry,
prompt and tool and configuration maintainability, and persistence of investigation records and
traces. The same practical baseline is sufficient for the local and hosted operation section 10
states. Deferred capabilities are in section 12; concerns carried only as extension seams are in
section 13.

---

## 9. Demonstration and Acceptance Expectations

Evaluation exists to demonstrate deliberate development and to enable comparison across changes. It
does not certify production incident-management quality. **NFR-25** An offline model-assisted judge
scores completed output against a rubric or golden scenario; it is never a runtime authority that
confirms a diagnosis.

**NFR-26** Final targets are recorded after an initial fixed-script and early OpsPilot baseline run.
**NFR-27** Any numeric threshold is set after that baseline and must remain appropriate to a small
corpus. **NFR-28** Any published timing, quality, or cost value is a demonstration target, not a
service-level commitment. Scoring methods, judges, metric definitions, ablations, and reporting
formats are owned by `evaluation.md`.

### 9.1 Diagnosis behavior by scenario class

**NFR-29** The following scenario classes define the minimum diagnosis behavior OpsPilot must
demonstrate.

| Scenario class | Acceptance expectation |
| --- | --- |
| Clear single-cause incident | The expected cause appears first, with correct supporting evidence |
| Ambiguous incident | The expected cause appears among the top candidates, with supporting evidence |
| Multiple contributing failures | The brief identifies that one cause does not explain all signals |
| Sparse evidence | The brief states that evidence is insufficient and names what is missing |
| Benign or transient condition | The brief allows no immediate action where that is supported |

**NFR-30** Results must be reported by scenario class with named failures, never hidden inside one
aggregate percentage.

### 9.2 Retrieval

- **NFR-31** Retrieval must be measured for precision and recall.
- **NFR-32** No evaluated incident may retrieve none of its expected evidence.
- **NFR-33** Exact identifiers such as service names, error codes, and deployment identifiers must
  be checked deterministically.
- **NFR-34** The selected retrieval approach must be compared against a simpler baseline.

### 9.3 Grounding and provenance

**NFR-35** Every incident-specific observation must cite resolvable evidence, every cited identifier
must resolve to a real corpus entry, inferences must identify the observations they depend on, and
recommendations must identify whether they came from a runbook, a prior incident, or general
operational practice.

**NFR-36** A model-assisted judge may additionally score whether cited evidence supports the claim
attached to it.

### 9.4 Tools, degradation, and recommendations

- **NFR-37** Evaluation must cover appropriate tool and evidence-path selection.
- **NFR-38** Evaluation must cover completion with an explicit partial result when a noncritical
  source fails.
- **NFR-39** Evaluation must cover bounded retries and bounded termination.
- **NFR-40** Evaluation must cover the presence of the required recommendation horizons.
- **NFR-41** Deterministic checks must verify that no prohibited write or unsupported operational
  action occurs.
- **NFR-42** Model-assisted evaluation must score usefulness, completeness, and relevance.

### 9.5 Structured-query and protocol correctness

**NFR-43** Structured-query behavior must be checked by comparing execution results against a golden
result, not by comparing generated query strings. **NFR-44** The protocol tool boundary must be
verified to produce the same semantics and no broader permission than the direct path.

### 9.6 Value of adaptive investigation

**NFR-45** A fixed-script baseline must use the same corpus and tools in a predetermined lookup
order, and at least one scenario must show an advantage from adaptive routing, follow-up retrieval,
or hypothesis revision. This supports the design claim; it need not prove that adaptive investigation
wins on every incident.

### 9.7 Repeatability, latency, and cost

**NFR-46** Repeated runs over a small representative subset must be recorded, along with whether the
leading candidate remains reasonably stable, end-to-end and major-step latency, the number of model
and tool calls, and token use and approximate cost. **NFR-47** These are reported alongside
correctness, never in a separate appendix. **NFR-48** A prompt or model change must be comparable
before and after.

### 9.8 Continuous evaluation signal

**NFR-49** Evaluation must run as an advisory, non-blocking signal on change. It informs; it does not
gate merge.

---

## 10. Runtime and Deployment Outcome

OpsPilot must:

- **NFR-50** run locally for development and evaluation;
- **NFR-51** run in Azure for a repeatable hosted demonstration;
- **NFR-52** be startable on demand rather than maintained as an always-on service;
- **NFR-53** make live investigation activity visible to the engineer while a turn runs;
- **NFR-54** tolerate ordinary demonstration downtime without implying an availability commitment;
- **NFR-55** persist completed turns and their briefs, the evidence needed to resolve their
  citations, and traces. Evaluation artifacts are also retained, and may be stored separately from
  the completed turns they reference.

**NFR-56** Short-term context is retained across the turns of a live session. **NFR-57** Losing an
in-flight turn's progress on process restart is acceptable baseline behavior; the turn is simply run
again. **NFR-58** Completed records remain intact and readable.

The hosted environment exists to demonstrate deployability and runtime observability, not production
availability engineering.

---

## 11. Strong Preferences

These may be attempted only after the primary end-to-end flow works. They create no downstream
design or implementation obligation unless explicitly promoted. No other document may design for
them, reserve structure for them, or plan against them. Promotion requires stating the promotion
here first.

- **Numeric evidence-support scoring.** If implemented, a score must be derived from defined
  supporting and contradicting evidence rather than invented by the model, and must never be
  presented as the probability that a candidate is correct. Qualitative candidate labels are
  required regardless; a numeric score is not.
- **Query rewriting or expansion.**
- **Context summarization or compression.**
- **Lightweight caching.**
- **A review or self-critique pass over the draft analysis.**
- **Bounded schema-retrieval refinement beyond the baseline governed query path.**
- **Explicit context-engineering documentation** covering write, select, compress, and isolate.
- **A privacy-redaction extension seam**, even though the primary corpus is synthetic.

---

## 12. Deferred Capabilities

These are intentionally outside the baseline. They must not be designed for or built against unless
promoted.

- Restart-resumable live sessions or in-flight turns.
- Long-term memory across investigations. If cross-investigation memory is ever promoted, admission
  into it must be explicit and governed; delivering a brief must never by itself admit its content
  into reusable memory.
- Learning from engineer corrections.
- An agent-to-agent interoperability card.
- Tuned semantic caching.
- Richer automatic proposal of diagnostic checks.
- A held-out generalization probe on a small, structurally similar external slice. Its purpose would
  be limited to showing that OpsPilot produces a coherent, evidence-grounded brief on unfamiliar
  evidence; diagnostic accuracy against the RetailEase answer key would not be scored. It is
  deferred wherever it would threaten completion of the primary RetailEase flow.

---

## 13. Considered Concerns

These are not baseline commitments and require no implementation. Runtime documentation should
identify a reasonable extension seam for each, without introducing unused infrastructure.

- Provider or model fallback.
- Horizontal scalability and capacity planning.
- Production-scale security hardening.

---

## 14. Non-Goals and Exclusions

OpsPilot does not include:

- autonomous remediation or any operational write;
- application of generated production code or configuration fixes;
- approval gates for operational writes, since the system is read-only;
- incident detection before an engineer request;
- automatic webhook ingestion;
- replacement of monitoring or incident-management platforms;
- support for arbitrary incidents or infrastructure environments;
- coordination of several independently declared incidents;
- mid-flight evidence injection into a running turn;
- a general-purpose multi-agent platform;
- production-grade high availability, disaster recovery, regional failover, scalability, tenancy,
  compliance certification, or service-level commitments;
- production-scale performance and cost optimization;
- calibrated root-cause probabilities;
- a large production-like corpus;
- voice or speech interaction, which fits poorly with a dense evidence brief;
- fine-tuning and related adaptation techniques, because the knowledge changes and must remain
  retrievable and citable;
- learned sparse retrieval at this corpus size;
- canary and rollback workflows, which need real production traffic to mean anything;
- automated drift detection, against a fixed corpus and a controlled demonstration runtime;
- full agent-to-agent interoperability for a single bounded system;
- implementing a technique merely to claim coverage of it.
