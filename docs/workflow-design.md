# OpsPilot - Workflow Design

**How does a bounded investigation turn execute over time?**

## 1. Purpose and Document Boundaries

This document owns behavior over time: how a turn executes, how it routes, what bounds it, how it
stops, how it degrades, and what states and reasons it records.

It does not own what information means. Evidence admission, tool-result vocabulary, citations,
candidates, assessment and brief semantics, and the completed-turn artifact belong to
`data-and-evidence.md`. Component responsibilities and authority belong to `system-design.md`.
Transport, hosting, and persistence realization belong to `runtime-and-deployment.md`.

---

## 2. Turn Model and Session Behavior

An **investigation** is one incident under study. A **turn** is one bounded adaptive cycle within it
that produces one investigation brief (FR-70). A **live session** is the ephemeral conversational
surface over an investigation and has no durable identity of its own.

One live streaming request owns one turn. That request creates the turn, streams its activity,
executes it, and ends by delivering a completed turn carrying a brief, or a failed execution. There
is no job dispatch, no background continuation after the request returns, and no way to reattach to
a turn already running.

Losing the request or the process may lose the active turn. Nothing incomplete is persisted, and the
engineer runs the turn again (NFR-57). Everything already completed remains readable (NFR-58).

Findings, tool results, questions, and engineer corrections are retained across the turns of one
investigation (FR-44, NFR-56), reconstructed from the completed turns the Investigation Record
holds. Unrelated investigations stay isolated (FR-45, NFR-12).

Each turn ends as **complete**, **partial**, or **inconclusive** (FR-55). Those describe completed
turns. A runtime attempt that cannot produce, validate, deliver, and persist a trustworthy brief is
a **failed execution**, not a fourth outcome (§9).

---

## 3. Investigation Stages

A turn passes through five stages:

1. **Intake and objective**
2. **Bounded investigation**
3. **Synthesis**
4. **Grounding and outcome validation**
5. **Delivery and completed-turn persistence**

Within bounded investigation the loop is reason-act-observe (FR-84), with the Supervisor deciding
after each cycle whether another is authorized. One optional edge exists: synthesis may return once
to investigation when the RCA Analyst identifies a further-evidence need and the Supervisor
authorizes it (§6). Every other transition is forward only.

```text
intake and objective
          │
          ▼
  bounded investigation ◄──── continuation authorized
          │                            ▲
          ▼                            │
      synthesis                        │ at most one
          │                            │ authorized cycle
          ├── further-evidence need ───┘
          │
          ▼ assessment or insufficiency
 grounding and outcome validation
          │
          ▼
delivery and completed-turn persistence
          │
          ▼
 complete · partial · inconclusive
```

Follow-up questions and handoff-summary requests never enter this sequence; they are answered from
retained state (§8).

---

## 4. Intake and Objective

This stage runs once when an investigation is opened, and again in reduced form whenever a follow-up
seeds a new turn.

The engineer selects a predefined incident (FR-1, FR-43). The selection resolves into the structured
incident form before the turn begins (FR-3), and engineer text is carried as untrusted data
throughout (NFR-9).

Investigation begins immediately; structured intake requires no blocking confirmation. One incident
is the active investigation (FR-42).

The Supervisor then sets the turn objective: what this turn is trying to establish, and the budget
it may spend. The objective follows from the incident, interpreted through the lower-cost deployment
as the one deliberately routed task (FR-105, `decisions.md` D-002). The objective and its budget are
set by the Supervisor alone, and no agent may widen them (FR-56).

---

## 5. Bounded Investigation

The Evidence Investigator selects evidence sources from the incident and what has already been found
(FR-49, FR-86), rather than running the same tools in the same order for every incident (FR-50).
Each observation informs whether another check is worth making (FR-51), and direction is revised
when evidence weakens the current explanation (FR-52). Different incidents therefore take
demonstrably different evidence paths (FR-85).

All access is through the approved read-only capability surface (FR-57, FR-75, NFR-1). Independent
evidence actions may be issued together where they do not depend on one another (FR-87); they share
the turn's remaining deadline.

Admitted evidence stays in ephemeral turn state. Nothing is written to the Investigation Record
while the turn runs.

### Continuation

Another cycle takes two steps: the Evidence Investigator proposes one, and the Supervisor authorizes
it or refuses. The split exists because the reasons for continuing are judgments and the limits on
continuing are not.

**The proposal.** The Evidence Investigator states the material question still unresolved, the
permitted action it believes would answer it, and why that answer could change the analysis. Where
retrieved knowledge influenced the proposed action, the proposal may carry the informing knowledge
reference or references; the field is present only when that influence is real, names only
knowledge already retrieved in this turn, and does not make that knowledge current operational
proof (FR-93, FR-94). This is a request and never a grant: proposing a cycle neither creates budget
nor obliges the Supervisor to allow one.

**The authorization.** The Supervisor evaluates only what code can decide, and all of the following
must hold:

- the proposed action is not a repeat of one already performed;
- the named capability is approved and permitted;
- budget remains for it.

Any failure means no further gathering. The Supervisor does not re-derive the judgment behind a
proposal; it accepts or refuses the proposal as offered (NFR-10).

Gathering ends when the evidence is ready to interpret, when no useful permitted action remains,
when a bound is reached, or when a required source is unavailable. The reason is recorded by the
stage that detects it, at the moment it is detected (§9).

Readiness to interpret is not a claim about the answer. A turn may end gathering cleanly and still
conclude that the evidence is insufficient.

### Bounds and turn ending

Execution limits on steps, tool calls, retries, elapsed time, context, and model use are
deterministic and configurable (FR-53), and they exist to make runaway execution impossible rather
than unlikely (FR-54). Code owns every budget; no agent extends, resets, or reinterprets its own
(FR-56, NFR-10). Configured values belong to `runtime-and-deployment.md`.

Code enforces those limits as a small fixed set of mechanisms: one turn deadline propagated into
every model and capability operation, one capability-call cap, one model-call cap, one
per-operation transport-retry cap, the one correction allowance below, and the one further-evidence
cycle of §6. Context size is bounded structurally by prompt assembly and the retrieval passage
budget rather than by a runtime token ledger; token usage is measured for telemetry and evaluation,
not budgeted.

One of those bounds is a single correction allowance. A turn may spend one corrective model call,
consumed by whichever failure reaches it first: a structurally unusable synthesis result (§6) or a
failed grounding check (§7). A turn that spends it on a structural failure has none left for a
grounding failure, and the reverse. A failure arriving with the allowance already spent is not
corrected again; the turn degrades under §10.

A turn ends when gathering reaches its natural end, when a bound is exhausted, or when the request
carrying it disconnects. Where a bound ends gathering early, synthesis runs over whatever evidence
exists, grounding still applies unchanged, and the brief is delivered marked partial (FR-40).

If the live request itself disappears before completion, the execution may be cancelled and
discarded. No completed turn is required when there is no connection through which a trustworthy
result can be delivered and nothing was committed.

---

## 6. Synthesis and the Further-Evidence Cycle

The RCA Analyst receives the incident context, the admitted evidence, the retrieved knowledge that
informed it, the open questions, the known limitations, and the reason gathering ended. It reaches
no tool or source directly (FR-101) and returns every result through the Supervisor.

It returns exactly one of three results:

**A supported assessment.** The leading candidate, supported alternatives with their qualitative
labels, the evidence supporting and weakening each, relevant history, unknowns and limitations, and
the recommendations that make up the brief's analytical content (FR-59, FR-60, FR-66, FR-81).

**An explicit insufficiency statement.** What was established, what is missing or contradictory, and
the most useful next check that would distinguish the remaining candidates (FR-23, FR-61, FR-62).

**A further-evidence need.** One material unresolved question, why answering it could change the
assessment, and the evidence type that could answer it. It is advisory: it creates no budget, does
not widen the turn, and does not decide whether gathering resumes.

Where more than one contributing failure explains the incident, that is represented within the one
assessment as contributing factors, never as competing conclusions (FR-65, FR-82). Contradictory
evidence is preserved rather than resolved away (FR-63), and retrieved history never stands as proof
of the current cause (FR-67).

### The one authorized further-evidence cycle

A further-evidence need is a proposal, and authorizing it is a separate decision. The same split
applies here as in §5, for the same reason: materiality and whether an answer would change anything
are judgments, and the limits on acting are not.

**The proposal.** The RCA Analyst states the material question left unresolved, the evidence type
that would answer it, and why that answer could change the assessment. It names an evidence type
rather than a capability, because it reaches no source and holds no view of the capability surface
(FR-101). It is a request and never a grant: it creates no budget, widens no bound, and does not
decide whether gathering resumes.

**The authorization.** The Supervisor evaluates only what code can decide, and all of the following
must hold:

- no further-evidence cycle has already occurred in this turn;
- an approved and permitted capability supplies the named evidence type;
- the action that capability would perform is not a duplicate of one already performed;
- sufficient existing turn budget remains.

If any condition fails, no further gathering occurs and the unresolved question is carried into the
brief as a discriminator or limitation. The Supervisor does not re-derive the judgment behind the
proposal; it accepts or refuses it as offered (NFR-10).

At most one such cycle is permitted per turn. It draws on the existing turn budget, adds no retry or
correction allowance, returns through the Supervisor, and is followed by one final synthesis pass
that cannot request another. This is a single bounded edge, not an open loop.

A synthesis result that is structurally unusable may be corrected by spending the turn's correction
allowance (§5), where that allowance is still unspent. A structural failure arriving with the
allowance already spent, or a correction that does not resolve it, degrades the turn under §10.
Correction mechanics belong to `code-guidelines.md`.

---

## 7. Grounding Gate and Outcome Validation

The gate runs once synthesis has produced an assessment, and before the completed-turn commit and
delivery of §8. The Supervisor's grounding gate executes exactly four deterministic grounding
checks: reference resolution, unsupported-element rejection, recommendation-provenance presence, and
required limitation disclosure. What each one inspects is defined in `data-and-evidence.md`; this
section owns when the gate runs and what routing follows.

This set is fixed. The checks are ordinary deterministic code inside the Supervisor boundary, not a
reviewing role, and each is a test over structure rather than a judgment about prose. Whether cited
evidence semantically supports what it is attached to is not among them; that judgment belongs to
the offline judge in `evaluation.md` and never gates delivery. Whether model output parses into a
valid structure is settled before these checks run, through the bounded correction path.
Incident-category evidentiary expectations are scenario expectations owned by `evaluation.md` and
are deliberately not runtime checks.

### The gate validates the outcome; it does not choose it

Which shape the turn supports follows from the turn state: the assessment, the admitted evidence,
the reason gathering stopped, how completely the objective was met, and the known limitations. The
Supervisor owns that decision. The checks only confirm that the proposed brief represents that shape
faithfully and safely.

The gate therefore never rules a turn partial because disclosure failed, never rules it inconclusive
because support failed, and never derives a different assessment from the identity of a failed
check.

When a check fails, the failed check and its reason are recorded. Where the turn's correction
allowance (§5) is still unspent, it is spent here: one bounded correction is requested, and the
corrected brief is checked again:

- **passes** — the turn proceeds to persistence and delivery, carrying the outcome shape its state
  supports. An initially failed check does not by itself prevent a complete outcome.
- **still fails** — the attempt becomes a failed execution. The brief is not delivered, no completed
  turn is created, and nothing is persisted.

Where the allowance was already spent correcting a structurally unusable synthesis result (§6), no
correction is requested. The failed check makes the attempt a failed execution directly, on the same
terms.

A persistently noncompliant brief is never downgraded and shipped with a limitation attached.
Limitations disclose missing evidence and degraded sources; they cannot make an unresolved
reference, an unsupported element, absent provenance, or an omitted recorded limitation safe to
deliver. No fourth outcome is created, and the gate never edits a brief into passing or substitutes
an analysis of its own.

---

## 8. Delivery, Persistence, and Follow-Up

Persistence precedes delivery. Once the grounding gate passes, the Supervisor commits one
completed-turn artifact, and only after that commit succeeds is the terminal outcome emitted with
its brief (FR-9, FR-70). A successful result is never announced before it has been persisted. Where
the commit fails, no successful outcome is emitted, no completed turn exists, and the attempt is a
failed execution.

The artifact carries the turn identity and objective, terminal outcome, stop reason, admitted
evidence and required source references, the assessment and the delivered brief, limitations,
relevant follow-up context, and the correlated trace reference (NFR-55). The Supervisor is the only
writer, and nothing is written mid-turn. Starting a turn persists nothing: the investigation record is
created by the first successful completed-turn commit, so a first execution that fails leaves no
investigation shell behind and no orphan records exist.

What the commit does and does not carry, including evaluation artifacts, belongs to
`data-and-evidence.md`.

Nothing stands between synthesis and delivery beyond the gate and the commit: there is no approval,
editing, review, publication, or finalization stage.

While a turn runs, investigation activity, tool use, and evidence arrival are visible to the
engineer as they happen (FR-109, FR-110, NFR-53). Supporting sources and tool outcomes remain
inspectable behind the delivered brief (FR-73). Transport belongs to `runtime-and-deployment.md`.

### Activity events

Meaningful activity events are emitted from the workflow facts the stages already produce: when the
active phase or responsible role changes; when the Evidence Investigator proposes an action; when a
capability, retrieval, structured-query, or MCP operation completes; when a material limitation is
recorded; when continuation or the further-evidence cycle is authorized or declined; when the
correction allowance is spent; when grounding completes; when persistence and terminal completion
succeed; and when a failed execution ends the attempt. Repeated or low-level
operations may be grouped for the feed. Event fields and their relation to telemetry belong to
`system-design.md` ("Activity projection").

### Follow-up

After delivery, an engineer message is handled as exactly one of two kinds. Where the kind is
ambiguous it is treated as a question, the cheapest interpretation, leaving the engineer free to
restate it.

| Kind | Handling |
| --- | --- |
| Question | Answered from retained completed-turn state; opens no turn (FR-6, FR-71) |
| Handoff-summary request | Derived from retained state; opens no turn (FR-10, FR-74) |

Neither kind opens a turn, so a later message never starts new evidence gathering.

A question is answered by the Supervisor from retained state through the primary model deployment.
The answer may cite only retained evidence and knowledge references, and it introduces no new
evidence, no new candidate cause, no new conclusion, and no recommendation presented as coming from
retrieved guidance. Before delivery it passes a deterministic follow-up answer validation: every
cited reference must resolve within the retained investigation state, and no new element of those
kinds is present. That validation is not a grounding check, and the four-check gate remains
exclusive to completed-turn delivery. Where retained state cannot answer the question, the answer
says so and, where appropriate, recommends a new investigative turn.

A handoff summary is a deterministic projection of retained structured state; it calls no model and
creates no new synthesis (`data-and-evidence.md`, "Handoff Summary").

Nothing reaches into a turn already executing (FR-8). A delivered brief is never edited in place.

---

## 9. Outcomes, Statuses, and Reasons

### Live status

A turn reports one live status, used for the engineer-facing surface and telemetry:

| Status | Meaning |
| --- | --- |
| `investigating` | Gathering evidence within bounds |
| `synthesizing` | Producing the assessment, or correcting it under the turn's correction allowance |
| `validating` | The grounding gate is executing its four grounding checks |
| `completed` | A completed turn exists |
| `failed` | No completed-turn artifact exists |

`completed` carries one of three outcomes. `failed` is not a fourth outcome; it means the attempt
produced no trustworthy artifact at all.

### Outcomes of a completed turn

- **Complete.** Gathering ended on its own terms and synthesis produced a supported assessment
  covering the objective (FR-39).
- **Partial.** The turn stopped early through a bound or a degraded source, having admitted at least
  some evidence, and reports plainly what was not reached (FR-40).
- **Inconclusive.** The evidence does not support a cause; the turn names what is missing or
  contradictory (FR-41).

An inconclusive turn may still state that no immediate action is required, or that action may safely
be deferred, where the evidence supports that (FR-72).

### Why gathering stopped

| Reason | Meaning |
| --- | --- |
| `analysis_ready` | The material questions needed for analysis were answered |
| `no_useful_action` | No permitted action was likely to improve the result |
| `bound_reached` | A configured execution bound was exhausted |
| `required_source_unavailable` | A source the objective depended on could not be queried |

`analysis_ready` is not a claim about the answer; a turn may stop for it and still be inconclusive.
Which bound was consumed is visible in telemetry rather than split into separate reasons.

### Why a turn was inconclusive

| Reason | Meaning |
| --- | --- |
| `insufficient_evidence` | Current evidence does not support a causal conclusion |
| `material_conflict` | Material observations remain contradictory |
| `required_evidence_unavailable` | Missing required evidence prevents a supported conclusion |

Reasons are recorded by the stage that detects the condition, at the moment it is detected. A later
stage never infers one.

---

## 10. Failure, Degradation, and Observability

### Degraded sources

A tool failure, unavailable source, timed-out call, or authoritative empty result is recorded as a
limitation (FR-68) and never fabricated into an observation (FR-69, NFR-8). Gathering continues when
the failed source was not essential, when another permitted source answers the same question, or
when sufficient evidence already exists.

A source failure is never hidden, and it constrains the outcome only by its materiality. Where the
failed source did not bear on the turn objective and the admitted evidence still supports the
assessment, the turn may still complete as **complete** with the failure disclosed. Where a source
the objective depended on stays unavailable, or required evidence could not be obtained, the
limitation carries into a partial or inconclusive outcome rather than a guess.

### Failed execution

Not every runtime failure produces a completed turn.

Where the application remains healthy enough to synthesize, ground, persist, and deliver a
trustworthy brief, the turn completes with the failure disclosed as a limitation.

Where it cannot, the attempt is a **failed execution**. It creates no completed-turn artifact, is
visible to the engineer where the stream survives and always in telemetry, and may be retried by
starting a new turn. Process termination, unrecoverable failure before a valid assessment or brief
exists, a brief that fails the grounding gate with the turn's correction allowance spent, failure to
persist the completed artifact, and a broken live connection with the execution abandoned all fall
here.

A persistence failure is never reported as a successfully completed turn.

### Degradation is visible

Missing sources, retries, failures, and bounded stops are surfaced to the engineer rather than
absorbed (FR-116).

### Observability

Each stage emits enough structured information to reconstruct a turn: which investigation and turn
ran, which role acted, which assignment and result passed between them, which actions were taken and
what they returned, what evidence was admitted, why gathering continued or stopped, which bounds or
degradation conditions were hit, whether the checks passed, the terminal outcome or execution
failure, and what the turn consumed (NFR-14). Telemetry realization belongs to
`runtime-and-deployment.md`.

Workflow records explain what the workflow did. They are not evidence about the incident.

---

## 11. Workflow Invariants

1. One live streaming request owns one turn; there is no dispatch, no background continuation, and
   no reattachment.
2. Losing the request or process may lose the active turn, and nothing incomplete is persisted.
3. Gathering continues only on a proposal the Supervisor authorizes against computable conditions,
   and no agent widens its own budget or re-derives the judgment behind a proposal.
4. Ordinary adaptive continuation happens only during bounded investigation and stays
   Supervisor-controlled.
5. The RCA Analyst returns a supported assessment, an insufficiency statement, or one
   further-evidence need, and nothing else.
6. At most one further-evidence cycle occurs per turn, on the existing budget, and the final
   synthesis pass cannot request another.
7. Every assignment and result passes through the Supervisor.
8. The grounding gate executes exactly four grounding checks, validating the outcome the turn state
   supports rather than choosing it; a failure spends the turn's one correction allowance where it
   remains, and a brief that fails with that allowance gone becomes a failed execution rather than a
   delivered one. The allowance is shared with structural correction of a synthesis result and is
   never replenished.
9. Complete, partial, and inconclusive are the only completed-turn outcomes; a failed execution
   produces no completed turn.
10. Evidence persists only as part of a completed turn, written by the Supervisor, and that commit
    succeeds before any successful outcome is emitted.
11. A terminal turn is never reopened, a delivered brief is never edited, and nothing reaches into a
    turn already executing.
12. The workflow performs no remediation and has no review, approval, publication, or recovery
    stage.
