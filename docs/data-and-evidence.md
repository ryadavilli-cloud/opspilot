# OpsPilot Data and Evidence

**What information does OpsPilot trust, how does it become evidence, what does the assessment carry,
and what makes a brief safe to deliver?**

This document owns information meaning: the trust model, references, tool results, admission,
evidence versus retrieved knowledge, the assessment, grounding, the brief, and the completed
investigation record. It defines the assessment's field set once. It does not prescribe one class
per noun; a shape below is a class only where it crosses a boundary, persists, or holds an invariant
no other layer owns.

---

## 1. Trust model

| Information | Comes from | Trusted for |
| --- | --- | --- |
| Admitted operational evidence | A successful read-only capability call, through admission | Claims about the current incident |
| Retrieved knowledge | Runbooks, architecture notes, postmortems, prior incidents | Interpretation, leads, and history; never current proof |
| Incident context | The selected authored incident | Framing the objective; untrusted text otherwise |
| Engineer question | The engineer, after completion | A question over the record; untrusted text otherwise |
| Model output | Any agent or the judge | A proposal until code admits it |
| Telemetry | OpsPilot itself | Troubleshooting OpsPilot; never evidence about the incident |

Retrieved content, tool output, incident text, and engineer text are data and never instructions.

---

## 2. Identity and references

One `investigation_id` scopes everything: evidence, operations, telemetry, persistence, and the
question. There is no other identity.

A **reference** is a stable prefixed string naming one evidence item or one knowledge item. The
evidence forms are `logs:<service>:<event_id>`, `metrics:<entity>:<metric>@<timestamp>`,
`deploys:<service>:<deploy_id>`, `deps:<from>-><to>`, `alert:<service>:<alert_id>`,
`incident:<incident_id>`, `absence:<capability>:<operation>`, and `query:<operation>`. The
knowledge forms are `runbook:<doc>`, `architecture:<doc>`, and `postmortem:<incident>`. The prefix
says whether it is evidence or knowledge; one parser reads it and one resolver answers whether it
names something real in this investigation or the corpus. References are the only way a claim
points at its support.

Each segment names one thing the record already carries. `<service>` and `<entity>` are the
service or infrastructure entity the record belongs to; `<event_id>`, `<deploy_id>`, and
`<alert_id>` are the record's own identifier; `<metric>@<timestamp>` names one sample of one
series; `<from>-><to>` names one dependency edge; `<incident_id>` names the incident record;
`<operation>` is the identifier of one operation in the investigation's operations list; `<doc>`
and `<incident>` name one knowledge document. An `absence:` reference makes an authoritative empty
result citable. A `query:` reference makes an aggregate result, which has no underlying row,
citable by the operation that produced it. A structured-query row carries the reference of the
record it projects, formed from the row's identifying fields, which every projection over that
collection includes. An incident-record observation carries only the fields the approved
structured-query surface exposes; the record's cause and resolution text never reaches an agent.

---

## 3. Tool results

Every capability call returns one result carrying two facts as separate fields: whether it
**executed** (succeeded, timed out, unavailable, refused, failed) and, if it succeeded, how
**complete** the answer was (complete, empty, partial). Both are kept because collapsing them is
how an unreachable source turns into a clean bill of health.

Only a succeeded result may be complete, empty, or partial, and only a succeeded result may carry
content. Any other pairing is meaningless and is rejected at the result boundary by one small check.
That is a real invariant and it has exactly one enforcement point.

Provider errors, stack traces, and status codes never leave the adapter. The result names what the
source did in OpsPilot's terms.

---

## 4. Admission

Evidence enters the investigation through one deterministic path and no other. Admission takes a
tool result and the question it was meant to answer, and produces either observations or a
limitation:

- a succeeded, complete or partial result becomes one or more **admitted observations**, each with
  a reference, its evidence type, its content, its completeness, and where it came from;
- a succeeded, empty result becomes one admitted observation with an `absence:` reference, so the
  finding "nothing matched" is citable;
- anything else becomes a **limitation**: the question that went unanswered and why, in the
  caller's terms.

Admission never fabricates an observation, never admits a failed call, and never lets a model
summary or working hypothesis into the evidence set. Retrieval does not pass through it: a
successful retrieval's passages join the knowledge set, and a retrieval that fails, times out, or is
unavailable becomes a limitation like any other capability call.

The **evidence set** for an investigation is: the admitted observations, the limitations, and the
operations list: each operation attempted, by its identifier, the capability it called, and its
outcome.

---

## 5. Evidence versus retrieved knowledge

**Operational evidence** is an admitted observation of the current incident. **Retrieved
knowledge** is a passage from a runbook, architecture note, or past incident. A passage carries its
text and its reference and reaches the agents as context. It can shape what is checked and how
evidence is read, and it can inform an action's provenance. It cannot by itself establish the cause
of the current incident, and a knowledge reference cannot stand as current operational support for
a claim.

---

## 6. The assessment

The RCA Analyst produces one assessment per investigation. Its fields, stated once:

| Field | Meaning |
| --- | --- |
| `what_happened` | Statement of the incident, its timing, and what was affected, with supporting references |
| `candidates` | Ordered list of candidate causes; the first is the leading candidate |
| `unknowns` | What could not be established, and material contradictions, in the analyst's words |
| `limitations` | The recorded limitations the analyst acknowledges, by their questions |
| `next_check` | Optional: the one check that would most usefully separate the remaining candidates |
| `actions` | List of recommended actions |
| `history` | Optional: how this incident relates to prior occurrences, with knowledge references |
| `knowledge_used` | Knowledge references that informed the assessment |

A **candidate** carries: `statement`; `label`, one of Leading, Plausible, or Weakly supported;
`established`, a bool meaning the brief may present it as current fact; `supporting`, evidence
references; `weakening`, evidence references. Whether a supported conclusion exists is not a stored
field; it is exactly "some candidate is established."

An **action** carries: `action`; `now`, a bool separating immediate action or verification from
longer-term follow-up and prevention; and optional `knowledge_ref` where retrieved guidance
supplied it. An action with no knowledge reference is general practice and is labelled as such in
the brief. Where the evidence supports that no immediate action is required, `actions` states that
affirmatively as its own entry with `now` set; it is never inferred from an empty list.

The three labels are the chosen design vocabulary, kept as an enum because it is reused and because
model output should be constrained to known values. R-8 requires qualitative labels; it does not
require three, and nothing enforces or tests that count.

The **proposal** the model is asked for is this shape as loose strings, plus one optional
`unresolved_question` with the question and the evidence kind that could answer it. That field is
routing metadata for the one return; the same matter is stated in `unknowns`. Structural admission
parses the proposal into the assessment; it does not remove, derive, or downgrade anything
semantic.

---

## 7. Grounding

One deterministic function: given the admitted assessment, the admitted operational evidence and
its references, the retrieved knowledge and its references, and the recorded limitations, return
zero or more issues. Each issue has a kind and a detail.

The function distinguishes two roles a reference can play, and the prefix already tells them apart:
**current operational support**, which must resolve to evidence admitted in this investigation, and
**knowledge or context**, which must resolve to a passage retrieved in this investigation. A
knowledge reference may support history, interpretation, or an action's provenance; it may never
stand as current operational proof. No role field or provenance taxonomy is needed to enforce
this.

The properties it enforces, over every material claim about the incident:

- every operational-support reference resolves in this investigation's admitted evidence, and
  every knowledge reference, including an action's `knowledge_ref` where present, resolves in its
  retrieved knowledge;
- a knowledge reference is not used where current operational support is required;
- `what_happened`, itself a material statement about the incident, has admitted operational
  support;
- every candidate marked established has admitted operational support;
- every recorded limitation is represented in the assessment.

These are useful diagnostics. Their number is not a contract, and no type exists to guarantee it.
The function does not inspect prose and does not judge whether evidence semantically supports a
claim; that belongs to the offline judge.

Grounding is the sole semantic owner of these properties. Structural admission does not
pre-enforce them, and no contract validator duplicates them.

---

## 8. The brief

The brief is a deterministic presentation of the accepted assessment. It introduces nothing the
assessment does not hold and drops nothing it does. It leads with what happened, the best-supported
explanation, and the most useful next action; it exposes credible alternatives where warranted,
what supports and weakens each, unknowns and limitations, historical context where useful, and
actions split into now and later. Where more than one candidate is established, the brief presents
them as contributing causes, not as a leading candidate and alternatives. An affirmative
no-immediate-action entry is rendered as such. Presentation and section layout are rendering
choices, not a schema. A `Brief` shape may exist because it crosses the API and persistence
boundary; its sections are not domain models.

The brief states which outcome the investigation reached, and it never presents a probability that
a cause is correct.

---

## 9. The completed investigation

One artifact per investigation, written once by the Supervisor after the gate passes and before
the terminal event, read afterwards for the brief, the question, and evaluation:

- `investigation_id`, the incident selected, and the objective;
- the outcome, and why gathering stopped or, for a failure category, nothing is written;
- the admitted observations and limitations;
- the operations list: each operation attempted, by its identifier, the capability it called, and
  its outcome; not its arguments and not its raw result;
- the retrieved passages used, with their references and text where the question needs them;
- the assessment;
- the brief;
- a correlation reference into telemetry, and the model deployment and prompt versions used;
- run accounting: the number of model calls made, the number of capability calls made, token usage
  accumulated across the run with input and output kept separate, and the run's duration. These
  are facts about the run in the same category as the deployment and prompt versions: they are not
  evidence, are cited by nothing, and are read by nothing in the investigation.

Ephemeral working state is not persisted: no bounds, no proposals, no working hypotheses. Evaluation
artifacts are separate and reference the investigation, never the reverse.

---

## 10. Invariants

- Model output is proposed data until code admits it, and never becomes evidence by being
  structured.
- Evidence enters only through admission; nothing else constructs an observation.
- A tool result's two facts are separate, and an impossible pairing cannot exist.
- Retrieved knowledge never stands as current operational support.
- Every reference resolves through one parser and one resolver.
- Established content rests on admitted operational evidence; grounding is the one place that
  checks it.
- Contradicting evidence is kept and shown, never resolved away.
- The brief renders the assessment and adds nothing.
- One completed record per investigation; nothing is written before completion.
