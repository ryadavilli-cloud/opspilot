# OpsPilot - Data and Evidence

**What information does OpsPilot trust, preserve, cite, and use to support an investigation brief?**

## 1. Purpose and Document Boundaries

This document defines one common language for the information that flows through an investigation:
what may be trusted, what may support which kind of claim, how an observation becomes citable
evidence, what an assessment and a brief mean, and what a completed turn preserves.

It owns information trust categories, the identity and reference model, tool-result meaning,
evidence admission and evidence semantics, retrieved-knowledge semantics, temporal semantics,
evidence types, candidate and assessment meaning, citation and grounding semantics, recommendation
provenance, brief and handoff meaning, completed-turn artifact semantics, and the data invariants
that downstream documents must preserve.

It does not own behavior, structure, or realization. Component responsibilities, conceptual
interfaces, and which boundary produces or consumes each artifact belong to `system-design.md`.
Stages, routing, loops, bounds, correction behavior, stop reasons, outcome
transitions, and when persistence occurs belong to `workflow-design.md`. Physical persistence,
storage products, serialization, trace backends, telemetry schemas, retention, and raw-result
storage belong to `runtime-and-deployment.md`. Ground truth, scenario schemas, scoring, metric
formulas, and judge behavior belong to `evaluation.md`. Concrete model classes, validation
implementation, adapter rules, and test requirements belong to `code-guidelines.md`.

Nothing here specifies a physical schema, a storage product, an encoding, or an interface format.

---

## 2. Information Trust Model

Not everything available to an agent is evidence. Each piece of information sits in one category,
and the category determines what it may be used for.

| Category | Origin | May it directly support an incident-specific claim? |
| --- | --- | --- |
| Incident input | The engineer, at intake | No. Untrusted content that frames the question |
| Engineer follow-up text | The engineer, after a turn completes | No. Untrusted input that never becomes evidence |
| Tool operation | An attempt against an approved capability | No. It records what was tried, not what is true |
| Tool observation | A source result, before admission | Not yet. It is a candidate for admission |
| Admitted operational evidence | Deterministic admission into the turn | Yes. This is the only current operational proof |
| Retrieved knowledge | Runbooks, service knowledge, prior incidents | Interpretation, historical claims, and recommendation provenance only |
| Working hypothesis | An agent, while deciding what to check next | No. It guides gathering and is never cited |
| Agent interpretation | A model summarizing or explaining | No. It explains evidence and is not evidence |
| Candidate assessment | The RCA Analyst | It is the claim, not its support |
| Investigation brief | Rendering of the assessment | The delivered result for one turn |
| Handoff summary | Derivation from retained state | A restatement; it introduces nothing new |
| Trace and evaluation references | Instrumentation and offline scoring | No. They describe the run, not the incident |

Four boundaries in that table carry most of the weight.

**Engineer input is untrusted.** Incident text and anything supplied later may contain speculation,
an asserted cause, or instructions. It is data the investigation reasons about, never direction the
agents follow (NFR-9).

**A tool observation becomes evidence only through deterministic admission** (§6). Passing through a
schema does not make a source result trusted.

**Models do not create evidence.** Model output may propose a tool action, formulate a structured
query, summarize an observation, rank candidates, identify a further-evidence need, or draft an
assessment or brief. None of that becomes evidence by being structured, plausible, or repeated. An
agent that describes an observation has not produced one (NFR-2, NFR-10).

**Retrieved knowledge is not current proof.** It may supply terminology, known failure patterns,
investigative direction, historical statements, and recommendation provenance, and it can never
independently establish the cause of the current incident (FR-67, FR-94).

---

## 3. Identity and Reference Model

Five identities exist. They are the smallest set that supports citation resolution, investigation
isolation, provenance, and deterministic checking (NFR-3, NFR-12, NFR-15).

| Identity | Identifies | Primary use |
| --- | --- | --- |
| Investigation identity | One incident under study | Scoping, isolation, attribution of every retained artifact |
| Turn identity | One bounded cycle within an investigation | Attribution of evidence, assessment, and brief to the turn that produced them |
| Operation reference | One logical tool, retrieval, structured-query, or protocol operation within a turn | Correlation, duplicate-action detection, operation history, retry attribution, evidence provenance |
| Evidence reference | One admitted operational observation | The reference an incident-specific citation points at |
| Knowledge reference | One retrieved passage or historical item used as context | The reference a historical or contextual citation points at |

A turn identity is not a session identity. A live session is the ephemeral conversational surface
over an investigation and has no identity of its own.

**Operation reference and evidence reference are distinct.** The operation reference answers what
was attempted; the evidence reference answers what was observed and where it came from. One
operation may produce one admitted observation, several, or none. A citation never points only at an
operation reference, because an operation is not an observation.

**Evidence and knowledge references must be typed and stable** enough to resolve after the completed
turn is persisted, to distinguish source category, and to support deterministic citation checking
(NFR-3, NFR-15). Their encoding, prefixes, key structure, and physical form are not specified here.

The reference type is what makes role compatibility decidable without judgment. An evidence
reference may occupy any citation role; a knowledge reference may occupy only the historical or
contextual role (§13). A grounding check can therefore reject an incompatible pairing by inspecting
the reference type alone.

No other identity exists. In particular there is no session identity, no report version, no
content hash, no publication identity, no review-decision identity, no checkpoint identity, and no
memory identity. Candidates are ordered within one assessment and need no identity of their own.

---

## 4. Capability Request and Result Semantics

One canonical result model covers every approved capability: direct operational tools, knowledge
retrieval, governed structured query, and the protocol boundary. There is no path-specific result
model, and no evidence concept named after an access path.

Every request carries the investigation and turn identity, the operation reference, the capability
being invoked, its validated parameters and scope, and the deadline within which it must complete.

Every result answers two independent questions: did the operation execute, and if it did, how
complete was the answer (NFR-7).

### Execution outcome

| Value | Meaning |
| --- | --- |
| `succeeded` | The operation ran and returned a trustworthy response |
| `timed_out` | The operation did not finish within its permitted time |
| `unavailable` | The source could not be reached |
| `rejected` | The request failed policy or validation at the boundary |
| `failed` | The operation ran and errored, producing no trustworthy answer |

### Completeness

| Value | Meaning |
| --- | --- |
| `complete` | The full answer available for the requested scope |
| `empty` | The scope was queried authoritatively and contains no matching observations |
| `partial` | Usable but incomplete: truncated, capped, or covering part of the scope |
| `not_applicable` | No successful result exists, so completeness cannot be assessed |

### Allowed combinations

| Execution outcome | Allowed completeness |
| --- | --- |
| `succeeded` | `complete`, `empty`, `partial` |
| `timed_out` | `not_applicable` |
| `unavailable` | `not_applicable` |
| `rejected` | `not_applicable` |
| `failed` | `not_applicable` |

Any other pairing is invalid and is a defect in the adapter that produced it.

### What the values mean in practice

`succeeded` with `empty` is a positive finding, not a failure. The source was reachable and
authoritative and reports nothing matching. "No error logs for this service in this window" is an
observation that can rule a hypothesis out, and it is admitted as evidence.

`succeeded` with `partial` is usable with its limit attached. The observation participates in
reasoning, and its incompleteness travels with it, so a claim resting on it must acknowledge that
the unseen remainder could change the picture.

`unavailable` means the source did not answer at all. This is the value that must never be read as
"nothing was found." Confusing it with `succeeded` and `empty` turns an unreachable source into a
clean bill of health, and that single confusion is the reason the two axes exist (NFR-7).

`timed_out`, `rejected`, and `failed` likewise produce limitations, not observations (NFR-8).

Provider-specific statuses, error codes, and partial-result conventions are translated inside the
adapter that owns the source. Only these two axes cross the Evidence Access boundary. A raw
exception, stack trace, or provider status is never evidence, never reaches a prompt as tool
content, and never enters an admitted observation.

---

## 5. Tool-Operation History and Limitations

The turn keeps a record of what it attempted, separate from what it observed. Both are ephemeral
while the turn runs.

For each attempt the history preserves the operation reference, the capability used, the validated
request scope, the execution outcome, the completeness, timing, and whether admission followed.

Keeping this apart from the admitted evidence matters because the two answer different questions.
The evidence can then be read as "what was observed" without filtering, while refusals, timeouts,
and unreachable sources stay visible where they are actually needed: in what the investigation still
does not know, and in the limitations a brief must disclose.

An operation that did not answer produces an operation record and a **limitation**, and no evidence
(FR-68, FR-69, NFR-8). A limitation names what could not be established and why, in terms of the
question it was meant to answer. The workflow never fabricates an observation to stand in for a call
that did not answer.

At turn completion, the operation information needed for traceability travels with the completed
turn or with its trace reference. There is no separate durable operation store.

---

## 6. Evidence Admission

Admission is the deterministic boundary between a source result and the turn's admitted evidence. It
is code inside the Evidence Access Layer, not agent judgment, and it is the only way into the
evidence set. Every capability uses it, so a structured-query result and a result reached through
the protocol boundary are admitted exactly as a direct tool result is.

Admission verifies that:

- the result belongs to the current investigation and turn;
- provenance is present and identifies the source;
- the content is a meaningful observation, or an authoritative empty one;
- required temporal information is preserved where the observation will bear on timing (§10);
- the same operation has not already produced this admitted item in this turn;
- a stable evidence reference can be assigned;
- untrusted-content handling has been applied.

Admission does not re-establish what the boundary already settled. Whether the operation was
permitted is decided by dispatch before it executes (`system-design.md` §8.1), and whether execution
outcome and completeness form a legal pairing is decided by the adapter that produced the result
(§4). Admission reads both as given and decides only whether the result may become evidence.

Only a result whose execution outcome is `succeeded` may be admitted. A `succeeded` and `empty`
result is admitted, because an authoritative absence is a real observation about the scope that was
queried. A `succeeded` and `partial` result is admitted with its incompleteness preserved and
carried forward.

Everything else produces an operation record and a limitation.

Admission assigns the evidence reference. It does not score, rank, weight, or judge the observation,
and nothing about it constitutes approval of a conclusion.

---

## 7. Admitted Evidence Set

The **admitted evidence set** is the collection of operational observations admitted during one
turn. It is the only source of current operational proof, and it is what an incident-specific
citation resolves against.

During the turn it is ephemeral. It becomes durable only as part of the completed-turn artifact
(§17), written by the Supervisor at turn completion. Nothing is written to the Investigation Record
while the turn is still running, so the evidence set leaves behind no orphan records and no
provisional evidence store. What an incomplete turn leaves behind belongs to `workflow-design.md`.

Each admitted observation preserves:

| Element | Purpose |
| --- | --- |
| Evidence reference | Stable identity for citation and resolution |
| Investigation and turn identity | Attribution and isolation |
| Producing operation reference | Provenance back to what was attempted |
| Evidence type | What kind of observation this is (§11) |
| Source | Which capability and which underlying source produced it |
| Affected entity | The service, resource, or dependency observed, where applicable |
| Observation time or window | When the observed thing happened, where applicable (§10) |
| Normalized observation | The observation in canonical form |
| Completeness | `complete`, `empty`, or `partial` |
| Provenance | Enough to locate and re-inspect the original source |
| Limitations | Known caveats, including what a partial observation omits |

Raw source output is not retained. The admitted observation is what survives, carrying its
normalized content, its provenance, and a stable evidence reference, and nothing downstream needs
the original payload once that exists. Provenance locates the source for re-inspection; it is not a
pointer into a stored copy of the response.

### Invariants

1. Agents cannot create evidence. Only admission writes into the evidence set.
2. A model summary or interpretation is not evidence, however well formed.
3. An operation that did not answer is a limitation, never an observation.
4. A `succeeded` and `empty` observation stays distinguishable from an `unavailable` source.
5. A `partial` observation stays marked partial wherever it travels.
6. Contradictory observations remain separate records; neither overwrites the other (FR-63, NFR-6).
7. Evidence belonging to another investigation can never be cited (NFR-12).
8. Evidence cited by a persisted completed turn remains resolvable for as long as that turn is
   retained (NFR-3, NFR-58).
9. Evidence is persisted only as part of a completed turn (NFR-55).
10. A lost in-flight turn leaves no durable evidence, and the turn is simply run again (NFR-57).

---

## 8. Engineer Input and the Evidence Boundary

Engineer text reaches the system as a follow-up question. It is untrusted input, and stating
something never makes it evidence. Calling something evidence does not admit it (NFR-9).

A question may name an incident detail, assert a cause, or quote an excerpt. None of that enters the
evidence set: an answer is drawn from what the investigation already admitted, and a statement in a
question cannot support a grounded element.

There is no manual-evidence approval path and no way to inject an observation the Evidence Access
Layer did not produce.

---

## 9. Retrieved Knowledge

Retrieved knowledge covers runbook passages, architecture and service knowledge, postmortems, and
prior incidents with their recorded remediation history (FR-89, FR-92).

Each retrieved item preserves:

| Element | Purpose |
| --- | --- |
| Knowledge reference | Stable identity for contextual and historical citation |
| Source identity and type | Which document or incident it came from, and which class of source |
| Matched passage or historical content | The text or record that actually reached the reasoning context |
| Retrieval purpose | The question or reason it was retrieved for |
| Relevance information | Enough ranking or match detail for traceability |
| Provenance | Enough to locate the original item |

**The matched content itself must reach the reasoning context.** A result reduced to a document
identifier is not usable, because an agent cannot reason over a pointer. Retrieval that returns only
identifiers has ranked something without supplying knowledge (FR-89, NFR-32).

### Current proof versus historical context

Operational evidence supports claims about the current incident. Retrieved knowledge supports
interpretation, terminology, known failure patterns, investigative direction, explicitly historical
claims, and recommendation provenance.

Retrieved knowledge cannot independently establish the cause of the current incident (FR-67, FR-94).
A past incident that resembles this one is a lead to verify against current signals, never a stored
answer to adopt. A conclusion therefore requires current operational evidence in addition to
whatever knowledge informed it.

Historical comparison is reported as what it is: how a prior occurrence resembles or differs from
this incident (FR-27). It is presented separately from current support and is never converted into a
probability that a candidate is correct for this incident (FR-26).

Two terms are used strictly throughout this document set. **Operational evidence** means observations
of the current incident admitted to the evidence set. **Retrieved knowledge** means runbooks,
service knowledge, and historical context. A retrieved passage is never called operational evidence.

---

## 10. Temporal Semantics

Time appears in several senses. Conflating them is how a coincidence becomes a fabricated causal
ordering, so the model carries only what is needed to prevent that.

| Concept | Meaning |
| --- | --- |
| Event time | When the observed thing actually happened |
| Observation window | The interval an observation covers or aggregates over |
| Collection time | When the investigation retrieved the observation |

Two rules follow:

- Collection time is never substituted for event time. Retrieval lag says nothing about when the
  observed thing happened.
- An observation used to support a timing or causal-order claim must carry an event time or an
  observation window.

An observation that carries neither may still be admitted and used as context, and it cannot support
a timing or causal-order claim. That is a test for the presence of a field, not a judgment about
what the observation means.

These rules are authoring obligations on the assessment. Whether a brief's stated ordering is
coherent is a semantic judgment, assessed offline by the judge's causal-ordering dimension against
the times the cited evidence carries (`evaluation.md`). It is deliberately not a runtime grounding
check; the gate's four checks do not inspect temporal fields.

---

## 11. Evidence Types

An evidence type describes what was observed. It is a compact vocabulary, not a taxonomy to be
extended per source or per scenario.

| Type | Typical content |
| --- | --- |
| Incident or alert observation | The reported condition and correlated alerts |
| Log event | Discrete log records from a service |
| Metric observation | A value, series, or aggregate over a window |
| Deployment or change observation | A release, rollback, or configuration change record |
| Dependency or topology observation | Relationships between services and resources |
| Structured operational record | Tabular operational or ticket-shaped data about an incident |
| Service-health observation | Availability or degradation state of an entity |

**Type describes meaning, not access path.** How an observation was reached is provenance, recorded
on the observation, and it never becomes the type. There is no protocol-boundary evidence type, no
structured-query evidence type, and no retrieval evidence type. A structured operational record
reached through the governed query path and the same record reached another way are the same kind of
observation (FR-100).

No incident requires every type. A universal checklist would force irrelevant gathering on some
incidents and under-serve others. Which evidence a given incident family should be expected to
produce is a scenario expectation and belongs to `evaluation.md`.

---

## 12. Candidate Assessment

The RCA Analyst produces exactly one authoritative assessment per turn (FR-79). It is the structured
synthesis from which the brief is rendered, and no other component produces a competing one.

The assessment can represent:

| Element | Meaning |
| --- | --- |
| Turn objective | What this turn set out to establish |
| What happened | The incident, its timing, the affected entities, and the observed impact |
| Leading candidate | The best-supported current explanation |
| Supported alternatives | Other explanations the evidence keeps open |
| Support labels | The qualitative label carried by each candidate |
| Supporting evidence references | Evidence that supports a candidate |
| Weakening evidence references | Evidence that weakens or contradicts a candidate |
| Unresolved discriminator | The check that would most usefully separate the remaining candidates |
| Relevant retrieved knowledge | Knowledge that informed interpretation |
| Historical comparison | How this incident relates to prior occurrences |
| Limitations and unknowns | What could not be established, and why |
| Recommendations | The actions proposed, by horizon (§14) |
| Conclusion disposition | Whether a supported causal conclusion may be stated |

### Grounded elements

Grounding attaches to these elements rather than to sentences. A **grounded element** carries its own
evidence or knowledge references, and where it can be asserted at more than one strength, an explicit
marker distinguishing **established** from **possible**.

| Grounded element | References it carries | Strength |
| --- | --- | --- |
| What happened | Current operational support for the incident, its timing, the affected entities, and the observed impact | Established or possible |
| Leading candidate | Supporting and weakening references; contextual references where retrieved knowledge informed it | Established or possible |
| Each supported alternative | Supporting and weakening references | Always possible |
| Each supporting or weakening reference | The reference is itself the element | Not applicable |
| Historical comparison | Historical or contextual support | Always possible |
| Each recommendation | A knowledge reference where its provenance is runbook or prior-incident (§14) | Not applicable |

An element marked **established** is one the brief presents as current fact. An element marked
**possible** is one the brief presents as open. Only established elements require current operational
support (NFR-2). An element explicitly about history may rest on retrieved knowledge instead.

Where a candidate asserts that its proposed cause preceded the effect it explains, that ordering is
part of the candidate and rests on the candidate's own supporting references, which must carry the
temporal information §10 requires.

The remaining elements ground nothing and carry no references: the turn objective, the support
labels, the unresolved discriminator, the limitations and unknowns, and the conclusion disposition.
Each either restates the turn's own state or names what is absent, and neither asserts a fact about
the incident.

### Qualitative support labels

Exactly three labels exist (FR-24):

- **Leading** is carried by the single best-supported current explanation.
- **Plausible** is carried by an alternative the evidence keeps genuinely open.
- **Weakly supported** is carried by an alternative that survives but rests on thin support.

There are no numeric evidence scores, no percentages, no probabilities, no calibrated confidence,
and no hidden model-confidence value anywhere in the assessment. Model confidence is not a form of
support and carries no weight in whether a conclusion may be stated.

### Support relationships

An evidence reference relates to a candidate in one of three ways: it **supports** it, it **weakens
or contradicts** it, or it is **contextual only**. Relationships carry no weights and form no scored
graph.

Contradictory evidence is preserved and attached to the candidate it bears on rather than dropped to
make the assessment read cleanly (FR-63, NFR-6). A contradiction may be resolved by later evidence,
explained as a difference of scope or window, retained as a stated limitation, or be the reason the
turn cannot support a conclusion.

### One assessment, not several conclusions

Ranking candidates does not create several authoritative conclusions (FR-82). Where the evidence
supports a causal conclusion, that conclusion is the leading candidate presented as such.

Where more than one contributing failure is needed to explain the incident (FR-65), the assessment
represents that as one explanation with its contributing factors named, or as one leading candidate
with its contributing conditions stated explicitly. It never becomes two competing conclusions.

### Supported conclusion versus insufficiency

A **supported causal conclusion** means the admitted operational evidence supports the leading
explanation strongly enough for the brief to present it as the current conclusion (FR-25).

**Insufficient evidence** means the opposite, and is a legitimate result rather than a failure. It
may establish the effect, may leave one or more candidates plausible, and states that current
evidence does not support presenting any of them as established, naming what is missing or
contradictory (FR-23, FR-62).

Model confidence cannot convert insufficiency into a supported conclusion. What a given incident
family should be expected to produce before a conclusion is credible is a scenario expectation owned
by `evaluation.md`, not a runtime policy defined here.

---

## 13. Claims, Citations, and Grounding

### What is grounded

What an engineer would act on or be misled by is carried by the grounded elements of §12 and §14,
not by sentences a reader must classify as material. Each such statement has a structure holding it:

- the cause is the leading candidate and each supported alternative;
- the affected entity and the impact are part of what happened;
- the incident's timing is part of what happened, and a candidate's cause-to-effect ordering is part
  of that candidate;
- a significant supporting or contradicting observation is the supporting or weakening reference
  itself;
- why an immediate operational recommendation follows is the candidate or observation the
  recommendation responds to, together with its provenance (§14).

Each grounded element carries its own references and, where it can be asserted at more than one
strength, its established-or-possible marker (§12). Every element marked established must resolve to
admitted operational evidence (NFR-2); an element explicitly about history may rest on retrieved
knowledge instead. A recommendation drawn from general operational practice is identified as such
rather than attached to current evidence it does not rest on.

The brief renders from these structures and cannot assert what they do not contain (§15). Connective
prose, restatement of the incident input, and clearly marked uncertainty assert nothing about the
incident and carry no references.

### Citations

A citation identifies the evidence or knowledge reference being cited, the grounded element it
attaches to, and the role it plays. Exactly three roles exist:

| Role | Asserts |
| --- | --- |
| Current operational support | This admitted evidence supports the element's assertion about the current incident |
| Current operational contradiction | This admitted evidence weakens or contradicts the element, and is disclosed |
| Historical or contextual support | This informed interpretation or supports an explicitly historical element |

The set is deliberately small. A larger citation vocabulary invites relabeling, and relabeling is how
a deterministic grounding check becomes negotiable.

A role a source cannot support is inadmissible. Retrieved knowledge cannot carry current operational
support, because a document cannot observe the running system.

Recommendation provenance is not a citation role. It is a field of the recommendation itself, with
its own three categories (§14).

Citation formatting, rendering, and linking are presentation concerns and are not specified here.

### The four grounding checks

The four grounding checks require the following evidence and citation semantics. The Supervisor's
grounding gate executes them before a brief is delivered; this section defines the information each
one needs, while the gate's routing, the correction allowance it spends, and what happens when a
brief persistently fails belong to `workflow-design.md`.

Each is a test over structure. None inspects prose, and none asks whether evidence semantically
supports what it is attached to. None re-checks admission either: everything a reference can resolve
to was admitted under §6, so turn and investigation membership is already established when the gate
runs.

**Reference resolution.** Every cited reference resolves to something the turn admitted, and carries
a reference type compatible with the role it occupies (NFR-3, NFR-35). Compatibility is a lookup,
not a judgment: a knowledge reference can never occupy a current-operational-support role (§3).

Whether the cited evidence semantically supports the element it is attached to is deliberately not
checked here. That judgment is entailment, it cannot be computed, and it belongs to the offline judge
in `evaluation.md`, which scores completed turns and never gates delivery.

**Unsupported-element rejection.** Every grounded element marked established carries at least one
current-operational-support reference (NFR-2). This is an enumeration over the grounded elements of
§12 and §14, not an inspection of the rendered text.

**Recommendation-provenance presence.** Every recommendation carries exactly one of the three
provenance categories, and carries a knowledge reference where that category is runbook guidance or a
prior-incident action (FR-38, NFR-4).

**Required limitation disclosure.** Every limitation recorded in turn state appears in the
assessment's limitations (FR-62, NFR-5). The gate compares two sets and does not judge which
limitations matter. Disclosing a limitation that turns out not to have mattered is not a failure;
omitting one that was recorded is.

Contract validity is not one of these. Whether model output parses into a valid structure is settled
before the grounding checks run, as part of structured model-output admission.

No further grounding check exists. Incident-family evidentiary expectations are scenario
expectations owned by `evaluation.md` and are deliberately not runtime checks.

---

## 14. Recommendations

Recommendations are advisory. Nothing in OpsPilot executes one, and no recommendation implies an
operational write (FR-75, NFR-1).

Every recommendation is placed in exactly one horizon (FR-34):

| Horizon | Purpose |
| --- | --- |
| Now | Reduce immediate impact, confirm whether intervention is needed, or explain why none is justified |
| Soon | Stabilize, verify a mitigation, gather remaining evidence, or determine escalation and coordination needs |
| Later | Reduce recurrence through code, configuration, capacity, resilience, observability, alerting, or follow-up work |

Each recommendation preserves:

- the action;
- its horizon;
- the candidate or observation it responds to (FR-35);
- its provenance;
- whether it is mitigation, verification, or longer-term prevention (FR-36).

Where an immediate mitigation is recommended, the recommendation states what should be observed to
confirm it worked (FR-37).

Provenance is a field of the recommendation, not a citation role, and it is exactly one of three
categories (FR-38):

- **Retrieved runbook guidance**, which carries the knowledge reference for the runbook passage;
- **Prior-incident action**, which carries the knowledge reference for the recorded prior incident;
- **General operational practice generated by the model**, which carries no reference and is
  labelled as such.

Provenance and its reference are therefore checkable together: where provenance is runbook guidance
or a prior-incident action, a knowledge reference is present; where it is general operational
practice, none is.

The third category is honest rather than weak. Recommending something sensible that no runbook or
prior incident supports is legitimate, and presenting it as though evidence backed it is not.

---

## 15. Investigation Brief

The investigation brief is the concise user-facing rendering of the assessment (FR-9). It is a
rendering, not a second analysis: it presents what the assessment contains, and it cannot introduce
a candidate, a relationship, a recommendation, or a conclusion the assessment does not hold.

Because it renders from the grounded elements of §12 and §14, it cannot present as established
anything those elements do not mark established, and it cannot attach support that they do not
carry. Presenting an element more strongly than its marker allows is a rendering defect, not a
grounding outcome.

The constraint is symmetric. A brief may not omit, reorder, or alter what the assessment holds any
more than it may add what the assessment does not. Candidate ordering, the evidence relationships
attached to each candidate, the recorded limitations, and the provenance carried by each
recommendation survive rendering unchanged. A brief that drops a weakening observation or a recorded
limitation asserts more than the assessment supports, exactly as one that invents a candidate does.

What a brief may vary is presentation: which sections are visible at once, how detail is disclosed,
and how citations are formatted (§13). Holding content behind progressive disclosure is presentation
and is required (FR-11, FR-12). Omitting a section the assessment left empty is presentation.
Removing, reordering, or rewriting content the assessment holds is not.

It leads with the most useful current conclusion and next action, and exposes the rest through
progressive disclosure (FR-11, FR-12). Its logical sections are:

1. Current conclusion and next action
2. What happened
3. What may be causing it
4. Supporting and weakening evidence
5. What remains unknown
6. What history says
7. What to do: Now, Soon, Later
8. Sources, limitations, and diagnostics available on demand

These are sections of one brief, not eight separately persisted objects.

One brief exists per turn, and it is never edited in place; a later change in analysis appears as
the brief of a later turn.

### Complete

A complete brief covers the turn objective, presents the supported assessment, discloses the
limitations the turn recorded, and passes the four grounding checks (FR-39).

### Partial

A partial brief reports what was established before the turn stopped, whether through a bound, a
degraded source, or an application interruption. It states plainly that it is incomplete
and names what was not reached, and it never claims more completeness than the turn achieved
(FR-40).

### Inconclusive

An inconclusive brief states that current evidence cannot support a cause and names what is missing
or contradictory. It may keep the ordered candidates visible as unresolved possibilities, and it
never presents a best guess as established (FR-41).

Which shape a brief takes follows from the turn state and the assessment. The four grounding checks
verify that the brief represents that shape correctly; they do not choose it.

Complete, partial, and inconclusive all describe delivered briefs that passed those checks. A brief
that still fails the checks after its one permitted correction is not a partial or inconclusive
brief; it is not delivered at all, and the attempt leaves no completed turn behind.

---

## 16. Handoff Summary

A handoff or status summary is a secondary output produced as a deterministic projection of
retained structured state (FR-10, FR-74). It restates; it does not investigate, and producing it
calls no model.

It may render only what retained state already holds: the current incident and its impact, the
latest turn objective and outcome, the leading candidate or the inconclusive state, the most
important supporting and contradicting evidence, the open questions, the Now/Soon/Later
recommendations, the material limitations, and the evidence and knowledge references attached to
them.

It opens no evidence-gathering turn, introduces no evidence, creates no new synthesis, changes no
candidate ranking, adds no recommendation, and does not replace the brief. Because it renders only
retained grounded elements with their existing references, its citation obligations hold by
construction. When it is produced belongs to `workflow-design.md` ("Follow-up").

Where a handoff summary is retained, it is retained with the investigation. It has no separate
identity and no persistence model of its own.

### Follow-up answers

A follow-up answer is likewise derived from retained state (FR-6, FR-71). It may cite retained
evidence and knowledge references; it creates no evidence, is not another assessment or brief, and
never alters the completed-turn artifact it draws on. Where retained state cannot answer the
question, the answer says so. Its production, model task, and the deterministic follow-up answer
validation it must pass belong to `workflow-design.md` ("Follow-up").

---

## 17. Completed-Turn Artifact

One logical artifact records a completed turn. The Supervisor commits it at turn completion, and it
is the only thing a turn leaves behind (NFR-55).

It carries:

- the investigation and turn identity;
- the turn objective;
- the terminal outcome;
- the reason gathering stopped;
- the admitted evidence set for that turn;
- the retrieved-knowledge references actually used;
- the final structured assessment;
- the delivered investigation brief;
- the material limitations;
- the follow-up context relevant to that turn;
- a reference to the correlated trace, together with a minimal version stamp (model deployment
  identifiers and prompt or contract versions) and the total token and approximate cost summary
  needed to compare runs later.

The stamp and totals are a summary, never a second telemetry schema; call-level configuration,
latency, and usage detail live only in the trace.

When the Supervisor commits this artifact relative to delivery belongs to `workflow-design.md`.

Evaluation artifacts are not part of it. Offline evaluation runs after a turn completes, reads the
completed turn and its trace, and records its own references to them by investigation and turn
identity. A completed turn is never rewritten later to point back at an evaluation run.

This is one artifact at design altitude. Whether it is physically one record or several linked ones
belongs to `runtime-and-deployment.md`.

### The ephemeral boundary

Everything a turn holds while it runs is ephemeral: its plan, its working hypotheses, its pending
operations, its operation history, its draft assessment, and its admitted evidence before commit.
None of it is checkpointed, and none of it makes an interrupted turn resumable (NFR-57).

The artifact therefore excludes in-flight plans, pending operations, hidden reasoning, and any
checkpoint or recovery state. Working hypotheses are not part of it; where they matter for
troubleshooting they appear in trace data, which is not evidence. There is no review state and no
publication state, because neither concept exists in this system.

### Trace and evaluation references

Trace and evaluation artifacts describe the run, not the incident. The completed-turn artifact
carries a reference to the correlated trace, together with the version stamp of the model and
prompt configuration used and the usage totals for the turn, so a developer can reconstruct what
happened (NFR-14, NFR-18, NFR-22).

Evaluation artifacts are a separate consumer. They read the completed turn and its trace and hold
their own references back to them by investigation and turn identity, so an evaluator can score the
run. The completed-turn artifact never holds a reference to an evaluation run or its result, and is
never rewritten after evaluation to add one.

Neither the trace reference nor an evaluation artifact's reference can ever be cited as proof of the
incident's cause. OpsPilot's own telemetry is not evidence about RetailEase. Telemetry and
evaluation structures themselves belong to `runtime-and-deployment.md` and `evaluation.md`.

---

## 18. Data and Evidence Invariants

The evidence-specific invariants are stated in §7 and are not repeated here. These are the
cross-cutting ones.

1. Model output is proposed data until deterministic code admits it, and never becomes evidence by
   being structured, plausible, or repeated.
2. Engineer text is untrusted input and cannot enter the evidence set at all; only an observation
   the Evidence Access Layer retrieved and admission accepted becomes evidence.
3. Retrieved knowledge informs interpretation and never independently establishes the current cause.
4. Historical comparison is reported as comparison and never converted into a current-cause
   probability.
5. Evidence is typed by what it means; the access path is provenance, never a type.
6. Every approved capability shares one result model, one admission path, and one evidence
   vocabulary.
7. Exactly one authoritative assessment exists per turn, and ranked candidates never become several
   conclusions.
8. Exactly three qualitative labels exist, and no numeric score, percentage, probability, or
   confidence value exists anywhere in the assessment or brief.
9. Every grounded element marked established resolves to admitted operational evidence, and
   grounding attaches to structured elements rather than to sentences.
10. Every citation carries one of three roles, and a reference cannot occupy a role its type is
    incapable of supporting.
11. Every recommendation carries one of three provenance categories, with a knowledge reference
    present where provenance is runbook guidance or a prior-incident action.
12. The brief renders the assessment: it introduces nothing the assessment does not contain, and
    omits, reorders, or alters nothing it does.
13. Complete, partial, and inconclusive are the only brief shapes, and the shape follows from the
    turn state rather than from a grounding check.
14. A delivered brief is never edited in place; a revised analysis is a later turn.
15. A handoff summary restates retained state and creates no evidence and no assessment.
16. Only the completed-turn artifact persists, and the trace reference within it is never incident
    evidence; evaluation artifacts reference completed turns, never the reverse.

---

## 19. Requirement Traceability

| Semantic area | Principal requirements |
| --- | --- |
| Information trust model | NFR-2, NFR-9, NFR-10, NFR-11 |
| Identity and reference model | NFR-3, NFR-12, NFR-15 |
| Capability request and result semantics | FR-103, FR-104, NFR-7, NFR-8 |
| Tool-operation history and limitations | FR-68, FR-69, NFR-8, NFR-37 to NFR-42 |
| Evidence admission | FR-57, FR-100, FR-103, NFR-1, NFR-7 |
| Admitted evidence set | FR-63, NFR-2, NFR-3, NFR-6, NFR-12, NFR-55, NFR-57, NFR-58 |
| Engineer input and the evidence boundary | NFR-9 |
| Retrieved knowledge | FR-66, FR-67, FR-89 to FR-94, NFR-31 to NFR-34 |
| Temporal semantics | FR-13 |
| Evidence types | FR-57, FR-100, FR-113 |
| Candidate assessment | FR-18 to FR-25, FR-58 to FR-65, FR-79 to FR-82 |
| Claims, citations, and grounding | NFR-2 to NFR-5, NFR-35, NFR-36 |
| Recommendations | FR-34 to FR-38, FR-72, NFR-40 |
| Investigation brief | FR-9, FR-11 to FR-41, FR-70, FR-73 |
| Handoff summary | FR-10, FR-74 |
| Completed-turn artifact | NFR-14, NFR-22, NFR-55, NFR-57, NFR-58 |
| Trace and evaluation references | NFR-14, NFR-18, NFR-22 |
| Structured-query and protocol parity | FR-95 to FR-102, FR-104, NFR-43, NFR-44 |
| Read-only boundary | FR-75, FR-102, NFR-1 |
| Observable evidence surface | FR-106 to FR-119 |
