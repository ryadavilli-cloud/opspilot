# Instructions for files under `docs/`

These files are authored text. An implementation task reads them constantly and edits none of
them. A file here changes only through a prompt that names it and says whether the text is
supplied (reproduce it exactly), derived from a named source (write only what traces to it,
report what you left out), or to be analysed (findings only, change nothing).

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
- `engineering-notes.md`: durable findings from building, evaluating, and hosting the system.
  Observations from the recorded work, phrased as such, never as guarantees about future runs. It
  is not a diary, a tracker, a changelog, or a plan.
- `DEMO.md`: how to run and read a live demonstration. It may link back into the design set to
  explain observed behavior; it promises nothing a nondeterministic run cannot keep.

Each element belongs to one document; others point to it rather than restating it. Design
documents describe intent: never put build status, completion markers, or "not yet implemented"
notes in one, and never ground a design document in the codebase. `README.md` and `DEMO.md` are
the presentation surface and must stay true to the tree: a tree-checkable claim is verified
against the repository before it is written, and historical observations belong in
`engineering-notes.md`.

## Precedence

`requirements.md`; then the governing design (`architecture.md`, `system-design.md`,
`workflow-design.md`, `data-and-evidence.md`, `runtime-and-deployment.md`, `evaluation.md`,
`decisions.md`, `code-guidelines.md`); then the repository itself for what exists. A presentation
or notes document never overrides a design document, and a design document never overrides
`requirements.md`. No document tracks implementation progress, and none is to be created for it.

## When the design looks wrong

Stop and report: which file and section, what the implementation established and where, why the
text cannot stand, the recommended change, and whether the work is blocked. Do not edit the
design, do not stage a fix, and do not proceed with code that contradicts the design. An
unworkable settled choice is a human revision to `decisions.md`; a requirement that appears
unimplementable is a `requirements.md` question. Neither is renegotiated by implementation.

## Rules in every mode

- Touch only the file the prompt names.
- Preferences listed in `requirements.md` live there and nowhere else; no other document designs
  for them or reserves structure for them.
- No em-dash on any line written. No invented identifier schemes, taxonomies, or numbering; only
  requirements and decisions carry identifiers.
- Do not compare against or explain a decision by contrast with a previous design.
- Never run git commands unless explicitly instructed. Do not create files that were not requested.
