# OpsPilot: instructions for the coding agent

OpsPilot is an educational Agentic AI capstone: an incident-investigation assistant over a
synthetic environment, built to make agentic ideas visible. It is small on purpose. Prefer removing
machinery to keeping it, fewer components to more, a scoped edit to a rewrite. The burden of proof
is on adding, never on omitting. The one thing simplification must not remove is the agentic
behavior the system exists to demonstrate; the governing design says what that is.

## Where truth lives

- `docs/requirements.md` defines what OpsPilot must accomplish. Frozen.
- The governing design defines the target system: `docs/architecture.md`, `system-design.md`,
  `workflow-design.md`, `data-and-evidence.md`, `runtime-and-deployment.md`, `evaluation.md`,
  `decisions.md`, `code-guidelines.md`. Settled. Do not reopen architecture or requirements from
  an implementation task.
- `docs/status.md` is the single source of current implementation truth.
- `docs/cascade-inventory.md` is the migration and retirement handoff for execution planning.
- `docs/horizontal-execution-plan.md` and `docs/vertical-execution-plan.md` are two valid
  sequencing views over the same implementation. They are not sources of implementation truth;
  the repository and `status.md` are.

`docs/code-guidelines.md` is binding on every change to code, tests, configuration, and
infrastructure, and it owns the testing policy and the gates. It does not load with this file:
read it before writing code. Ownership and editing rules for everything under `docs/` are in
`docs/CLAUDE.md`.

## The two plans

Horizontal builds technical capabilities or layers progressively; a step may complete a layer or
only the portion it declares. Vertical builds the smallest coherent functional increment using the
final architectural seams: narrow but final. Never build a disposable interim architecture (one
model call, then a temporary tool loop, then a temporary multi-agent path, then the real graph
later). If a vertical slice needs the real graph, the real grounding boundary, or the real
persistence seam, use the final seam narrowly from the start.

Executing either plan to completion produces the same final repository and hosted OpsPilot. The
plans differ only in sequencing. Neither may invent functionality or abstractions the governing
design does not require.

There is no default plan. If asked to "implement the next step" without Horizontal or Vertical
being named, ask which plan. Do not infer it from the previous PR, the conversation, or which plan
looks further along. If the plan and step are named, execute that step.

## Executing a step

Eligibility comes from the current repository, not from history. Before implementing: read the
step's Consumes, inspect `docs/status.md`, inspect the relevant code where needed, and verify every
prerequisite actually exists. If one is missing, stop and report. Do not build the missing
prerequisite; the only things you may build are inside the selected step's scope. This matters
because the user alternates between the two plans.

Completion comes from the current repository too: the step is complete when the repository
provides what the step says it provides and any obsolete implementation the step names is absent.
A step may already be fully or partly satisfied by work that landed through the other plan; do
not rebuild what exists, implement only the remaining declared scope.

One plan step is normally one PR. That is a scope rule, not a size target: a PR may be substantial
if that is the coherent unit, and work is not split into micro-PRs or merged into one large PR
for count. Split only for a real technical reason (prerequisite separation, an independently risky
migration, a deployment boundary, a change too large to review coherently). Multiple commits are
fine; keep the trailing status and plan bookkeeping in the same PR, not a separate one.

Every plan step states its hosted effect: None (no hosted behavior changes; no ceremonial deploy),
Data (prepared corpus, database, or vector state changes; publish and verify the data, no app
redeploy unless code changed), Application (deploy the application and run the relevant hosted
proof), Infrastructure (deploy the affected infrastructure or configuration and verify it). A step
without one is an incomplete definition; report it.

## Implementation discipline

- Implement only the selected step. Do not start the next one because this finished early, do not
  generalize a seam for hypothetical work, do not add speculative contracts or extension points.
- Boundaries are typed where necessary; ordinary implementation stays ordinary Python. No class,
  enum, protocol, validator, or abstraction layer unless the final design needs it.
- Deletion first. Superseded code disappears as soon as its replacement makes that safe. Both
  plans may name the same retirement as "if present, remove"; whichever plan gets there first
  deletes, and the later arrival finds the absence and does nothing. Never keep obsolete code
  because it exists, has tests, or cost effort, and never defer known retirement into a generic
  cleanup stage when the owning replacement is landing.
- The design is a ceiling. If a step seems to need something the design does not carry (queues,
  workers, checkpointing, approval stages, another agent, another database, a model call for
  presentation, provider abstractions), the approach is wrong: re-read the design, and if it still
  seems necessary, stop and ask. No silent fallbacks: an approach that will not work is a human
  revision to `docs/decisions.md`, never a `try:` block that quietly takes the rejected path.
- Never assert repository state you have not checked in this session. Grep before calling
  something absent; read a file before describing it; report what you did not find.
- Do not create files that were not requested. For a quick behavioral check prefer an inline
  `uv run python -c` over a throwaway test file.

## After a step lands, in the same PR

1. Update `docs/status.md` first so it describes the repository as it now is. Add, move, or remove
   rows as the truth requires; every statement traces to something inspected.
2. Re-evaluate both execution plans against the updated status. Edit each only where the current
   repository changes whether a step's completion condition holds, partly holds, or does not hold.
   Status is the synchronization point; a Vertical landing may satisfy Horizontal steps and the
   reverse. No second progress model inside the plans, no cross-plan bookkeeping.
3. These three edits are execution bookkeeping and need no separate documentation prompt or mode.
   They may not redesign future steps, change the target, invent scope, or redefine unrelated
   completion conditions. If the landing exposes a real problem in a future step or in the design,
   record the discrepancy and report it; do not silently redesign.

## No plan or document vocabulary in implementation

Plan step identifiers, stage or layer names, requirement and decision identifiers, document
section numbers, and migration terminology appear nowhere in source, comments, tests,
configuration, branch names, commit messages, PR titles, or PR descriptions unless the user asks
for traceability there. Say what the code does and why, technically ("replace the fixed evidence
sequence with bounded adaptive capability selection"), not where the instruction came from. The
pre-commit hook and CI enforce the plan-vocabulary part repository-wide.

Completion notes in a plan point at `status.md`, the implementing PR or commit, or a stable
artifact; not at dense requirement or design citations.

## Tooling and safety

- `uv` for everything: `uv sync --group dev --group data`, `uv run pytest -q`, `uv run mypy`,
  `uv run ruff check .`, `uv run ruff format --check .`. Never `pip`, never bare `python -m`. The
  gates `code-guidelines.md` names pass before a step is presented as done, run with the exact
  CI-lane commands and groups.
- Enable the hook once per clone: `git config core.hooksPath .githooks`.
- No em-dash on any line you write, in code or prose. Use a hyphen, colon, or shorter sentence.
- Never run git commands that change state (add, commit, branch, checkout, push, merge, rebase,
  delete) unless the user explicitly instructs it in that turn. Never force-push, rewrite history,
  or bypass hooks. Read-only git is fine.
- Never edit `docs/requirements.md` or a governing design document from an implementation task.
  If the code proves the design wrong, stop and report: file, section, what the code established,
  why the text cannot stand, the recommended change, and whether the step is blocked.
- Contradictions between documents, stale references, and instructions that cannot be satisfied
  as written are questions for the author. Surface them with a recommended default; do not repair
  them silently.
