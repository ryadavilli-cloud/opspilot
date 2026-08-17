# OpsPilot Requirements

**What must OpsPilot accomplish and demonstrate, and what stays out?**

OpsPilot is an educational and portfolio capstone: an agentic incident-investigation assistant that
demonstrates a coherent set of important agentic-AI ideas through one believable, end-to-end
investigation of an authored incident. It is not a production incident-management platform, and it
is not measured as one.

This document states what OpsPilot must accomplish and demonstrate, and the properties that make it
trustworthy. It does not state how. Structure, components, execution mechanics, data and evidence
semantics, runtime realization, evaluation method, settled technical choices, and implementation
rules are each owned by their own document. Requirements names no library, framework, model,
database, query language, or transport, with one exception: Azure is the fixed hosting environment,
because that commitment is made here and portability is not a goal.

Identifiers here are stable references for the design set. They are not a decomposition to be
implemented one at a time.

---

## 1. Purpose and Value

When an operational alert fires, an on-call engineer typically spends the first fifteen to twenty
minutes gathering context before real diagnosis can begin: metrics and logs, recent changes,
dependencies, runbooks, and similar past incidents. The same visible symptom often has several
plausible causes, and the engineer must work out which one the evidence supports, what remains
uncertain, and what can safely be done now.

OpsPilot prepares that initial investigation and presents it as one concise, evidence-supported
brief that the engineer can question. It does not replace the engineer, does not guarantee a root
cause, and does not act on the environment it investigates.

The value being demonstrated is agentic: an investigation whose evidence path adapts to what it
finds, carried out by agents with distinct responsibilities, using tools and retrieved knowledge,
staying grounded and bounded throughout, and observable while it happens.

### Why the investigation must be adaptive

Many incidents are handled well by fixed dashboards and known-signature lookups, and OpsPilot does
not compete with those. Adaptive investigation earns its place where the right evidence path cannot
be known in advance: where one observation changes what should be checked next, and where a
conclusion requires correlating several kinds of evidence. OpsPilot targets exactly those scenarios,
and the authored corpus is built so that at least one shows an adaptive path outperforming a fixed
one.

---

## 2. Scope and Posture

OpsPilot is a bounded, repeatable investigation environment over a synthetic domain. It must work
coherently end to end and demonstrate its agentic capabilities working together. Its quality is
judged by how well those capabilities combine and how clearly a reviewer can see them, not by the
number of agents, frameworks, services, or protocols it uses.

It is read-only. It recommends; it never changes what it observes.

It must remain understandable, demonstrable, and buildable by one developer within a bounded
schedule and an individual-scale runtime budget. Grounding, read-only safety, bounded execution,
provenance, and repeatable evaluation must be real. Production availability, throughput, tenancy,
compliance, and operational breadth are outside its ambitions, and complexity that serves only those
ends is out of scope.

Complexity earns its place only where it materially supports the journey, an important agentic-AI
concept, grounding or read-only safety, a meaningful evaluation, or basic troubleshooting of the
demonstration.

---

## 3. Domain and Corpus

OpsPilot operates against **RetailEase**, a synthetic e-commerce microservices environment with a
service topology, operational knowledge, incident history, deployment records, dependency
relationships, and post-incident narrative. The synthetic environment is a feature of the capstone:
it makes every scenario reproducible and every answer checkable.

**R-1 Authored corpus.** The bounded primary domain is seven authored RetailEase incidents spanning
five overlapping incident families: resource saturation, downstream or external dependency failure,
deployment regression, cache failure or stale data, and queue backlog or consumer failure. Families
deliberately share alerts and visible symptoms, so OpsPilot must distinguish causes by evidence and
must never treat one alert name as one cause.

Evaluation additionally needs to exercise five scenario classes: a clear single-cause incident, an
incident with competing hypotheses, an incident with multiple contributing failures, an incident
where important evidence is unavailable, and a benign or transient condition where immediate action
is not justified. The seven authored incidents supply most of these; where a class is not naturally
present among them, a small controlled fixture may represent it. That fixture is part of the
evaluation corpus, not an eighth authored incident, and nothing here requires one.

**R-2 Evidence surface.** An investigation must be able to reach logs, metric observations,
deployment records, service dependencies, runbooks, postmortems, prior incidents and remediation
records, and structured operational tables. Evidence carries stable references so that citations
can be checked. How the corpus is structured and how expectations are recorded belong to
`evaluation.md`.

---

## 4. The Journey

An **investigation** is one bounded, adaptive evidence-gathering and synthesis run over one authored
incident, producing one investigation brief. Once complete, its record is retained and can be
questioned. There is one investigation per incident selection; nothing reopens or extends a
completed one.

**R-3 Start.** The engineer selects one authored RetailEase incident. Investigation begins
immediately, with no confirmation step and no free-text intake.

**R-4 Run.** The investigation runs adaptively within deterministic bounds while the engineer
watches its activity. It ends when the evidence is ready to interpret, when a bound is reached, when
required evidence is unavailable, or when the request carrying it disconnects. An investigation that
cannot produce, ground, persist, and deliver a trustworthy brief fails without producing one; a
failure is not a kind of result.

**R-5 Result.** The investigation delivers exactly one investigation brief, as defined in section 5.
It states honestly whether the evidence supported a conclusion, established part of the picture, or
was insufficient, and it never presents a best guess as an established finding.

**R-6 Question.** The engineer may ask a question about a completed investigation and receive an
answer drawn only from that investigation's retained record. A question gathers no new evidence,
introduces no new conclusion, and creates no new investigation. Where the record cannot answer, the
answer says so. A concise handoff or status summary derived from the same record is a preference,
not a requirement (section 10).

---

## 5. The Investigation Brief

**R-7 Purpose and shape.** The brief is the authoritative result of an investigation. It must be
concise enough to use during an active incident, lead with the most useful conclusion and next
action, and make supporting detail available without burying the conclusion in it. Presentation and
layout are design choices.

**R-8 Content.** The brief must communicate, concisely and where the evidence supports each:

- what appears to have happened: the incident, its timing, and what was affected;
- the leading candidate cause and, where warranted, credible alternatives, each with a qualitative
  support label rather than a number, and with the evidence that supports or weakens it;
- the most useful next check where one would distinguish the remaining candidates;
- important unknowns, missing or unavailable evidence, and contradictions;
- useful action: what to do or verify now, kept distinct from longer-term follow-up or prevention,
  and including "no immediate action is required" where the evidence supports that;
- relevant historical context, where it materially helps, shown separately from current evidence.

Where more than one failure contributes to an incident, the brief says so rather than forcing a
single cause.

**R-9 Honesty.** The brief distinguishes what was observed from what was inferred, states a causal
conclusion only where the evidence supports one, and states plainly when the evidence is
insufficient. An honest inconclusive result that names what is missing is a good result. Candidate
support is qualitative; OpsPilot never presents a probability that a cause is correct.

---

## 6. Agentic Capabilities

These are the capabilities OpsPilot exists to demonstrate. Each must be genuinely present and
visible end to end.

**R-10 Three agent responsibilities.** The investigation is carried out by three agents with
distinct, visible responsibilities: a Supervisor that sets the objective, coordinates the work, and
holds the bounds; an Evidence Investigator that decides what evidence to gather and gathers it
through approved sources; and an RCA Analyst that is the sole owner of analysis and produces the
brief's conclusions. Coordination between them is inspectable. How responsibilities are realized,
how agents communicate, and how work is sequenced are design choices.

**R-11 Adaptive investigation.** The evidence path adapts to what is found: which source to consult
next depends on the incident and on what has already been observed, and the investigation revises
direction when evidence weakens its current explanation. Different incidents must take demonstrably
different evidence paths. A fixed sequence of the same lookups for every incident does not satisfy
this.

**R-12 Analysis can redirect gathering.** When analysis identifies a material unresolved question
that available evidence can still answer, it can redirect gathering to answer it, within the
investigation's deterministic bounds. This is what makes the RCA Analyst part of the investigation
rather than a formatter at the end of it. It is not a general re-investigation mechanism.

**R-13 Model-directed tool use.** Agents choose which approved read-only tools to use and with what
arguments, across several evidence source types. Every tool result carries an explicit outcome the
system can act on.

**R-14 Retrieval that influences the investigation.** OpsPilot retrieves relevant runbook,
architecture, and past-incident knowledge in a way that handles both meaning and exact operational
identifiers, such as service names, error codes, and deployment identifiers, well enough to be
trusted on them. Retrieved knowledge must demonstrably influence what the investigation checks or
concludes; retrieval that only decorates a finished result does not satisfy this. Retrieved
knowledge informs interpretation and can never by itself establish the cause of the current
incident.

**R-15 Governed structured querying.** OpsPilot can answer natural-language questions about
structured operational data through a bounded, read-only query capability over an approved surface,
deterministically validated before anything executes, and never usable as a general database
assistant. What it returns becomes evidence with provenance like any other observation.

**R-16 One real protocol boundary.** At least one genuine investigation capability is additionally
exposed through a real MCP boundary, with the same read-only behavior, the same permissions, and the
same semantics as the direct path. This demonstrates the protocol; it does not make OpsPilot a
protocol platform.

**R-17 Observable agent activity.** While an investigation runs, and afterwards from its record, the
engineer can understand which agent or capability is acting, what meaningful action it is taking,
what evidence, retrieval, or tool result it obtained, why the investigation continued or stopped,
and how the final result rests on its evidence. Activity is a compact projection of meaningful
events, not a transcript, and it never exposes hidden model reasoning. A plain chat window that
hides the agentic system does not satisfy this; production polish is not required.

---

## 7. Trust and Safety

These properties define trustworthy behavior. Losing any of them is a defect, not a simplification.

**R-18 Read-only.** Operational access is read-only on every path, including the protocol boundary,
under every configuration. No path can mutate what OpsPilot observes.

**R-19 Grounded.** Every material claim about the incident resolves to evidence gathered during the
investigation, and every citation resolves to a stable reference. Recommendations show whether they
came from retrieved guidance or from general practice.

**R-20 No fabrication.** A tool that fails, times out, is unavailable, or is refused produces a
stated limitation, never a fabricated observation. Missing, unavailable, sparse, or contradictory
evidence is disclosed rather than smoothed over.

**R-21 Result distinctions preserved.** OpsPilot preserves, and shows, the difference between a
source that returned evidence, one that answered and found nothing, one that answered partially, and
one that could not execute or answer.

**R-22 Contradiction preserved.** Contradictory observations are kept and shown; they are not
overwritten or resolved away.

**R-23 Untrusted content.** Retrieved content, tool output, incident text, and engineer text are
data and never instructions.

**R-24 Bounded.** Execution runs within deterministic limits that code enforces and that no agent
can extend, reset, or widen. Reaching a bound never turns insufficient evidence into a conclusion.

**R-25 Isolation.** Unrelated investigations do not contaminate one another.

**R-26 Basic hygiene.** Identity and secret handling are sound at a basic level, and the application
holds only the data access it needs.

---

## 8. Evaluation

Evaluation exists to show that development was deliberate, that OpsPilot's important claims hold,
and that the capstone demonstrates how agentic systems are evaluated. It runs offline against the
authored corpus and fixtures, informs rather than gates, and certifies nothing about production
suitability. No numeric threshold is set before a measured baseline exists, and no published figure
is a service-level commitment. It is reproducible enough that a meaningful prompt or model change
can be compared before and after.

Two kinds of evaluation are kept distinct. Where correctness can be determined mechanically, it is
determined by code. Where quality requires semantic judgement, an offline model-assisted judge
supplies it. Neither is a runtime authority.

**R-27 Scenario behavior.** Each authored incident and evaluation fixture carries an authored
expectation of what a correct investigation establishes. Evaluation reports, per scenario, whether
OpsPilot reached a reasonable diagnosis, handled ambiguity honestly, recognized multiple
contributors where they exist, admitted insufficient evidence where appropriate, and recommended no
immediate action where none is justified. Failures are named.

**R-28 Grounding and deterministic correctness.** Evaluation checks mechanically that cited
references resolve, that material incident claims have admitted support, that no prohibited
operational write occurred, and that structured-query results match expected results.

**R-29 Adaptive value.** A simple fixed-path baseline, using the same tools in a predetermined
order, exists for comparison, and at least one authored scenario shows adaptive investigation
reaching a better result than the fixed path. This is the falsification test for OpsPilot's central
claim; it is not a benchmark across every incident.

**R-30 Retrieval influence.** For scenarios where relevant knowledge is expected, evaluation
demonstrates that retrieved knowledge materially influences an investigation action, hypothesis,
interpretation, or recommendation. At least one suitable scenario must demonstrate this influence
against the same investigation without that retrieval influence. Retrieval is not required where
the scenario does not need it.

**R-31 Model-assisted judgement.** An offline judge evaluates the qualitative aspects of completed
investigation output against an authored rubric or expected scenario: whether the brief is useful
and coherent, whether uncertainty is communicated appropriately, whether the diagnosis is well
explained in context, and whether recommendations fit the established situation. It complements the
deterministic checks, is advisory, runs offline, and is never a runtime authority. One judge path
and one authored rubric are enough.

---

## 9. Runtime and Deployment

**R-32 Local and hosted.** OpsPilot runs locally for development and evaluation, and runs in Azure
for a repeatable hosted demonstration. It may start on demand; ordinary demonstration downtime
implies no availability commitment.

**R-33 Retention.** A completed investigation, its brief, and the evidence needed to resolve its
citations are retained and remain readable, so that questions can be answered and evaluation can run
against them. Losing an in-progress investigation on restart is acceptable; it is simply run again.

**R-34 Basic observability.** Agent, tool, model, and retrieval activity for one investigation is
correlated end to end well enough to understand and troubleshoot a demonstration from its logs and
telemetry, and the application reports basic health and fails in legible ways. This is a practical
troubleshooting baseline, not production observability.

---

## 10. Preferences

These may be pursued after the primary journey works end to end. They create no obligation on any
other document unless promoted here first.

- **A concise handoff or status summary** derived from a completed investigation's record.
- **Parallel execution of independent evidence actions**, where it is cheap and does not complicate
  bounds, failure handling, or the activity view.
- **A verification signal for an immediate mitigation**: what to observe to confirm it worked.
- **A developer view** exposing model and prompt metadata, structured model outputs, detailed tool
  requests and responses, trace identifiers, basic usage figures such as latency and approximate
  cost, and evaluation results, as progressive disclosure within the primary interface.
- **Extending the R-31 rubric to entailment**: whether each cited piece of evidence actually
  supports the claim it is attached to.
- **Query rewriting or expansion; context compression; lightweight caching; a self-critique pass.**

---

## 11. Deferred and Non-Goals

Deferred, and not to be designed for unless promoted:

- restart-resumable investigations;
- long-term memory across investigations;
- learning from engineer corrections;
- a held-out generalization probe on unfamiliar evidence.

Non-goals:

- autonomous remediation or any operational write, and approval gates for writes, since there are
  none;
- incident detection, webhook ingestion, or replacement of monitoring and incident-management
  platforms;
- free-text incident intake and clarification; redirecting an investigation; engineer-supplied
  evidence; explicit cancellation controls beyond disconnect handling;
- support for arbitrary incidents or environments, or coordination of several incidents;
- a general-purpose multi-agent platform, agent-to-agent interoperability, or exposing more than the
  demonstration needs through MCP;
- production availability, disaster recovery, scalability, tenancy, compliance certification,
  service-level commitments, or production-scale performance and cost optimization;
- calibrated root-cause probabilities;
- a large production-like corpus;
- voice or multimodal interaction, fine-tuning, learned sparse retrieval, canary and rollback
  workflows, drift detection;
- implementing any technique merely to claim coverage of it.
