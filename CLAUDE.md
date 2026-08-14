# OpsPilot — standing instructions

Governs implementation work anywhere in this repository. `docs/CLAUDE.md` governs
edits to files under `docs/` and wins for the file being edited.

---

## Operating principle

This is a bounded demonstration system. It is small on purpose, and every rule
below exists to keep it that way.

Prefer removing machinery to preserving it. Prefer fewer components to more.
Prefer a scoped edit to a structural rewrite. When no requirement justifies a
piece of code, the correct action is deletion, not a smaller version of it.

Thoroughness here means closing exactly what the current slice names, not
everything nearby that looks unfinished. An absence is not a gap unless
`status.md` says it is.

The burden of proof is on adding, never on omitting.

---

## The accepted design is a ceiling

The documents describe what the system needs. They are not an invitation to
elaborate each concept into a subsystem. Implement the concept; do not expand it.

- Three agents means three agents — not a framework with configurable agent
  registration.
- Six boundaries means logical ownership — not six deployed services.
- One MCP boundary means one real protocol demonstration — not an MCP platform.
- Structured query means the bounded accepted structure — not a text-to-SQL
  engine.
- Retrieval means the accepted lexical, dense, fusion, and deterministic
  promotion path — not a search platform.
- Investigation persistence means completed-turn artifacts — not durable
  workflow state.
- Activity means a compact projection of instrumentation facts — not an event
  architecture.
- Evaluation means the accepted evaluation layers — not a scoring framework.
- Azure deployment means the accepted small hosted composition — not a landing
  zone.

An abstraction is justified when it removes real duplication or enforces an
accepted seam. Otherwise leave the code explicit.

---

## Existing code has no presumption of survival

Much of the repository predates the accepted design. A module is not retained
because it works, has tests, took effort to build, looks production-ready, or is
reusable in theory.

Keep it only when all three hold: it directly serves the accepted design, it is
the simplest realization of that, and it drags no obsolete concept or dependency
along with it.

Prefer deletion to wrapping obsolete machinery in an adapter. Do not repair
obsolete architecture. A temporary adapter exists only where the plan explicitly
permits coexistence, and it dies in the slice the plan names.

---

## Never add

Not in code, tests, Bicep, config, or a document. Not stubbed, scaffolded,
feature-flagged, or reserved structure for:

- Queues, workers, background jobs, outboxes, durable dispatch
- Checkpointing, replay, per-stage recovery, recovery scanners, durable
  suspension
- Approval, review, or publication stages; report versioning or publication
  identity
- Escalation as a status
- Leases, fencing, epochs, multi-replica coordination, sticky routing
- Idempotency indexes, version salts, accept-once index containers
- Per-user or role-based concurrency admission; role or group authorization
- High availability, disaster recovery, multi-region, tenancy, compliance
  machinery
- Dynamic capability registration, plugin registries, runtime discovery,
  dependency-injection frameworks
- Another agent of any kind — reviewer, planner, narrator, critic — or
  reflection loops, recursive delegation, autonomous background agents
- A model reranker
- A model call whose only purpose is presentation
- Another database, container, screen, or frontend application
- Provider or backend abstraction for providers OpsPilot does not use
- An Azure service no accepted document requires
- Retries, caches, or timeouts beyond what the owning document specifies

If implementing something appears to require one of these, assume first that the
implementation approach is wrong and re-read the accepted design. If it still
appears necessary after that, stop and ask. Do not implement it and flag it.

**No silent fallbacks.** When an accepted approach will not work, the answer is a
recorded revision in `decisions.md`, made by a human, before the code changes.
Never a `try:` block that quietly takes the rejected path.

---

## Do not simplify away the agentic behavior

Every rule above pushes toward less. This one pushes back, and it is not
optional: the agentic behavior is what the system exists to demonstrate.

These stay real and model-directed. Do not replace one with a deterministic
script because scripting it is easier or more testable:

- Supervisor judgment, held apart from deterministic control
- Evidence Investigator selecting sources from what has been observed
- RCA Analyst synthesis
- Proposal and authorization as separate acts
- Evidence paths that adapt to what was found
- Retrieval influencing the investigation
- One bounded further-evidence cycle
- Model-directed capability use, and the structured-query proposal
- Task-based model routing
- Evaluation of agent behavior, not just of outputs

Simplify the realization. Preserve the concept.

---

## Models judge, code controls

Keep the seam obvious. Models interpret objectives, choose sources, propose
actions, synthesize, and answer bounded follow-ups. Deterministic code owns
validation, authorization, bounds, reference resolution, admission, grounding,
persistence ordering, read-only enforcement, cancellation, transport, and the
activity projection.

Do not ask a model to make a decision the design deliberately made
deterministic. Do not add a model call for convenience.

---

## Contracts to honor

Violating one of these silently changes what the system means.

- **Two-axis capability results.** Whether the operation executed and how
  complete its answer was are separate axes. `succeeded + empty` and
  `unavailable` stay separately representable, separately admitted, separately
  visible. No code reads a tool result as a boolean.
- **Admission is the only door.** Nothing becomes evidence except through
  deterministic admission, which assigns its reference. Every operation that did
  not answer produces a limitation naming the question it failed to answer.
- **The registry is the only path to a source.** Explicit static mapping.
  Nothing registers itself.
- **Every source call carries a deadline** no greater than the turn's remaining
  time. A call that outlives its turn is a violation even when its data is
  correct.
- **No numeric confidence anywhere** in the assessment.
- **Model routing is by task label alone.** No severity, confidence, cost, or
  runtime signal. No fallback chain.
- **Retrieval returns passages** with source, collection, and provenance — never
  identifiers alone.
- **The grounding gate is structural.** It checks shape and reference
  resolution. It does not judge meaning.
- **One writer, one artifact.** The Supervisor writes the completed-turn record.
  A terminal success cannot be emitted before that commit succeeds.
- **No query text is constructed anywhere.** The structured-query path validates
  a bounded structure and executes it read-only under a limit and a timeout.

For exact vocabularies — outcome values, citation roles, support labels,
provenance categories, stream statuses — read the owning document. Do not
reconstruct one from surrounding code. Do not extend one because a case looks
uncovered; an uncovered case is a question, not a new enum member.

---

## Runtime posture

One application, one process, one streaming request owning a turn. Active-turn
state is ephemeral. Only completed turns persist, committed before successful
terminal delivery. Zero-to-one hosted replica. No durable active-turn recovery.

The engineer-facing surface is one screen: intake and follow-up, a compact
activity feed, the brief as the dominant element, one expandable details area.
Not a portal. No dashboards, admin views, trace viewers, or configuration
screens. Activity exists to make useful agent behavior visible, not to expose
internals.

---

## Slice discipline

THere are two different plans available - vertical and horizontal. Each task or 
slice can come from either document. However, it should always be the next step
 in the corresponding document. 

`horizontal-execution-plan.md` owns the horizontal execution plan order. 
These are the rules for the horizontal execution plan slices. 

- A slice leaves the tree green. One that cannot is too big — say so rather than
  splitting it yourself.
- **Replaces, does not extend.** The old path dies in the slice that supersedes
  it. No parallel implementations, no switch flags, no "until the new one is
  proven."
- Do not start the next slice because this one finished early.
- Do not implement what a later slice owns because you are already in the file.
- Do not add a caller to a module the plan schedules for deletion.
- Do not create a second implementation of a contract that already has one.
- Nothing is committed until the local pass for the slice has been reviewed.

Write the tests the slice names — the ones a reviewer would not predict.
Ordinary unit coverage is assumed and needs no discussion.

Evaluation is advisory and gates no merge. No numeric target before a measured
baseline exists; no baseline re-set downward without recorded justification.


`vertical-execution-plan.md` owns the vertical execution plan order. 
These are the rules for the vertical execution plan slices.

Each slice must produce something that can be run, observed, tested, or demonstrated.

Prefer:

> contract + minimal implementation + tests + visible behavior

over:

> framework + infrastructure + abstractions now, useful behavior later.

A PR should have one primary completion claim.

Do not create broad horizontal PRs such as:

* "add orchestration framework";
* "build common infrastructure";
* "introduce extensibility layer";
* "create generic repository framework";
* "add event architecture";
* "prepare for future agents."

Build only the infrastructure required by the vertical behavior currently being implemented.



---

## When the documents are silent

A gap is not the same as a contradiction. A contradiction stops work; a gap
usually does not.

1. Confirm the authoritative documents genuinely do not answer it — check
   `decisions.md`, `status.md`, and the plan before concluding they are silent.
2. Choose the smallest local, reversible implementation that preserves the
   accepted intent.
3. Do not create a subsystem to fill a documentation gap.
4. Record what was implemented in `status.md`.

Stop and ask instead whenever the answer would expand architecture,
dependencies, runtime components, persistence concepts, or scope. Those are not
gaps to fill on your own authority.

---

## Verification

Never assert repository state you have not checked in this session. Read the file
before describing it. Grep before calling something absent. Report what you did
not find, not only what you did.

`status.md` is the only file that records what is built. If your work changes
what is true about the repository, that is a `status.md` edit — and only where
inspection contradicts what is written. A row never changes because reasoning
suggests it should.

Status is anchored to the design, not to a plan. It carries no slice identifiers,
no stage or layer numbering, no sequence, and no statement of what comes next.
Work that landed ahead of the sequence describing it is simply built.

Both halves run at every landing, as part of the definition of done: status
records what was built, and every slice whose subject that landing touched
re-derives its marker from status. Updating one without the other leaves derived
data stale and silently wrong, and nothing else in the repository will catch it.

Design documents describe intent. Never add build status, completion markers, or
"not yet implemented" notes to one.

---

## Documents

Each element belongs to exactly one document; point to the owner rather than
restating it. Ownership, source precedence, and the three editing modes are in
`docs/CLAUDE.md`. Do not author or modify anything under `docs/` unless the
prompt names the file and names a mode.

`status.md`, `vertical-execution-plan.md` and `horizontal-execution-plan.md` are not design documents.

`NFR-NOTE` comments mark where production hardening would attach. They are
markers, not TODOs. Do not implement one.

---

## Code guidelines

`docs/code-guidelines.md` is binding on every change to code, tests,
configuration, and infrastructure. **It does not load with this file.** Read it
before starting implementation work, not after the code is written.

Sixteen sections. The merge gates are §13 Merge Standards, which carries the
definition of done, §14 Prohibited Patterns, and §16 Change Scope, Deletion, and
Proportion. A change is checked against those three before it is presented as
done.

Do not cite a section number from memory. The numbering has changed before, and
a confident wrong citation is worse than looking it up.

Two rules are enforced mechanically, by CI and by `.githooks/pre-commit`, so a
violation fails before the push rather than after it:

- **§12, no execution-plan vocabulary outside `docs/`.** Stage, phase, layer,
  gap, slice, and PR-sequence identifiers, and references to a plan document or
  one of its sections, appear nowhere in code, tests, configuration,
  infrastructure, prompts, log strings, or names, and in no commit or
  pull-request title or body. Say what the code does and which contract it
  satisfies; delete the comment where nothing remains once the identifier is
  gone. Requirement, NFR, and `D-nnn` identifiers stay: they resolve.
- **Lint and formatting, repo-wide** rather than scoped to touched files.

A fresh clone does not have the hook enabled: `git config core.hooksPath
.githooks`.

---

## Toolchain

- `uv` for everything: `uv sync --group dev --group data`, `uv run pytest -q`,
  `uv run mypy`, `uv run ruff check .`. Never `pip`, never bare `python -m`.
- All four pass before a slice is presented as done.
- For a quick behavioral check, prefer an inline `python -c` under `uv run` over
  a throwaway test file.
- **Never run git commands** — add, commit, branch, checkout, push, delete —
  unless explicitly instructed.
- Do not create files that were not requested.

---

## Stop and ask

An internal contradiction, a stale reference, a conflict between documents, or an
instruction that cannot be satisfied as written is a question for the author, not
a defect to repair.

Do not resolve it, work around it, note it and proceed, or fix it silently
because the fix seemed obvious.

Surface open forks explicitly, each with a recommended default. Do not leave an
ambiguity unstated, and do not resolve one on your own authority.