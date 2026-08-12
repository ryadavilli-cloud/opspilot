# OpsPilot - Status

**Purpose:** record current implementation truth against the accepted OpsPilot design: what is
built, what coexists temporarily, what is verified, and what is next. This document does not
sequence work or restate design intent; `vertical-execution-plan.md` owns the implementation
sequence, and `requirements.md`/`architecture.md`/`system-design.md`/`workflow-design.md`/
`data-and-evidence.md`/`runtime-and-deployment.md`/`evaluation.md` own the accepted design.

Every claim below traces to a command run or a file read in the session that recorded it. A row
changes only where the repository contradicts what is written here, never because a plan implies
it should.

## 1. Current Baseline

- **Inspected commit:** `main` at `3fd7a1c` ("A question the model may ask, in a shape it cannot
  widen", #74), 2026-08-12.
- **CI-equivalent lanes, both green at this commit:**
  - Core lane (`uv sync --group dev --group data`; `ruff check .`; `mypy`; `pytest -q -m "not llm"`):
    ruff clean, mypy clean (no errors), **667 passed, 8 skipped, 3 deselected, 1 xfailed** (18.9s).
  - Full lane (`uv sync --group dev --group data --group eval`;
    `pytest -q -m "not reranker and not llm"`): **703 passed, 5 deselected, 1 xfailed** (208s).
  - `ruff format --check` was not run repository-wide; CI itself only checks files a change
    touches (`.github/workflows/deploy.yml`), so a repo-wide result would not reflect what CI
    enforces.
- **S-0, S-1, and S-2 are complete.** S-3 is the next slice.

## 2. Completed Slices

Retained only for what remains to consume. Full detail, dependencies, and completion evidence are
in `vertical-execution-plan.md`.

**S-0, baseline cleanup.** The authoritative `docs/` set is committed. The unpushed durable-dispatch
WIP is abandoned (never an ancestor of `main`). Dead severity-tier configuration, stray files, and
corpus-path duplication are removed. `README.md` and `.env.example` describe the running system.

**S-1, turn identity and streaming transport.** Turn identity (`turn/identity.py`); the stream
envelope with its fixed ordering (identity first, close marker last,
`stream/contracts.py`/`stream/projection.py`); the normalized incident-context contract for
predefined intake (`intake/contracts.py`, `decisions.md` D-007); the `InteractionKind` type (shape
only, no classifier yet); the activity projection, derived from the same telemetry facts it
describes; client-disconnect detection on the streaming request; the one-screen client at
`/investigation` (`static/investigation.html`).

**S-2, evidence, capability results, assessment, and the record port.** The evidence reference
model with one parser and resolver, including the `absence:` form for an authoritative empty result
(`evidence/references.py`, `decisions.md` D-008); the two-axis execution-outcome/completeness
capability result vocabulary and Evidence Access Layer admission that assigns every reference and
records a limitation for every operation that did not answer (`tools/contracts.py`,
`evidence/admission.py`); the assessment, candidate-cause, recommendation, limitation, and brief
contracts, with qualitative support labels and no numeric confidence anywhere
(`assessment/contracts.py`); the task-labelled `rca_synthesis` model call and deterministic brief
projection (`assessment/synthesis.py`, `assessment/brief.py`); the Investigation Record port and its
commit-ordering contract over an in-memory backend (`record/port.py`, `record/memory.py`); capability,
model, and admission spans carrying `investigation_id`/`turn_id`; the replay cassette
(`eval/cassettes/turn_synthesis.json`) that keeps synthesis deterministic in CI.

**Landed ahead of its owning slice:** the governed structured-query path (bounded query structure,
static three-collection schema map, deterministic validation before execution, translation to one
parameterized read-only Cosmos query, admission through the same two axes) is implemented
(`data/structured_query.py`, `tools/structured_query.py`), verified against the live
`operational-records` container across six cases. This is the capability `vertical-execution-plan.md`
schedules as S-10; that slice's remaining scope is narrowed accordingly.

## 3. Current Capability Status

| Capability | Status | Note |
| --- | --- | --- |
| Streaming turn transport, activity projection, one-screen client | Implemented | S-1. No cancellation signal yet (disconnect only); no accepted terminal outcome yet. The client handles the identity, activity, and close events and has no branch for the brief, so a rendered brief arrives and is visible only in the details area |
| Predefined intake normalization | Implemented | S-1. Free-text normalization and clarification are S-5 |
| Evidence reference model, two-axis capability results, EAL admission | Implemented | S-2 |
| Governed structured query | Implemented | Landed ahead of S-10; see above |
| Assessment contracts, one bounded synthesis call, deterministic brief projection | Implemented | S-2. Renders a brief but does not conclude a turn |
| Investigation Record port and commit-ordering contract | Implemented, in-memory backend only | S-2. No real commit is exercised yet; the artifact this port stores does not exist until S-3 |
| Four grounding checks, correction allowance, outcomes, commit, completed-turn artifact | Missing | S-3, next |
| Explicit turn controller (LangGraph replacement) | Missing | S-4 |
| Three-agent split (Supervisor / Investigator / Analyst) | Missing | S-5 |
| Explicit cancellation signal and safe-boundary cancellation | Missing | S-6. Disconnect detection exists (S-1) |
| Durable Cosmos-backed completed-turn persistence | Missing | S-7. `investigations` container exists and is empty |
| Follow-up, handoff, redirect, supplied context | Missing | S-8 |
| Accepted retrieval (embeddings + Cosmos vector + lexical + RRF + deterministic promotion) | Missing | S-9. Old BM25/dense/rerank stack still present, slated for deletion |
| MCP: single accepted exposure | Missing | S-11. Three old exposures (`get_incident`, `query_logs`, `search_runbooks`) still served |
| Further-evidence cycle | Missing | S-12 |
| Categorical evaluation, judge, baselines, report | Missing | S-13. Golden scenario records and cassette replay exist |
| Hosted alignment (replicas, built-in auth, Application Insights) | Missing | A-0/A-1. Old composition is deployed and green (section 5) |

## 4. Temporary Legacy Coexistence

Every item below is scheduled for deletion in `vertical-execution-plan.md`'s coexistence register;
this section only summarizes what still runs and why.

| Legacy component | Still does | Deleted in |
| --- | --- | --- |
| LangGraph orchestration (`graph.py`, `nodes/investigation.py`, `router.py`, `checkpoint.py`) + `langgraph`, `langchain-core`, `langgraph-checkpoint-sqlite` | Old five-stage-plus-HITL pipeline behind `/investigate` and the async job API | S-4 |
| Async job API (202+poll, decision endpoint, `CommittedDecision`, lease/fencing) | Old turn lifecycle | S-4 |
| Old approval console (`static/console.html`) | Submit/poll/review/approve UI at `/console` | S-4 |
| Legacy `contracts.py`, `diagnosis/{admission,cycle,llm_planner,planner,sufficiency,render}.py`, `triage.py`, `composition.py` | Old report/claim model and planner/triager selection | S-4 (contracts, admission if redundant with S-3's gate) / S-5 (planner, triage, sufficiency; `render.py` orphaned once both its callers are gone) |
| `guardrails/policies.py` two-policy grounding | Citation-in-produced-refs check ahead of the old `hitl_gate` | S-3 introduces the four-check gate; the old wrapper coexists until S-4 |
| Three-role hand-rolled JWT auth (`auth.py`, `pyjwt`) | Guards the old async endpoints only; the new `/turns` endpoint is unauthenticated | S-4 (roles) / A-0 (built-in auth replaces the seam) |
| Deprecated `EvalTargets` numeric thresholds | Consumed by `eval/scenario_eval.py` and the old scorecard gates | S-4, with the gates that read it |

## 5. Current Data and Azure Status

**Corpus:** seven authored incidents (`inc-001` to `inc-007`) across five families, closure-verified,
chronology and answer-leakage repairs landed 2026-08-08. Golden scenario records exist per
`data/answer_key/golden_scenarios.yaml`. One open corpus item remains: templated noise realism (905
near-identical error strings, no pre-incident baseline history), owned by S-12.

**Cosmos (last live-inspected 2026-08-11, read-only; not re-verified this session):**
`retailease/knowledge` (196 passages from 28 documents, 1536-dim vector policy, populated) and
`retailease/operational-records` (14,013 documents across six kinds, hierarchically partitioned by
`/kind` then `/service`) are both live and read by the accepted capabilities. `opspilot/investigations`
exists and is declared in Bicep but holds nothing; the runtime commits nothing to it, since the
completed-turn artifact it will store does not exist until S-3. The application identity holds
data-contributor scoped to `investigations` alone and data-reader scoped to the whole `retailease`
database; the corpus setup principal holds data-contributor on `retailease` separately.

**Hosted deployment (last live-inspected 2026-08-09, not re-verified this session):** green, at the
old composition: `opspilot-api` Container App, 0-3 replicas (target is 0-1), one `gpt-5-mini` chat
deployment plus a `text-embedding-3-small` embedding deployment, no Application Insights, hand-rolled
three-role JWT auth in front of the old endpoints. A-0 and A-1 own bringing this to the accepted
six-service composition.

## 6. Open Decisions and Issues

- **D-004 (MCP library and realization) is the only open decision gate.** Still pending library
  inspection; blocks S-11 implementation only, nothing else.
- **D-005 and D-006 are both Accepted**, with every criterion in D-006's selection table naming a
  real incident identifier. Neither is an open gate. `vertical-execution-plan.md` had retained
  language treating them as decisions still to be made in S-9, S-12, and S-13; that language has
  been corrected to consume the accepted answers instead.
- **One disclosed, out-of-scope regression is carried as an xfail** (the single `xfailed` in both
  lanes above): `tests/test_single_agent_gate.py::test_single_agent_beats_the_deterministic_floor`.
  The corpus repair added metric evidence the deterministic fixed plan sweeps incidentally but the
  legacy single-agent LLM planner does not request, so it no longer strictly beats the floor. The
  test's subject is old-architecture machinery already named for deletion, so the fix is the
  deletion rather than repairing the planner's tool selection.
- **One open question is not a decision gate and has no decision record.** If free-text intake
  clarifies through a short-lived normalization token, that token needs an explicit signing, expiry,
  and payload contract; a simpler resubmission path is preferred where it meets the requirement.
  Nothing in the repository takes a position either way, since no clarification path exists yet, so
  the absence of a token is not evidence the simpler path was chosen. It blocks S-5 and nothing
  else. Recorded here because the reconciliation inventory that carried it was retired and the
  question was not answered with it.
- No contradiction was found between `decisions.md` and the current repository.
- **One contradiction this cleanup created, not yet resolved:** `horizontal-execution-plan.md` cites
  this document roughly eighty times by heading name (`Deletion and Replacement Register`, `Detailed
  Missing and Partial Implementation Register`, `Data and Corpus Status`, and others). Those headings
  no longer exist here. The citations are stale until that plan is re-pointed, which is its own task
  and was not in this pass's scope.

## 7. Next Slice

**S-3, four grounding checks, one shared correction allowance, completed outcomes, and the first
completed turn.** Full scope, entry criteria, and completion evidence are in
`vertical-execution-plan.md`. Nothing before S-3 may deliver a completed turn; the current streamed
path (`turn/synthesis_step.py`, wired into `api.py`'s `/turns` endpoint) deliberately stops after
rendering a brief, because the grounding gate, outcome assignment, the completed-turn artifact, and
commit-before-delivery all belong to S-3.
