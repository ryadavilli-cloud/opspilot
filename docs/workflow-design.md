# OpsPilot Workflow Design

**How does one bounded investigation run over time, and what can happen to it?**

This document owns behavior over time: the run lifecycle, gathering and continuation, synthesis,
the one analysis-to-gathering return, grounding, correction, persistence, delivery, degradation and
failure, bounds, outcomes, and the question over a completed record. What each component owns
belongs to `system-design.md`; what the information means belongs to `data-and-evidence.md`.

---

## 1. One investigation is one run

An engineer selects one authored incident. That mints one `investigation_id`, starts one bounded
run, and ends in one completed investigation record, or in a failed execution that leaves no record.
Nothing reopens, extends, or revises a completed investigation. A question about it afterwards reads
the record; it is not a run.

There is no session, no turn history, no background continuation, no job, no checkpoint, and no
resumption. If the request carrying the run disconnects, the run is abandoned and nothing is
persisted; the engineer selects the incident again.

---

## 2. The graph

The run is one small compiled in-process graph over typed investigation state.

```text
  set_objective ──► gather ──► synthesize ──► ground ──► persist ──► deliver
                     ▲  │          │            │
                     │  └─continue─┘            │ one correction, then
                     │                          │ failed execution
                     └───── one return ─────────┘
```

Nodes are ordinary functions. There is no checkpointer, no interrupt, no pause or resume, and no
framework agent abstraction. State is in memory for the streaming request and is not recoverable.

---

## 3. Objective

The Supervisor reads the normalized incident context and, in one model call, states what this
investigation is trying to establish. It then sets the bounds. Neither the objective nor the bounds
change afterwards, and no agent may widen a bound.

---

## 4. Gathering and continuation

The Evidence Investigator proposes one evidence action at a time: which registered capability, with
which arguments, to answer which question. It chooses from the incident, the objective, the
evidence admitted so far, and any retrieved knowledge. One observation informs the next choice, and
the direction changes when evidence weakens the current explanation. Different incidents therefore
take different paths.

The Supervisor authorizes each proposal deterministically. All of the following must hold:

- the capability is registered;
- the same question has not already been answered;
- the capability-call cap and the deadline both have room.

If any fails, gathering ends and the reason is recorded. Otherwise evidence access executes the
call with the remaining deadline and admits the result: an observation, an authoritative empty
observation, a partial observation, or a limitation.

Gathering also ends when the Evidence Investigator reports that the evidence is ready to interpret
or that no useful permitted action remains, or when a source the objective depends on is
unavailable.

Retrieval is proposed and authorized like any other registered capability and counts against the
same capability-call cap. Its passages join the knowledge set; a retrieval that fails, times out,
or is unavailable is recorded as a limitation.

---

## 5. Synthesis

The RCA Analyst receives the incident context, the admitted evidence, the retrieved knowledge, the
limitations, and why gathering ended. In one model call it proposes an assessment. It reaches no
tool.

Structural admission then parses the proposal: it enforces the field types, normalizes harmless
representation, and rejects malformed structure or a reference string that cannot syntactically be
a reference. It does not remove an unsupported candidate, does not derive or downgrade
`established`, and does not discard an action for its provenance. What the model proposed is what
the grounding gate sees.

A structurally unusable proposal may spend the one correction (section 8).

---

## 6. The one return

The assessment proposal may carry one `unresolved_question`: what remains unanswered and what kind
of evidence could answer it. It is routing metadata on the proposal; the same matter is stated in
the assessment's `unknowns`, so the assessment is complete whether or not the return happens. The
RCA Analyst still cannot call anything.

The Supervisor authorizes a return only when no return has happened yet, a registered capability
supplies that kind of evidence, and the bounds have room. If authorized, the graph returns to
gathering with the question seeded, gathering runs under the same continuation rules, and synthesis
then runs once more with the return flag set. If the return is unavailable or already spent, the
Supervisor does not follow the edge and does not edit the assessment; the unknown already stands.

That is the whole feedback loop: at most one return per investigation, by design.

---

## 7. Grounding

One deterministic function reads the admitted assessment, the admitted operational evidence, the
retrieved knowledge, and the recorded limitations, and returns zero or more issues over every
material claim about the incident. Issues that naturally arise: an operational-support reference
that does not resolve in this investigation's admitted evidence, or a knowledge reference that does
not resolve in its retrieved knowledge; a knowledge reference used where current operational
support is required; `what_happened` or an established candidate with no admitted operational
support; a recorded limitation the assessment does not disclose. The number of issue kinds is a
description, not an invariant.

The gate never edits the assessment and never chooses the outcome. No model runs inside it.

---

## 8. One correction

The state carries `correction_used`. Either a structurally unusable proposal or a non-empty issue
list may spend it: one corrective model call carrying the problem, then re-admission and, for
grounding, a re-check. If the problem remains, or the correction was already used, the attempt is a
failed execution.

---

## 9. Outcome, persistence, delivery

Code assigns the outcome from two facts already in state: whether any candidate is established,
and whether any limitation was recorded.

- **Inconclusive** when no candidate is established. The record may still hold observations,
  unknowns, contradictions, a useful next check, and limitations.
- **Partial** when some candidate is established and at least one limitation was recorded.
- **Complete** when some candidate is established and no limitation was recorded.

Nothing else contributes: not the stop reason, not reaching a bound, and not an unavailable source
except through the limitation it already recorded. This over-reports partial, since one small
limitation makes an otherwise clean investigation partial; that is deliberate, and the honest
direction to err, because the limitation is disclosed either way. Reaching a bound never turns
insufficient evidence into a conclusion.

The completed investigation is saved. Only after the save succeeds is the terminal event emitted
with the brief. A save that fails is a failed execution.

---

## 10. Degradation and failure

A source that fails, times out, is unavailable, or is refused becomes a limitation. Gathering
continues where another capability can still answer a useful question. Every limitation is
disclosed in the assessment and, under section 9, makes the outcome at most partial. A run with at
least one admitted operational observation reaches an outcome under section 9, however many
sources failed. A run with zero admitted operational observations is a failed execution: no
grounded brief can be produced, because `what_happened` has nothing admitted to rest on, and the
incident context does not substitute for admitted evidence.

Failed execution is any of: zero admitted operational observations when gathering ends, an
unusable proposal after the one correction, grounding issues remaining after the one correction, a
failed save, the deadline expiring before a trustworthy brief can be synthesized, or an unhandled
error. A failed execution emits a terminal event with a sanitized failure category, persists
nothing, and is not an outcome. It is visible in the activity feed and in telemetry.

---

## 11. Bounds

Five pieces of deterministic state, set at objective time, held on the graph state, never written
by a model:

- one deadline, propagated into every model and capability call;
- one capability-call cap, which retrieval calls count against;
- one model-call cap;
- `correction_used`;
- `return_used`.

Token usage is measured for telemetry and evaluation, not budgeted. There is no per-agent budget,
no retry policy object, and no budget hierarchy.

---

## 12. What the engineer sees

While the run executes, the interface streams a compact activity feed: which agent or capability is
acting, what it is doing, what it obtained, why gathering continued or stopped, the return if it
happened, the grounding result, persistence, and the terminal outcome or failure. Never
chain-of-thought.

The brief is delivered as the terminal event. Supporting evidence and limitations remain
inspectable behind it.

---

## 13. The question over a completed record

After delivery, the engineer may ask a question. The Interface receives it and presents the answer;
the Supervisor answers it in one model call whose only context is the completed record, with
instructions to answer from it or say it cannot. The response carries the answer and the references
it cites; where it refers to a candidate structurally, it may carry that candidate's position in the
retained ordered list. Deterministic code checks that every cited reference exists in the record and
that any candidate position is valid; if a check fails or the record cannot answer, the answer says
so. The no-new-conclusion property rests on the constrained context, the instruction, those
structured references, and refusal, not on code judging prose. No evidence is gathered and no
investigation is created.

---

## 14. Invariants

- One `investigation_id`, one run, one record.
- The Evidence Investigator never reaches the engineer; the RCA Analyst never reaches a tool.
- Every capability call carries the remaining deadline; every operational result passes through
  admission, and every retrieval result joins the knowledge set or becomes a limitation.
- Continuation and the one return are authorized by code against computable conditions alone.
- The gate is deterministic, edits nothing, and chooses no outcome.
- At most one corrective model call and one return per investigation.
- Nothing is persisted before completion; nothing is delivered before persistence succeeds.
- Failed execution leaves no record and is not an outcome.
