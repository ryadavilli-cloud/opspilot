# Instructions for files under `docs/`

These files are authored, finished text. They are not something an agent
generates, infers, verifies, or improves on its own initiative.

---

## Default posture: read-only

**No file in this folder is written during implementation work.**

Three files are the exception, under the bounded conditions below, and they
are not one category:

- `status.md` — what the repository currently is, measured against the design
- `horizontal-execution-plan.md` — the horizontal implementation sequence
- `vertical-execution-plan.md` — the vertical implementation sequence

Every other file — `requirements.md`, `architecture.md`, `system-design.md`,
`workflow-design.md`, `data-and-evidence.md`, `runtime-and-deployment.md`,
`evaluation.md`, `decisions.md`, `code-guidelines.md` — is read-only unless a
prompt names that specific file and names a mode. Read them freely. Cite them
constantly. Do not edit them.

This holds even when a design document is *wrong*. A design document that no
longer matches the code, contradicts another document, or describes something
the implementation proved impossible is a question for the author. It is not a
defect for you to repair, and the fact that you are already certain what the fix
should be does not change that.

---

## The tracking files

Three files track rather than design: `status.md`, and the two execution plans.
They are not one category. Status is anchored to the design and answers what the
repository currently is; a plan is anchored to status and answers how to close
the difference. They are edited for different reasons, on different triggers,
and the rules below are therefore separate.

### When

At every landing, after the local pass has been reviewed — not mid-slice, not in
anticipation, not because a change seems inevitable.

Both halves run, as part of the definition of done. Status records what was
built. Every slice whose subject that landing touched re-derives its marker.
Updating one without the other leaves derived data stale and silently wrong, and
nothing else in the repository will catch it.

Do not record a slice as done before its four gates pass.

### `status.md` — what may change

Edited when the repository contradicts it, never on the occasion of a slice.

- Rows whose standing the tree has changed, moved to what is now true
- Rows whose subject no longer exists, removed
- Test and verification counts, re-measured rather than incremented
- The baseline line: commit, date, gate results
- Rows that inspection contradicts

Bounded by one rule: **a row changes only where the repository contradicts what
is written.** Never because reasoning suggests it should, never because a design
document implies it, never to reconcile status with a plan. Every edit traces to
something you ran or read in this session.

Status carries no slice identifiers, no layer or stage numbering, no sequence,
and no statement of what comes next. Work that landed ahead of the sequence that
describes it is simply built; status holds no order for it to have arrived out
of, and records no note that it did.

If something landed and no row describes it, that is a gap. Report it. Do not
author a new row to cover it.

### `horizontal-execution-plan.md` and `vertical-execution-plan.md` — what may change

Far less. The plan is derived from the design and the registers; it is not a
progress log.

Permitted:

- Re-deriving a slice's marker from status: complete, partially satisfied with
  precisely what remains, or not started. A slice whose subject is already built
  marks itself complete and cites the row that shows it. A slice whose subject is
  partly built states what exists and narrows itself to the remainder
- Absorbing an out-of-order landing, which belongs here because sequence is the
  plan's to own
- Recording a divergence: where the work required something the slice text did
  not anticipate, or where a slice's stated citation had no counterpart

Not permitted without a separate prompt:

- Re-sequencing slices, moving work between layers, splitting or merging a slice
- Changing a definition of done
- Adding, removing, or restating a slice's tests, evaluation obligations, or
  observability obligations
- Rewriting a citation because the register wording changed — the register
  changes first, then the plan is re-derived against it, as its own task

The plan carries no dates, no estimates, and no ordering beyond dependency. Do
not introduce any.

---

## When a design document needs to change

Stop and ask. Do not edit it, do not stage the edit for approval, do not note the
needed change inside `status.md` instead, and do not proceed with an
implementation that quietly contradicts it.

State, in this order:

1. Which file, and which section
2. What the implementation established, with the file and line that establishes
   it
3. Why the current text cannot stand — a contradiction, an impossibility, or a
   contract the code cannot satisfy as written
4. What you believe the change is, as a recommendation rather than a draft
5. Whether the current slice can continue while the question is open, or is
   blocked on it

Then wait. The change arrives as its own prompt, naming the file and a mode.

Two cases that look like document edits and are not:

- **A settled choice turning out to be unworkable** is a `decisions.md`
  revision, made by a human before the code changes. Never a runtime fallback,
  never an undocumented deviation.
- **A requirement that appears unimplementable** is a `requirements.md`
  question. Scope is not renegotiated by implementation.

---

## Modes

A prompt that authorizes a document edit must name one of these. **If it does
not, assume reproduction and ask.**

### Mode 1 — Reproduction (default)

The prompt supplies the text.

- Write exactly what is given. Add no sections, examples, cross-references,
  disclaimers, TODOs, or formatting that was not in the provided text.
- Do not improve, expand, correct, or editorialize, even where the text looks
  incomplete or could be clearer. If something looks wrong, stop and ask. Do not
  fix it silently.
- Preserve code blocks, diagrams, and ASCII art exactly. Do not convert them to
  Mermaid, tables, or any other rendering.
- Match the file's existing line endings and wrapping.

### Mode 2 — Derivation

The prompt names an authoritative source and a target document.

- The source is the design. Express it at the altitude the target owns — do not
  extend it, improve it, or fill its gaps.
- Write only content that traces to the source, to `requirements.md`, or to a
  decision the prompt states. If something the target needs is absent from all
  three, stop and ask. Do not supply it.
- Do not carry over material from the previous version because it was already
  there. Previous content survives only where the prompt says it does.
- Report what you left out and why.

### Mode 3 — Analysis

The prompt asks for review, assessment, or reconciliation.

- Produce findings. Change no existing document.
- Ground every claim in a real file and line reference. If supporting text
  cannot be found, say so rather than inferring it.
- The accepted design set is authoritative; nothing else becomes so merely by
  being detailed or by appearing in an active document. For material outside it,
  the burden of proof is on retention.
- Surface open forks explicitly with a recommended default.
- Report what you did not find, not only what you did.

### Source precedence

Apply strictly, in this order:

1. `requirements.md` — governing product intent, scope, capabilities, journey
2. The accepted target design — `architecture.md`, `system-design.md`,
   `workflow-design.md`, `data-and-evidence.md`, `runtime-and-deployment.md`,
   `evaluation.md`: the settled answer for architecture, components, flows,
   contracts, and technology responsibility, and what `status.md` is measured
   against
3. Settled decisions confirmed in the prompt
4. RetailEase corpus and scenario facts
5. `code-guidelines.md` — implementation and merge rules binding code to the
   accepted design; `decisions.md` — the record of settled choices. Neither is
   part of the accepted design, and neither overrides anything above
6. Anything under `docs/archive/`, and any superseded assessment output —
   historical context only

A decision record is not settled merely because it is marked accepted. A document
is not authoritative merely because it is detailed.

---

## Status, design, and plan

The design set — `requirements.md`, `architecture.md`, `system-design.md`,
`workflow-design.md`, `data-and-evidence.md`, `runtime-and-deployment.md`,
`evaluation.md` — states what OpsPilot is meant to be. `status.md` states what the
repository currently is, measured against that design and against nothing else. An
execution plan states how to close the difference. Each document answers one
question and never answers another's.

Status is anchored to the design, not to a plan. A capability is implemented,
partially implemented, or missing because of what the tree contains, not because a
slice ran. Status therefore carries no slice identifiers, no layer or stage
numbering, no sequence, and no statement of what comes next. Work that landed early
is simply built — status holds no order for it to have arrived out of. A row changes
only where the repository contradicts what is written, and every claim traces to a
file read or a command run in the session that recorded it.

The plan depends on status; status never depends on the plan. A slice reads the
registers and records its own state against them: complete, partially satisfied with
precisely what remains, or not started. A slice whose subject is already built marks
itself complete and cites the register row that shows it. A slice whose subject is
partly built states what exists and narrows itself to the remainder. Out-of-order
landings are absorbed here, in the plan, because sequence is the plan's to own.

Both halves run at every landing, as part of the definition of done: status records
what was built, and every slice whose subject that landing touched re-derives its
marker. Updating one without the other leaves derived data stale and silently wrong,
and nothing else in the repository will catch it.

This holds only where a slice's completion criteria are stated in terms status can
answer — capabilities, modules, contracts, observable behavior. A criterion status
cannot answer cannot be reflected and must be either restated or given a row to rest
on.

---

## Rules in every mode

### Ownership

Each element belongs to exactly one document. Do not restate content owned
elsewhere; point to it in one line.

- `requirements.md` — intent, scope, journeys, observable behavior, functional
  and non-functional requirements, capability commitments, constraints,
  acceptance expectations, strong preferences, deferred capabilities, non-goals
- `architecture.md` — drivers, system context, top-level shape, trust and
  authority boundaries, major information flow, principles, structural
  trade-offs
- `system-design.md` — component catalogue, responsibilities, authority
  boundaries, conceptual interfaces, session and turn model, persistence
  responsibilities, retrieval and structured-data subsystems, technology map
- `workflow-design.md` — behavior over time: turn execution, stages, routing,
  handoffs, follow-ups, bounds, status transitions, degradation
- `data-and-evidence.md` — evidence admission, citations, candidate causes,
  causal claims, brief contract, handoff semantics
- `runtime-and-deployment.md` — runtime design, Azure deployment realization,
  operational verification, in three explicit parts
- `evaluation.md` — corpus, ground truth, baselines, metrics, ablations,
  reporting
- `decisions.md` — settled choices only: ID, status, decision, rationale,
  accepted cost, pointer to the owning design section
- `code-guidelines.md` — implementation and merge rules binding code to the
  design; references canonical contracts rather than redefining them
- `horizontal-execution-plan.md` — the layer wise implementation sequence: slices, their
  dependencies, what each must include
- `vertical-execution-plan.md` — the vertical slice wise implementation sequence: slices, their
  dependencies, what each must include
- `status.md` — what the repository currently is, measured against the design:
  implemented, partially implemented, and missing capabilities, what coexists
  temporarily, and what has been verified. Sequence belongs to the plans

`status.md`, `horizontal-execution-plan.md` and `vertical-execution-plan.md` are not design documents.
Never put implementation status, gap identifiers, or build progress in one that
is a design document.

### Strong preferences do not propagate

They live in `requirements.md` and nowhere else. No other document designs for
them, reserves structure for them, or plans against them. They carry no
identifiers. Promotion requires assigning an identifier in `requirements.md`
first.

### Do not compare against the old design

- `docs/archive/` holds a previous, broader version. Do not read it, reference
  it, or explain a decision by contrasting with it — no "instead of X," "unlike
  the previous approach," "simpler than Y."
- These documents describe the system as it is meant to be, not a defense of it
  against an alternative.
- Do not write anything that reads as a transcript of the conversation that
  produced a decision.

### Do not ground design documents in the codebase

`status.md` is the only file that records what is built. Do not survey the
repository, run tests, or check implementation status to inform a design
document, and do not add build status, completion markers, or "not yet
implemented" notes to one.

This is the one rule `status.md` inverts: it is grounded in the repository by
definition, and every claim in it must trace to something inspected.

### Scope discipline

- This is a bounded demonstration system, not a production incident-management
  platform. Do not propose high availability, disaster recovery, multi-region
  operation, distributed workflow infrastructure, tenancy, or compliance
  machinery.
- Do not reintroduce durable suspension, per-stage checkpoint recovery, or
  recovery-scanner machinery. Session state may be lost on restart; completed
  records, traces, and evaluation artifacts persist.
- Prefer removing machinery to preserving it. Prefer fewer components to more.
- Do not invent ID schemes, taxonomies, phase or stage numbering, or maturity
  levels. Only requirements and decisions carry identifiers.
- Architecture-level documents use concept-level language. Vendor and product
  names belong in system design, decisions, and runtime documents.

### Files

- Touch only the file the prompt names. Do not modify, reformat, or tidy any
  other.
- Never run git commands unless explicitly instructed.
- Do not create files that were not requested.

### When something looks wrong

Stop and ask. An internal contradiction, a stale reference, or a conflict between
documents is a question for the author, not a defect for the agent to repair.