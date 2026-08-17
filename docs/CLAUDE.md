# Instructions for files under `docs/`

These files are authored text. An implementation task reads them constantly and edits only the
three bookkeeping files named below. Everything else changes only through a prompt that names the
file and says whether the text is supplied (reproduce it exactly), derived from a named source
(write only what traces to it, report what you left out), or to be analysed (findings only, change
nothing).

## Who owns what

- `requirements.md`: what OpsPilot must accomplish and demonstrate; scope, trust properties,
  evaluation obligations, preferences, non-goals. Frozen.
- `architecture.md`: top-level shape, authority per concern, trust boundaries, major flow,
  structural principles. Concept-level language, no product names.
- `system-design.md`: component responsibilities, permitted interactions, seams, evidence-access
  capabilities, the investigation model, the question over a completed record, technology map.
- `workflow-design.md`: behavior over time: the run, gathering and continuation, synthesis, the one
  return, grounding, correction, outcome, degradation and failure, bounds, the question.
- `data-and-evidence.md`: trust model, references, tool results, admission, evidence versus
  knowledge, the assessment field set, grounding properties, the brief, the completed record.
- `runtime-and-deployment.md`: runtime posture, transport, state, Azure resources, model
  connectivity, Cosmos realization, configuration and secrets, telemetry, hosted verification.
- `evaluation.md`: inputs, scenario behavior, deterministic correctness, the two controlled
  comparisons, the judge, the runner and report.
- `decisions.md`: settled choices only, each with why and cost; retired records keep their number.
- `code-guidelines.md`: how code stays faithful to the design; typing, invariants, dependency
  direction, testing policy and gates, change discipline. Binding on every code change.
- `status.md`: the single source of current implementation truth, measured against the design.
- `cascade-inventory.md`: the migration and retirement handoff for execution planning: what is
  reusable, missing, partial, and retired, and the rules a derived plan must honor.
- `horizontal-execution-plan.md` and `vertical-execution-plan.md`: two sequencing views over the
  same implementation, reaching the same repository. Neither is implementation truth.

Each element belongs to one document; others point to it rather than restating it. Design
documents describe intent: never put build status, completion markers, or "not yet implemented"
notes in one, and never ground a design document in the codebase.

## Precedence

`requirements.md`; then the governing design (`architecture.md`, `system-design.md`,
`workflow-design.md`, `data-and-evidence.md`, `runtime-and-deployment.md`, `evaluation.md`,
`decisions.md`, `code-guidelines.md`); then `status.md` for what exists; then the inventory and
the plans. A plan never overrides a design document, and a design document never overrides
`requirements.md`.

## Bookkeeping at a landing

Updating `status.md`, `horizontal-execution-plan.md`, and `vertical-execution-plan.md` in the same
change as the implementation is part of executing a step and needs no separate prompt or mode.

- `status.md` is edited first, to say what the repository now is. Rows may be added, moved between
  implemented, partial, missing, and superseded, or removed once the subject is deleted; factual
  descriptions may be revised. Every statement traces to something inspected in that session.
  Status carries no plan identifiers, no sequence, and no statement of what comes next; it is not
  a changelog.
- Each plan is then re-evaluated against the updated status. A step's completion is a condition
  over current repository state: its declared outputs present, its named obsolete implementation
  absent. Record where that condition holds, partly holds (with what remains), or does not hold.
  Nothing else in a plan changes at a landing: no resequencing, no new scope, no redefined
  completion conditions, no second progress model.
- A landing from either plan may satisfy steps in the other. That is expected; status is the
  synchronization point.

## When the design looks wrong

Stop and report: which file and section, what the implementation established and where, why the
text cannot stand, the recommended change, and whether the step is blocked. Do not edit the design,
do not stage a fix, do not note it in `status.md` instead, and do not proceed with code that
contradicts the design. An unworkable settled choice is a human revision to `decisions.md`; a
requirement that appears unimplementable is a `requirements.md` question. Neither is renegotiated
by implementation.

## Rules in every mode

- Touch only the file the prompt names, or the three bookkeeping files at a landing.
- Preferences listed in `requirements.md` live there and nowhere else; no other document designs
  for them or reserves structure for them.
- No em-dash on any line written. No invented identifier schemes, taxonomies, or numbering; only
  requirements and decisions carry identifiers.
- Do not compare against or explain a decision by contrast with a previous design.
- Never run git commands unless explicitly instructed. Do not create files that were not requested.
