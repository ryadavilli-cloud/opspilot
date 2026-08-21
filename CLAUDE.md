# OpsPilot: instructions for the coding agent

OpsPilot is an educational Agentic AI capstone: an incident-investigation assistant over a
synthetic environment, built to make agentic ideas visible. The designed implementation is
complete; the work here is maintenance of a finished system, not execution against a plan. It is
small on purpose. Prefer removing machinery to keeping it, fewer components to more, a scoped edit
to a rewrite. The burden of proof is on adding, never on omitting. The one thing simplification
must not remove is the agentic behavior the system exists to demonstrate; the governing design
says what that is.

## Where truth lives

- `docs/requirements.md` defines what OpsPilot must accomplish. Frozen.
- The governing design defines the system: `docs/architecture.md`, `system-design.md`,
  `workflow-design.md`, `data-and-evidence.md`, `runtime-and-deployment.md`, `evaluation.md`,
  `decisions.md`, `code-guidelines.md`. Settled and authoritative. Do not reopen architecture or
  requirements from an implementation task.
- The repository itself is the description of what is actually built. What exists is answered by
  inspecting the tree, never by a tracking document, and no such document is to be created.
- `docs/engineering-notes.md` records durable findings from building, evaluating, and hosting the
  system: observations from the recorded work, not guarantees about future runs.
- `README.md` and `docs/DEMO.md` are the presentation surface. Every tree-checkable claim in them
  is verified against the repository before it is written.

`docs/code-guidelines.md` is binding on every change to code, tests, configuration, and
infrastructure, and it owns the testing policy and the gates. It does not load with this file:
read it before writing code. Ownership and editing rules for everything under `docs/` are in
`docs/CLAUDE.md`.

## Changing the implementation

- Every change remains faithful to the governing design. If a requested change cannot be made
  faithful to it, stop and report the conflict: which document, what the request needs, why the
  two cannot both stand, and a recommended resolution. Do not silently change the design and do
  not silently narrow the request.
- The design is a ceiling. If a change seems to need something the design does not carry (queues,
  workers, checkpointing, approval stages, another agent, another database, a model call for
  presentation, provider abstractions), the approach is wrong: re-read the design, and if it
  still seems necessary, stop and ask. No silent fallbacks: an approach that will not work is a
  human revision to `docs/decisions.md`, never a `try:` block that quietly takes the rejected
  path.
- Deletion lands with replacement. Superseded code does not linger beside what replaces it, and
  nothing is kept because it exists, has tests, or cost effort.
- No speculative abstraction, no reserved field, no extension seam for a future the requirements
  do not carry. Boundaries are typed where necessary; ordinary implementation stays ordinary
  Python.
- Never assert repository state you have not checked in this session. Grep before calling
  something absent; read a file before describing it; report what you did not find.
- Do not create files that were not requested. For a quick behavioral check prefer an inline
  `uv run python -c` over a throwaway test file.
- The gates pass, without suppression, before a change is presented as done, run with the exact
  CI-lane commands and groups: `uv sync --group dev --group data`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy`, `uv run pytest -q -m "not llm"`. Do not weaken
  lint, type, or test configuration to get green.

## Vocabulary

Execution-plan identifiers, stage or slice names, document section numbers, and migration
terminology appear nowhere in source, comments, tests, configuration, branch names, commit
messages, PR titles, or PR descriptions. Say what the code does and why, technically. The
pre-commit hook and CI enforce this repository-wide; keep those checks intact.

## Tooling and safety

- `uv` for everything. Never `pip`, never bare `python -m`.
- Enable the hook once per clone: `git config core.hooksPath .githooks`.
- No em-dash on any line you write, in code or prose. Use a hyphen, colon, or shorter sentence.
- Never run git commands that change state (add, commit, branch, checkout, push, merge, rebase,
  delete) unless the user explicitly instructs it in that turn. Never force-push, rewrite history,
  or bypass hooks. Read-only git is fine.
- Never edit `docs/requirements.md` or a governing design document from an implementation task.
  If the code proves the design wrong, stop and report: file, section, what the code established,
  why the text cannot stand, the recommended change, and whether the work is blocked.
- Contradictions between documents, stale references, and instructions that cannot be satisfied
  as written are questions for the author. Surface them with a recommended default; do not repair
  them silently.
