# OpsPilot - Vertical Execution Plan

**Status:** Working implementation plan.

Vertical-slice implementation sequence derived from `docs/status.md` (repository inspected at
branch `stage-5f-durable-dispatch`, `0c3c175`; `main` at `e567adf`) against the accepted
documentation baseline (Phase 3A, 2026-08-05). The design is settled; this document owns order,
migration mechanics, ownership, and PR structure. It does not restate the accepted design and it
does not record build progress, which belongs to `status.md`.

---

## Plan operating rules

These rules govern every slice. They are stated once here rather than repeated inside each slice.

1. Every slice must leave the application runnable.
2. Every slice must produce a visible, executable, or independently testable outcome.
3. Deletion is part of implementation, not optional cleanup. A slice is not complete while the
   code it replaces is still reachable.
4. Existing code survives only with an accepted-design justification. Production suitability,
   test coverage, and effort already spent are not justifications.
5. No slice may introduce a second long-lived implementation of the same contract.
6. Temporary compatibility code must name the slice in which it is removed, and must appear in the
   coexistence register below. Coexistence without a named deletion slice is not permitted.
7. Tests for deleted behavior are deleted, not rewritten to preserve obsolete behavior.
8. Later slices must build on stabilized contracts rather than repeatedly redesigning them.
9. No completed turn is delivered before the full accepted terminal ordering has run: synthesis,
   the four grounding checks, the possible single correction, outcome assignment, commit, then
   terminal delivery. S-3 is the first slice that produces an accepted completed turn; nothing
   before it may deliver one. Backends may change; the ordering may not.
10. Any slice that resolves a pending decision or an implementation clarification must update the
    owning authoritative document, or `decisions.md`, before its implementation PR is complete.
    `status.md` records that the question was resolved; it is never the design authority for the
    answer.
11. `status.md` records current truth; this plan records remaining work. A landed slice is marked
    **Completed** and collapsed to its outcome, merge commits, and verification evidence rather
    than deleted, so that dependency reasoning, the course map, and the record of why each deletion
    happened survive. Collapsed slices move to an appendix if the plan becomes unwieldy.

Slice identifiers are stable labels, not an execution order. Execution order is the order slices
appear in this document, and it differs from numeric order in one place: A-1 runs before S-13, so
that the milestone report can include final hosted verification.

## Planning posture

- The repository materially conflicts with the target. The plan is deletion-led: the old runtime
  is cut over and removed as soon as the replacement can execute one real investigation. The plan
  does not preserve the old architecture as a safety blanket through several capability slices.
- Every slice ends with something a reviewer can run, see, or verify that was not available before.
- The plan starts from `main` (`e567adf`). The unpushed durable-dispatch WIP commit is abandoned,
  not repaired or built upon.
- Existing code survives only when it directly supports the accepted design and is the simplest
  suitable realization. Production suitability is not a reason to retain it.
- Azure is reconciled incrementally rather than in one late slice. A-0 aligns the hosted
  environment immediately after cutover, each capability slice adds only the resource it needs and
  adds it additively, and A-1 performs live deletion and complete hosted verification.
- Evaluation grows with capability. Each slice that adds behavior adds the accepted evaluation
  increment for that behavior; S-13 completes the judge, baselines, and report rather than building
  the evaluation system from nothing.
- Telemetry is emitted where behavior is added, not retrofitted. The Application Insights sink can
  wait for the hosted slice; the emission semantics cannot.
- The accepted corpus remains seven authored incidents across five families. Controlled fixture
  variants may fill evaluation classes, but the plan does not silently add authored incidents.
- Course-material sequencing is an aid, not a straitjacket.
- D-003, D-004, D-005, and D-006 remain open until a consuming slice has the evidence needed to
  resolve them, and each carries a resolution deadline below.

## Standard slice template

Every slice below uses the same fields, in this order. A field that does not apply reads "None"
rather than being omitted, so that gaps stay visible.

| Field | What it records |
| --- | --- |
| Demonstrable outcome | What a reviewer can run, see, or verify that was not available before |
| Entry criteria | What must already be true and verified before the slice starts |
| Existing foundation retained | Repository code kept, with its accepted-design justification |
| Code and data to delete | What leaves the repository in this slice |
| Code to replace | What is superseded, and by what |
| New implementation | What is built |
| Contract introduced or stabilized | Which accepted contract becomes stable here |
| Telemetry and activity impact | The authoritative instrumentation facts this slice must emit |
| Deterministic tests | Offline tests that must pass, independent of environment |
| Evaluation increment | What the accepted evaluation gains here, advisory only |
| Dataset or fixture work | Corpus, golden, cassette, or fixture changes |
| Azure impact | Execution posture and any infrastructure change |
| Decision gates | Pending decisions resolved, or explicitly still deferred |
| Explicit non-goals | What this slice deliberately does not do |
| Small PR breakdown | The PR sequence, one primary completion claim each |
| Completion evidence | The concrete artifact or run that closes the slice |
| Status updates required after landing | What must change in the status document |

## PR-size guardrails

"Small PR" means the following operationally.

- One coherent contract or behavior per PR.
- Deletion and replacement may share a PR only when the replacement is already runnable.
- Do not mix corpus regeneration, orchestration changes, and Azure changes in one PR.
- A PR has one primary completion claim. If the description needs "and also", split it.
- Infrastructure deletion is separate from code introduction wherever rollback safety requires it,
  in particular for live Cosmos containers and authentication changes.
- Do not split a single atomic contract across PRs merely to reduce line count. A contract that
  cannot compile or be tested in halves ships whole.

## Status synchronization rule

After each PR or completed slice, update `status.md`:

- update the inspected commit;
- change classifications, for example Replace to Deleted or Missing to Implemented;
- record the commands and tests actually run, with their results;
- update Azure state only when it was actually rechecked, not when it was assumed;
- record newly discovered contradictions;
- revise future plan slices only when evidence requires it.

This plan is not a progress log. Landed slices are marked Completed and collapsed per operating
rule 11; current truth lives in `status.md`.

---

## Course concept map

The original course source material is available at the repository-relative path
`..\Source Material\`. The mapping below uses the inspected chapter topics; exact deck titles
should be confirmed against the source material.

| Course chapter or topic | OpsPilot slice(s) |
| --- | --- |
| Ch 0 Python for GenAI; Ch 1 Agentic AI Foundations / calling LLMs programmatically | S-2: one bounded typed synthesis call |
| Ch 2 and Ch 3 RAG-powered knowledge agents, RAG pipelines, evaluation, anti-hallucination | S-9 retrieval; S-13 evaluation |
| Ch 4 Multi-Agent Systems | S-5 three-agent responsibility split |
| Ch 6 Agent Communication Protocols: MCP, A2A, Google ADK | S-11 MCP parity |
| Ch 7 Hybrid Search and Retrieval | S-9 semantic + lexical + RRF + deterministic promotion |
| Ch 8 Agent Observability, Evaluation and Safety | S-1 activity, S-3 grounding, S-13 evaluation, A-0 App Insights |
| Ch 13 Agentic Research Systems: planning, tools, guardrails | S-5 adaptive proposal/authorization; S-12 further evidence |
| Ch 14 Agentic Text-to-SQL | S-10 governed structured query, deliberately bounded rather than arbitrary SQL |
| Ch 5 Multimodal; Ch 9 Fine-Tuning; production-oriented LLMOps chapters | Not implementation slices: multimodal and fine-tuning are non-goals; LLMOps remains a small advisory evaluation and hosted-verification posture |

The course's multi-agent examples may use LangGraph. OpsPilot demonstrates the same concept with the
accepted explicit state machine because a graph runtime, durable checkpoints, and pause/resume are
unnecessary for this capstone. Azure is an OpsPilot-specific addition and appears once the local
executable flow can be deployed honestly.

---

## Contract stabilization

A contract is stable when its shape is fixed and later slices consume it without redefining it.
Later slices may extend a stable contract only where the accepted documents already allow the
extension. Reshaping a stable contract is a plan change, not progress.

| Contract | Stabilized in |
| --- | --- |
| Stream envelope, turn and live-session identity, activity projection | S-1 |
| Normalized incident context and request-shape interaction kind | S-1 |
| Evidence reference encoding, its single parser, and its resolver | S-2 |
| Two-axis capability result vocabulary and admitted-evidence structure | S-2 |
| Assessment, candidate cause, recommendation, limitation, brief | S-2 |
| Investigation Record port and its commit semantics, with a lifecycle contract test for delivery ordering | S-2 |
| Grounding result, completed-outcome vocabulary, completed-turn artifact, terminal ordering | S-3 |
| Turn-controller and terminal-delivery ordering | S-4 |
| Agent proposal and authorization | S-5 |
| Free-text normalization and single-clarification flow | S-5 |
| Cancellation, degradation, and cancelled-turn persistence rules | S-6 |
| Investigation Record storage layout and restart-safe resolution | S-7 |
| Follow-up, handoff, redirect, and supplied-context semantics | S-8 |
| Retrieval result and knowledge-reference model | S-9 |
| Governed-query structure | S-10 |
| MCP parity contract | S-11 |
| Evaluation scenario and fixture assignments | S-12 |
| Evaluation result and report model | S-13 |

Three entries are deliberately split across slices and none is a reshape. The Investigation Record
port and its commit semantics are fixed at S-2 over an in-memory backend, with a lifecycle contract
test proving that terminal delivery cannot occur until a commit succeeds; S-3 adds the
completed-turn artifact the port stores, performs the first real commit, and realizes the ordering
in the running turn; S-7 replaces the backend and adds the storage layout without changing the
artifact, the port, or the ordering. The evidence reference model is fixed at S-2 and S-9 extends
the same owned parser and resolver to knowledge references. The MCP result contract is carried
through the S-2 envelope change, and only its exposed capability set changes at S-11.

The assessment shape is stabilized at S-2 and the outcome vocabulary at S-3 because an accepted
completed outcome is a consequence of the grounding gate, which does not exist until S-3. S-2
therefore renders an assessment; it does not conclude an investigation.

## Decision gates

Pending decisions carry a resolution point, so that "pending" does not become "forgotten".

| Decision | Resolve when | Blocks |
| --- | --- | --- |
| D-003 Cosmos vector viability | First S-9 technical PR | Retrieval implementation choice |
| D-004 MCP library mechanics and transport carriage | Before S-11 implementation | Library usage, session handling, result carriage |
| D-005 judge rubric version | First S-13 PR | Judge implementation and removal of the standalone judge configuration |
| D-006 retrieval-influence selection | After the minimum S-9 data repair | Retrieval-influence demonstration |
| D-006 remaining corpus selections | End of S-12 | S-13 evaluation wiring |

D-003 is the only gate that can force a documented design revision rather than a recorded
selection. If Cosmos vector search proves unviable in the S-9 spike, stop and revise D-003
explicitly before falling back to an in-process cosine scan.

D-004 does not reopen hosting. One real in-process MCP boundary inside the single application and
process is frozen; D-004 settles library mechanics, session and transport handling, and result
carriage only.

## Implementation clarifications and their owners

`status.md` section 17 records questions the repository exposed. Each is answered inside a slice
before code invents an incompatible answer.

| Clarification | Owning slice | Default position |
| --- | --- | --- |
| Normalized incident-context fields | S-1 | One typed contract; the current `Alert` shape is evidence, not authority |
| Evidence and knowledge reference encoding, keys, and parsing | S-2 | One owner, one parser, one resolver; evaluate the existing frozen grammar rather than copying it |
| Stateless clarification token | S-5 | Prefer simple resubmission of the original input; introduce a signed short-lived token only if resubmission demonstrably fails the requirement |
| Evaluation artifact storage location | S-2 | Committed deterministic fixtures and reference reports under `eval/`; dated live-run outputs under a separate, gitignored, non-authoritative run directory; no database, telemetry store, or new Azure resource |
| Minimal knowledge metadata contract | S-9, first PR | Identifier, container category, promotion date, and admission provenance only. No authoritative document fixes this today, so S-9 records it before implementing rather than treating it as a precondition |
| D-004 library evidence | S-11 | In-process hosting is fixed; record the library findings |
| D-006 corpus evidence | S-9, S-12 | Selections wait for repairs and the coverage audit |
| D-003 vector viability | S-9 | Verify before choosing; an in-process cosine scan requires a recorded revision |

## Execution environment matrix

Azure is reconciled incrementally. The posture per slice is stated rather than left implicit.

- **Local deterministic:** fakes, fixtures, cassettes, in-memory repositories. Runs in CI.
- **Azure-assisted local:** the local application using real Azure OpenAI or Cosmos, for
  verification a fake cannot provide. Never a CI requirement.
- **Hosted verification:** the deployed Container App and real Azure resources.

| Slice | Posture |
| --- | --- |
| S-0, S-1 | Local deterministic |
| S-2 | Local deterministic (replay cassette required); optional Azure-assisted run to record the cassette |
| S-3, S-4 | Local deterministic |
| A-0 | Hosted verification |
| S-5, S-6 | Local deterministic |
| S-7 | Deterministic contract tests over the port; a separate Azure-assisted Cosmos integration lane for the compatibility check |
| S-8 | Local deterministic, with one optional Azure-assisted follow-up verification |
| S-9 | Azure-assisted local required for the embedding and vector-viability spike; deterministic fixtures for CI |
| S-10 | Local fixture adapter first; Azure-assisted Cosmos integration second |
| S-11 | Local deterministic |
| S-12 | Local deterministic plus selected Azure-assisted model verification |
| A-1 | Hosted verification |
| S-13 | Local deterministic report from committed fixtures; deliberate Azure-assisted judge runs |
| A-2 | Hosted verification |

**Destructive infrastructure cutovers and hosting or security contract changes are confined to A-0
and A-1.** A-0 owns the hosting and security posture: streaming runtime as the served application,
replica range, built-in authentication, telemetry sink, interim smoke. A-1 owns the only
destructive changes: live container deletion, orphan cleanup, and the complete eight-check suite.

**Capability slices do deploy application behavior.** CI builds, deploys, and smokes on merge, so
S-5 through S-12 change what the hosted application does as they land: three agents, free-text
intake, cancellation, durable records, follow-up, retrieval, governed query, MCP, and the
further-evidence cycle all reach the deployed app. That is intended. The constraint on those slices
is not that the hosted app stays frozen; it is that **the interim smoke installed in S-4 keeps
passing through S-12**. A capability slice that would break the interim smoke either fixes the
smoke in the same PR, within its existing scope, or is not ready to merge.

**Capability slices may also add isolated Azure resources once their local contracts are stable**:
the `investigations` container or its agreed target (S-7), the embedding deployment and categorized
`knowledge` container (S-9), and the `operational-records` container (S-10). Each is isolated and
independently reversible. Nothing is deleted outside A-1, with one narrowly approved exception
named in S-7.

## Coexistence and adapter register

Every temporary artifact is named here with the slice that removes it. Operating rule 6 is
enforced against this table.

| Temporary artifact | Why it exists | Introduced | Deleted |
| --- | --- | --- | --- |
| Old polling, HITL, decision, and job routes | The old runtime must stay runnable until the replacement can complete a grounded turn | Pre-existing | S-4 |
| Legacy contract module `src/opspilot/contracts.py` | The accepted contracts land in `src/opspilot/assessment/contracts.py`; the old runtime keeps its own shapes until it is deleted | Pre-existing, frozen at S-2 | S-4, optionally leaving one narrow re-export |
| Old approval console `src/opspilot/static/console.html` | The new screen is added at `static/investigation.html` on its own route, so the old runtime keeps a working UI until it is deleted | Pre-existing, frozen at S-1 | S-4 |
| One-way projection from the accepted assessment to the old report shape | The old runtime still renders its own report while S-2 holds the accepted shape | S-2 | S-4 |
| Two-axis to binary capability-result shim for old consumers | The old planner and claim admission read `status: ok\|error` | S-2 | S-4 |
| Deprecated `EvalTargets` numeric thresholds | The old scenario and single-agent gates still consume them; removing the configuration before its consumers would break the S-0 baseline | Pre-existing, frozen and marked deprecated at S-0 | S-4, with the gates that read it |
| Three incorrect MCP exposures (`get_incident`, `query_logs`, `search_runbooks`) | Parity must survive the S-2 envelope change continuously; narrowing the exposed set is a separate concern | Pre-existing, carried through S-2 | S-11 |
| Old `safety_validate` wrapper delegating to the four-check gate | The old graph path still calls a safety step after S-3 replaces the policies | S-3 | S-4 |
| Interim hosted smoke (start, authentication, one streamed turn) | Keeps CD green and honest between cutover and the eight-check suite. Every capability slice through S-12 must leave it passing | S-4 | A-1 |
| In-memory Investigation Record backend | Commit-before-terminal must exist before Cosmos work begins | S-2 | Not deleted: S-7 replaces the backend; the port, the in-memory implementation, and their tests remain as the local and CI backend |

## Corpus repair protocol

Corpus defects are repaired by this procedure every time. S-9 applies it to the minimum retrieval
demonstration set; S-12 applies it to the remaining defects. Neither slice restates it.

1. Identify the generator or source fixture that owns the defect.
2. Modify the generator rather than manually editing generated output wherever the generator owns
   the value.
3. Regenerate only the affected assets.
4. Run reference-closure checks over evidence and retrieval references.
5. Run chronology and cause-before-effect checks.
6. Run answer-leakage scans over log lines, deployment notes, and ticket text.
7. Verify that seven authored incidents across five families remain.
8. Regenerate affected answer keys, goldens, retrieval fixtures, and cassettes.
9. Review the diff for accidental evidence inflation: a repair must not make a scenario easier
   than the authored intent.
10. Record which D-006 criterion the repaired scenario supports.

Steps 4 through 7 are automated gates, not manual review. Where a gate does not exist yet, the
slice that first needs it adds it.

---

## Path-level detail for S-0 to S-5 and A-0

These slices restructure the repository, so their paths are named now. Paths marked "proposed"
are the intended destination and are confirmed in the slice's first PR. S-6 onward keeps
provisional placement until this structure exists.

| Concern | Path | Owner slice | Note |
| --- | --- | --- | --- |
| Stream envelope and activity contract | `src/opspilot/stream/contracts.py` (proposed) | S-1 | New module; no existing counterpart |
| Activity projection from instrumentation facts | `src/opspilot/stream/projection.py` (proposed) | S-1 | Derives from `obs/tracing.py` span facts |
| Turn and live-session identity | `src/opspilot/turn/identity.py` (proposed) | S-1 | No turn model exists today (status 10.12) |
| Normalized incident context and intake classification | `src/opspilot/intake/contracts.py` (proposed) | S-1 | Predefined intake only; S-5 adds free text and clarification |
| Telemetry seam | `src/opspilot/obs/tracing.py` | S-1 | Retained; `configure_exporter()` wired at startup, App Insights exporter added in A-0 |
| Streaming endpoint | `src/opspilot/api.py` | S-1 | Added beside the old routes; old routes removed in S-4 |
| One-screen client | `src/opspilot/static/investigation.html` (proposed) | S-1 | New file on its own route; single file, no build step. The old console keeps working until S-4 |
| Old approval console deletion | `src/opspilot/static/console.html` | S-4 | Deleted when the new screen becomes the sole client |
| Evidence reference model, parser, resolver | `src/opspilot/evidence/references.py` (proposed) | S-2 | The single owner; duplicate parsing in `diagnosis/admission.py` and `diagnosis/sufficiency.py` is deleted (status 8.3.4) |
| Evidence admission (observations) | `src/opspilot/evidence/admission.py` (proposed) | S-2 | Evidence Access Layer owned. Not `diagnosis/admission.py`, which admits model-proposed claims, a different thing (status 6.4, 10.4) |
| Capability result envelope | `src/opspilot/tools/contracts.py`, `tools/service.py` | S-2 | Two-axis execution-outcome and completeness replaces `ok`/`error` |
| Capability registry | `src/opspilot/tools/__init__.py` | S-2 | Registry and `READ_ONLY_TOOLS` duplication collapsed to one source |
| Final assessment contracts | `src/opspilot/assessment/contracts.py` (proposed) | S-2 | New module. `src/opspilot/contracts.py` is frozen as legacy-only and deleted in S-4 |
| Investigation Record port and in-memory backend | `src/opspilot/record/` (proposed) | S-2, S-3 | Port and commit-ordering rule in S-2; the completed-turn artifact and the first real commit in S-3; Cosmos backend in S-7 |
| MCP result serialization | `src/opspilot/mcp/server.py` | S-2, S-11 | S-2 carries the new canonical envelope through unchanged; S-11 changes only the exposed capability set |
| Evaluation artifact home | `eval/fixtures/`, `eval/reports/`, and a gitignored `eval/runs/` (proposed) | S-2 | Settled before the first golden record exists |
| Model-access seam and task labels | `src/opspilot/llm/` | S-2, S-5 | Retained; task-label routing and provider narrowing in S-5 |
| Provider narrowing | `src/opspilot/llm/client.py`, `config.py` | S-5 | One Azure OpenAI adapter plus the fake and cassette seams; Ollama and generic OpenAI selection removed |
| Grounding gate | `src/opspilot/grounding/checks.py` (proposed) | S-3 | Absorbs `guardrails/policies.py`; exactly four checks |
| Claim admission | `src/opspilot/diagnosis/admission.py` | S-3 | Folded into the gate or deleted if the assessment and gate make it redundant |
| Deterministic brief projection | `src/opspilot/diagnosis/render.py` | S-2, S-3 | Retained as a projection from the assessment |
| Explicit turn controller | `src/opspilot/turn/controller.py` (proposed) | S-4 | Replaces `graph.py` and `router.py` |
| Old orchestration deletion | `src/opspilot/graph.py`, `nodes/investigation.py`, `router.py`, `checkpoint.py` | S-4 | Deleted; ingest/gather/synthesize logic harvested first |
| Old API deletion | `src/opspilot/api.py` async job routes, `investigations.py`, `cosmos_investigations.py`, `repository.py` | S-4 | Job lifecycle, decision endpoint, outbox, lease and fencing removed |
| Legacy contract module deletion | `src/opspilot/contracts.py` | S-4 | Deleted with the old runtime; a narrow re-export from `assessment/contracts.py` is permitted if imports are widespread |
| Authorization reduction | `src/opspilot/auth.py` | S-4, A-0 | Three-role surface deleted in S-4; minimal caller-identity seam replaced by built-in authentication in A-0 |
| Concurrency reduction | `src/opspilot/api.py`, `config.py` | S-4 | Per-user and role-based admission collapsed to one configured application-level limit (status 8.3.3) |
| Dead configuration removal | `src/opspilot/config.py` | S-0, S-4, S-5, S-13 | Severity routing, numeric confidence, and dispatch keys in S-0; deprecated `EvalTargets` in S-4 with the gates that read it; six bounds in S-5; standalone judge configuration in S-13 |
| Dependency removal | `pyproject.toml`, `uv.lock`, `Dockerfile` | S-4, S-9, A-0 | Graph and checkpoint groups in S-4; the local embedding stack in S-9; `pyjwt` in A-0 |
| Agent modules | `src/opspilot/agents/supervisor.py`, `investigator.py`, `analyst.py` (proposed) | S-5 | Split from the S-4 single-flow controller |
| Free-text normalization and clarification | `src/opspilot/intake/normalize.py` (proposed) | S-5 | Produces the S-1 normalized incident context |
| Fixed-script evidence plan fixture | `eval/fixtures/evidence_plans/` (proposed) | S-5 | Extracted from `diagnosis/planner.py` and `cycle.py` before they are deleted |
| Test deletion | `tests/test_investigations_api.py`, `test_investigations.py`, `test_report_binding.py`, `test_checkpointer.py`, `test_auth.py`, `test_scenario_gate.py`, `test_single_agent_gate.py` | S-4 | Deleted with their subjects, not rewritten |
| Test deletion, second wave | `tests/test_triage.py`, `test_triager.py`, `test_composition.py`, `test_sufficiency.py`, `test_planner_seam.py`, `test_diagnose.py`, `test_llm_planner.py` | S-5 | Deleted with the planner and triage subjects |
| Test replacement | `tests/test_stream_projection.py`, `test_evidence_references.py`, `test_record_commit.py`, `test_grounding_gate.py`, `test_turn_controller.py` (proposed) | S-1, S-2, S-3, S-4 | New deterministic suites |
| Every other existing test module | `tests/` | Various | Disposition is in the test-disposition appendix at the end of this document; no test module is left unassigned |
| Bicep and hosted alignment | `infra/main.bicep`, `scripts/smoke_deployment.py` | S-4, A-0 | Interim smoke in S-4; replicas, authentication, App Insights, lower-cost deployment in A-0 |

---

## Horizon 1: Foundation cleanup, first executable flow, cutover, and hosted alignment

### S-0 Repository reset and truthful baseline

**Status: Completed.**

**Outcome:** a clean `main`-based branch containing the authoritative documentation, truthful
setup instructions, and none of the rejected unpushed dispatch skeleton, exactly as this slice's
demonstrable outcome specified.

**Merge commits:** branch `s0-repository-reset`, cut from `main` at `e567adf`; commits `c8ea681`
(docs, hooks, README, env example), `4400d93` (debris, empty packages, dead severity-tier config,
corpus-path collapse), `3e1f41d` (status.md landing record); merged to `main` via PR #54 as squash
commit `4c8f706`.

**Verification evidence (observed on `main` at `4c8f706`):**

| Check | Result |
| --- | --- |
| Abandoned dispatch WIP is not an ancestor | `git merge-base --is-ancestor 0c3c175 HEAD` exits nonzero |
| Dispatch code is absent | `git grep -n -e DispatchMessage -e relay_pending -e SERVICE_BUS -- src tests infra scripts` empty |
| Dead severity routing is absent | `git grep -n -e PROD_MODELS -e resolve_tier -e SEVERITY_TIER -e ENABLE_OPUS_SEV1 -e CONFIDENCE_THRESHOLD -- src tests` empty |
| Deprecated settings are marked, not orphaned | `EvalTargets`, `MAX_TOOL_CALLS`, `JUDGE_MODEL` remain in `config.py`, each with a deprecation comment, no new consumer |
| Empty package placeholders are gone | `git ls-files src/opspilot/ops src/opspilot/eval` empty |
| Stale root debris is gone | `git ls-files out.txt raw.txt infra/.gitkeep data/.gitkeep` empty |
| Authoritative docs are committed | `git ls-files docs .githooks` lists the accepted set |
| Environment example matches reality | `tests/test_env_example.py` asserts every setting `config.py` reads has a key in `.env.example` |
| Baseline is green | `uv run ruff check`, `uv run mypy src` (0 errors, was 2), `uv run pytest -m "not reranker and not llm"` (382 passed, 5 deselected, 0 failed, was 31 failed/351 passed) all pass |

**Divergences from this slice's original text:**

- The deprecation comments for `EvalTargets`, `MAX_TOOL_CALLS`, and `JUDGE_MODEL` do not name an
  owning deletion slice in-code, as originally specified above. `code-guidelines.md` §12 (plan
  vocabulary must not appear in the repository) postdates this slice's text and is merge-blocking
  per its §13; the comments instead describe the condition or cite the relevant `decisions.md` ID
  (`D-005` for `JUDGE_MODEL`) without a slice number. The same full-file scan retired existing
  `Stage N`/`G-NN` references from `config.py`, the one file this slice already touched.
- "Verified merged remote branches" from the code-and-data-to-delete list was not completed. The
  six branches `status.md` names under "Documentation and Repository Hygiene" remain undeleted.

### S-1 Streaming turn skeleton, turn identity, predefined intake, and one screen

- **Demonstrable outcome:** post a predefined incident to a new streaming endpoint and observe
  identities first, a compact sequence of safe activity entries, and a stream-close marker last in
  one HTTP response. A minimal same-origin screen at its own route renders intake, feed, brief
  region, and one details area. The closing event is a transport demonstration marker proving
  ordering, not a completed investigation outcome; accepted outcomes do not exist until S-3.
- **Entry criteria:** S-0 is green; docs and baseline branch are committed; the abandoned WIP is
  proven absent by the S-0 checkpoint.
- **Existing foundation retained:** FastAPI app, the static single-file no-build-step approach, and
  the tracing seam in `obs/tracing.py`, which already emits once at shared primitives with
  correlation ids and a swappable exporter (status 6.10). The old polling and HITL endpoints and
  their console are temporary compatibility, registered in the coexistence register and deleted in
  S-4; no new feature work goes into them.
- **Code and data to delete:** none in this slice.
- **Code to replace:** none in this slice. The streaming endpoint is added beside the old routes,
  and the new screen is a new file at `static/investigation.html` on its own route rather than a
  rewrite of `console.html`, so the old runtime keeps a working UI until S-4 deletes both together.
- **New implementation:** streaming HTTP response without WebSockets or replay; turn and
  live-session identity, which no component owns today; the normalized incident-context contract
  populated from predefined intake; request-shape interaction classification; the accepted activity
  projection emitted from the same instrumentation facts; live statuses; deterministic stub
  assessment and brief solely to prove transport and rendering; in-process cancellation signal;
  minimal one-screen client.
- **Contract introduced or stabilized:** stream envelope, turn and live-session identity, activity
  projection; normalized incident context and request-shape interaction kind. The normalized
  context is authored to its final accepted shape now and populated only by predefined intake;
  S-5 adds the free-text producer without reshaping it.
- **Telemetry and activity impact:** turn identity and live-session identity on every span; stream
  open, activity emission, and terminal events derived from the same facts. No prompts, provider
  content, hidden reasoning, logs, or secrets reach the projection.
- **Deterministic tests:** activity projection fidelity and sanitization; identities-first and
  close-marker-last ordering; no stream-only facts; turn isolation across concurrent streams.
- **Evaluation increment:** none. Evaluation begins at S-2, when a real assessment exists.
- **Dataset or fixture work:** none. The stub path uses an existing predefined incident.
- **Azure impact:** Local deterministic. No infrastructure change.
- **Decision gates:** the normalized incident-context clarification (status 17.1) is settled here.
- **Explicit non-goals:** no model call, no grounding checks, no accepted completed outcome, no
  persistence, no retrieval, no free-text intake, no clarification, no agent split, and no removal
  of the old routes or the old console.
- **Small PR breakdown:** (1) turn identity, normalized context, and projection contract with
  instrumentation emission; (2) streaming endpoint; (3) the new one-screen client on its own route.
- **Completion evidence:** local executable stream and deterministic ordering and sanitization
  tests.
- **Status updates required after landing:** the activity-streaming row in section 9 moves off
  "No" for implementation; the Engineer Interaction Interface rows in section 10.1 for the single
  screen and activity projection move to Implemented; record the local run command used.

### S-2 Evidence, reference, and assessment contracts with one bounded model call

- **Demonstrable outcome:** one existing incident (`inc-001` or `inc-005`) gathers evidence through
  two or three existing read-only capabilities, performs one structured RCA synthesis call, and
  streams a rendered assessment whose references resolve to admitted evidence. The Investigation
  Record port exists with defined commit semantics, and a lifecycle contract test proves that
  terminal delivery cannot occur until a commit succeeds.
- **This slice deliberately does not conclude an investigation.** The four grounding checks do not
  exist until S-3, and an accepted completed outcome is a consequence of that gate. S-2 renders the
  assessment as a non-terminal demonstration and closes the stream with the S-1 transport marker.
  It commits nothing as a completed turn, and it emits none of complete, partial, or inconclusive.
  Putting the gate here instead would make an already large slice larger; moving first completion
  to S-3 is the cleaner split.
- **Entry criteria:** streaming ordering and activity sanitization tests pass; the S-1 stream
  envelope and normalized context are stable and consumed by the new screen.
- **Existing foundation retained:** LLM client, prompt registry, and cassette seams; `ToolService`,
  its closed registry, and its request validation and error sanitization; the MCP server, which
  keeps delegating to the same service; the existing synthesis prompt as raw material; the
  produced-reference discipline and the content-hash technique, the latter kept as an internal
  integrity device with no publication or version semantics (status 8.3.3).
- **Code and data to delete:** duplicate evidence-reference parsing in `diagnosis/sufficiency.py`
  once the single parser owns it (status 8.3.4).
- **Code to replace:** `tools/contracts.py` binary status, superseded by the two-axis vocabulary;
  the `READ_ONLY_TOOLS` static allowlist, superseded by the registry key set as the single
  capability inventory.
- **Coexistence mechanism, with named paths so this slice is executable:**
  - the accepted contracts land in a new module, `src/opspilot/assessment/contracts.py`;
  - `src/opspilot/contracts.py` is frozen as legacy-only, gains no new members and no new callers,
    and is deleted in S-4, optionally leaving one narrow re-export;
  - a one-way projection maps the accepted assessment to the old report shape for the old runtime;
  - a two-axis to binary shim serves the old planner and claim admission;
  - every adapter is registered in the coexistence register and carries an S-4 deletion comment.
- **MCP impact, which is immediate rather than deferred to S-11:** the MCP server passes the
  canonical capability envelope through unchanged, so changing that envelope changes MCP in this
  slice. Update the MCP serialization to carry the new canonical result unchanged and update
  `test_mcp_parity` to the new vocabulary. Keep the three currently exposed capabilities for now;
  they are registered in the coexistence register for replacement in S-11. Parity therefore holds
  continuously rather than breaking for nine slices.
- **Contract rule:** define the final accepted assessment, grounded-element, candidate-cause,
  recommendation-provenance, limitation, and brief-projection contracts now. Populate only the
  subset needed by the first scenario. Do not introduce a temporary result schema that S-3
  immediately replaces. The completed-outcome vocabulary belongs to S-3 and is not anticipated
  here.
- **New implementation:** the evidence reference model with exactly one parser and one resolver;
  Evidence Access Layer owned admission of normalized observations into an admitted-evidence set
  with first-class limitations, including `succeeded + empty` as a positive observation; the
  two-axis capability result vocabulary; the typed assessment model with qualitative support labels
  and no numeric confidence; a task-labelled `rca_synthesis` call; deterministic brief projection
  from the assessment; the Investigation Record port with an in-memory backend, defining the commit
  operation and its success and failure contract. The port supplies commit semantics; it does not
  own delivery. Ordering is a lifecycle property, asserted here by a contract test against a stub
  delivery step and realized in the running turn by S-3's controller.
- **Contract introduced or stabilized:** evidence reference encoding, its parser, and its resolver;
  two-axis capability result vocabulary and admitted-evidence structure; assessment, candidate
  cause, recommendation, limitation, and brief; the Investigation Record port and its commit
  semantics, with the delivery-ordering rule proven by a lifecycle contract test rather than by a
  delivered completed turn.
- **Telemetry and activity impact:** capability request and admission results, including the
  execution-outcome and completeness axes; model task label, prompt version, and usage totals;
  the port's commit-attempt result. Admission facts appear in the activity projection in their safe
  form.
- **Deterministic tests:** legal execution-outcome and completeness pairings; reference resolution
  through the single parser; `succeeded + empty` admitted as a positive observation; structured
  output validation; rendering fidelity for populated fields; MCP parity against the new envelope;
  commit semantics on the port, including its failure contract; a lifecycle contract test proving
  that a stub delivery step cannot run until a commit succeeds; replay-cassette end-to-end path.
- **Evaluation increment:** the evaluation artifact home is settled and created here, because the
  first artifacts appear here: committed deterministic fixtures under `eval/fixtures/` and
  reference reports under `eval/reports/`, with dated live-run outputs under a gitignored
  `eval/runs/`. No database, telemetry store, or new Azure resource. The first accepted golden
  scenario record is authored into that home. Advisory only, never a merge ratchet.
- **Dataset or fixture work:** record one replay cassette for the synthesis call against the chosen
  incident, with the manifest the drift rules require; author the first golden record from the
  existing answer key. No corpus change.
- **Azure impact:** Local deterministic; the cassette is required so CI never calls a model.
  Optional Azure-assisted local run against the primary deployment to record the cassette.
- **Decision gates:** the reference-encoding clarification (status 17.2) and the evaluation
  artifact storage clarification (status 17.4) are settled here, and both are recorded in the
  owning authoritative document per operating rule 10. Task labels are introduced; routing to a
  second deployment is S-5, using the deployment A-0 adds.
- **Explicit non-goals:** no grounding checks; no accepted completed outcome; no committed
  completed turn; no terminal delivery of a domain result; no multi-agent split; no Cosmos
  persistence; no retrieval; no free-text intake; no change to the MCP exposed capability set.
- **Small PR breakdown:** (1) evidence reference model, parser, and resolver, and the evaluation
  artifact home; (2) two-axis result vocabulary, Evidence Access Layer admission, the old-path
  shim, and the MCP envelope and parity update; (3) accepted assessment contracts in their new
  module and the old-path projection adapter; (4) Investigation Record port, in-memory backend,
  commit semantics, and the lifecycle delivery-ordering contract test; (5) synthesis task,
  deterministic brief projection, and streaming integration.
- **Completion evidence:** one reproducible incident-to-assessment run in a single streamed
  request, the commit-semantics and lifecycle-ordering contract tests green, MCP parity green
  against the new envelope, and the first golden record committed in its settled location.
- **Status updates required after landing:** the evidence-admission rows in section 10.4 and the
  assessment rows in section 10.5 move to Implemented; the binary-status row in section 8.3.1 moves
  to Replaced; record the cassette identity, the incident used, the evaluation artifact location,
  and the first golden record. The commit-before-terminal row in section 10.11 stays open until
  S-3.

### S-3 Four grounding checks, correction allowance, outcomes, and the first completed turn

- **Demonstrable outcome:** the first accepted completed turn. Every delivered assessment passes
  exactly four deterministic checks, is assigned one of complete, partial, or inconclusive, is
  committed, and only then produces the terminal event. A deliberately malformed synthesis is
  corrected once and, if still invalid, produces failed execution with no completed artifact, no
  commit, and no delivered brief.
- **Terminal ordering realized here in full:** synthesis, four checks, possible single correction,
  outcome assignment, commit, terminal delivery. No later slice may reorder it.
- **Entry criteria:** the accepted assessment contract exists, one real structured synthesis
  completes end to end under replay, and the Investigation Record port's commit semantics and
  lifecycle delivery-ordering contract test are green.
- **Existing foundation retained:** S-2 contracts and the Investigation Record port, which gains
  its first real writer and its first real artifact here; the produced-reference discipline, a real
  ancestor of reference resolution.
- **Code and data to delete:** the two-policy guardrail surface once the four checks subsume it,
  including its tests; `diagnosis/admission.py` claim admission if the accepted assessment and the
  gate make it redundant, which is the expected outcome (status 8.3.4 assigns citation grounding to
  one gate).
- **Code to replace:** `guardrails/policies.py` citation grounding, superseded by the four-check
  gate; the `safety_validate` naming and any two-policy terminology that could be mistaken for the
  final gate. The read-only allowlist behavior moves to the capability registry rather than being
  deleted.
- **Coexistence mechanism:** the old graph path keeps a thin `safety_validate` wrapper that
  delegates to the new gate and discards the accepted result shape. It is registered in the
  coexistence register and deleted in S-4 with the graph.
- **New implementation:**
  1. citation and reference resolution with permitted role and type pairing;
  2. required operational support for grounded elements marked established;
  3. recommendation-provenance presence;
  4. disclosure of recorded limitations.
  Add the one shared correction allowance, deterministic outcome assignment, the completed-turn
  artifact the port stores, the commit itself, terminal delivery after the commit, and
  failed-execution behavior outside the three completed outcomes. Do not add semantic entailment,
  temporal coherence, or any hidden fifth check.
- **Contract introduced or stabilized:** grounding result, completed-outcome vocabulary, the
  completed-turn artifact, and terminal ordering.
- **Telemetry and activity impact:** grounding result per check, correction-allowance spend, the
  outcome assignment, the commit result, and the terminal shape decision, all as span facts that
  the projection renders safely.
- **Deterministic tests:** each check independently; the fixed four-check set with no fifth;
  single-spend correction allowance; rendering remains a projection; the full terminal ordering
  asserted end to end; persistent failure delivers nothing, commits nothing, and is not one of the
  three completed outcomes; a commit failure after a passing gate also delivers nothing.
- **Evaluation increment:** the deterministic conformance aggregation entry point, covering
  grounding results and completed outcomes over the S-2 golden record, written into the evaluation
  artifact home settled in S-2. Advisory only.
- **Dataset or fixture work:** a malformed-synthesis fixture for the correction demonstration.
- **Azure impact:** Local deterministic. No infrastructure change.
- **Decision gates:** none.
- **Explicit non-goals:** no fifth check, no semantic entailment, no Cosmos persistence, no agent
  split, no cancellation semantics.
- **Small PR breakdown:** (1) grounding result contracts; (2) the four checks and correction
  routing, with the old-path wrapper; (3) outcome assignment, the completed-turn artifact, commit,
  and terminal delivery; (4) failed-execution behavior and conformance aggregation.
- **Completion evidence:** one incident run end to end producing a committed completed turn
  delivered after its commit, one visible correction demonstration, one persistent-failure run that
  delivers and persists nothing, and a conformance aggregation run over the first golden record.
- **Status updates required after landing:** the grounding rows in section 10.6 and the
  commit-before-terminal row in section 10.11 move to Implemented; the one-check safety gate row in
  section 8.3.1 moves to Replaced; the guardrails row in section 7 moves to Replaced.

### S-4 Streaming-runtime cutover and obsolete-system deletion

- **Demonstrable outcome:** the streaming explicit turn path is the only investigation runtime. The
  application remains executable and produces the grounded, committed S-3 completed turn using the
  contracts introduced in S-2, while the async job, approval, polling, checkpoint, graph-runtime,
  and graph-dependent evaluation surfaces are gone.
- **Why this slice exists separately:** deletion is a coherent product outcome. It prevents the
  repository from carrying two competing architectures while the three-agent split is added.
- **Entry criteria:** the replacement streaming path completes a grounded, committed turn without
  relying on the old API, proven by an S-3 run that touches no old route.
- **Existing foundation retained:** the S-1 through S-3 replacement path; ingest normalization,
  evidence gathering, and synthesis logic lifted out of the graph nodes before those modules are
  deleted.
- **Code and data to delete:** LangGraph graph, nodes, and routers; `hitl_gate`, `apply_edit`, and
  the `postmortem` dead path; `checkpoint.py` and the checkpointer dependencies; `checkpoints` and
  `investigation-index` code paths; the 202-and-poll investigation API; the decision endpoint,
  `CommittedDecision`, and decision idempotency; approval, edit, and reject UI; the job-status
  vocabulary; the outbox, lease, fencing, and multi-replica transition machinery; publication
  identity and the approval-bound report hash as semantics, keeping only the internal content hash;
  the three-role authorization surface and `ReviewerPrincipal`; the legacy
  `src/opspilot/contracts.py` module, optionally leaving one narrow re-export from
  `assessment/contracts.py` if imports are widespread; the old approval console
  `static/console.html`, once the S-1 screen becomes the sole client; the deprecated `EvalTargets`
  configuration, deleted here together with the gates that consume it; the old-path adapters
  registered in the coexistence register; old hosted-smoke assertions; and the tests that die with
  these subjects, including `test_investigations_api.py`, `test_investigations.py`,
  `test_report_binding.py`, `test_checkpointer.py`, `test_auth.py`, and the approval cases inside
  `test_api.py` and `test_guardrails.py`. Dependencies removed from `pyproject.toml`, `uv.lock`,
  and the `Dockerfile` install groups: `langgraph`, `langchain-core`,
  `langgraph-checkpoint-sqlite`, `langchain-azure-cosmosdb`.
- **Graph-dependent evaluation removed or parked in the same slice:** `eval/scenario_eval.py`,
  `eval/record_single_agent.py`, `tests/test_scenario_gate.py`, `tests/test_single_agent_gate.py`,
  the committed numeric scorecards, the stub `eval/harness.py` with `tests/test_scaffold.py`, and
  the RCAEval probe (`eval/wild.py`, `record_wild.py`, its baseline and cassette,
  `tests/fixtures/wild_ob/`, `tests/test_wild.py`). Parked material moves under a clearly archived
  path excluded from CI; S-13 makes the final keep-or-delete call. Leaving these active would
  leave the repository broken or misleading the moment the graph is deleted.
- **Code to replace:** `graph.py` and `router.py`, superseded by a small explicit turn controller;
  the default client route, which now serves `static/investigation.html` as the only client;
  per-user and role-based concurrency admission, superseded by one configured application-level
  concurrency limit; `scripts/smoke_deployment.py` approval assertions, superseded by the interim
  smoke.
- **New implementation:** a small explicit turn controller invoking the objective, evidence,
  synthesis, gate, and commit steps; no checkpoints, reattachment, background job, or workflow
  framework. The minimal accepted evaluation spine becomes the only active evaluation: the S-2
  golden record, the S-3 conformance aggregation, and one recorded categorical outcome, advisory
  and never a numeric merge ratchet. An interim hosted smoke covering start, authentication, and
  one streamed turn, so that CD stays green and honest until A-1 installs the eight accepted
  checks.
- **Contract introduced or stabilized:** turn-controller and terminal-delivery ordering.
- **Telemetry and activity impact:** the turn controller emits stage transitions through the same
  seam the graph node wrapper used, so no instrumentation fact is lost in the swap.
- **Deterministic tests:** one complete streamed turn; one gate failure; old route absence; no
  runnable approval or checkpoint behavior; the suite green after obsolete tests are removed rather
  than rewritten to validate deleted behavior.
- **Evaluation increment:** the old numeric ratchets stop gating CI and the accepted spine replaces
  them as the only active evaluation.
- **Dataset or fixture work:** none.
- **Azure impact:** Local deterministic for the runtime change. The deployed app keeps running; the
  hosted contract narrows to the interim smoke. No Bicep resource change here; A-0 owns the hosted
  alignment that immediately follows.
- **Decision gates:** none.
- **Explicit non-goals:** no three-agent split, no Cosmos persistence, no retrieval, no live
  container deletion, which waits for A-1 after data safety is verified.
- **Small PR breakdown:** (1) switch the default route and client to the streaming screen, delete
  the old console, and delete the old-path adapters and the legacy contracts module; (2) remove the
  async and HITL API, role machinery, and concurrency wrappers; (3) remove graph and checkpointer
  modules and their dependencies from `pyproject.toml`, `uv.lock`, and the `Dockerfile`; (4) remove
  or park graph-dependent evaluation, its CI gates, and `EvalTargets`; (5) remove obsolete tests and
  smoke clauses and install the interim smoke.
- **Completion evidence:** the checkpoint below passes, and the only runnable investigation journey
  is the accepted streaming one.
- **Status updates required after landing:** the orchestration, transport, auth, console, and
  checkpointer rows in sections 7 and 8 move to Deleted or Replaced; the dependency rows in section
  14 move to Removed; the numeric-ratchet row in section 8.3.1 moves to Replaced; record the
  marker-lane result after the obsolete suites are deleted.

#### Checkpoint after S-4

This is the architectural cutover. Nothing later may depend on the deleted runtime. All greps are
scoped to runtime paths and use exact symbols.

| Check | Proof |
| --- | --- |
| No graph runtime dependency | `uv tree` shows no `langgraph`, `langchain-core`, `langgraph-sdk`, `langsmith`; `uv run python -c "import langgraph"` fails |
| No checkpointer code or dependency | `git grep -n -e CHECKPOINTER -e Checkpointer -e "langgraph.checkpoint" -e msgpack -- src tests infra` is empty; `uv tree` shows no `langgraph-checkpoint-sqlite`, `sqlite-vec` |
| No HITL or approval surface | `git grep -n -e hitl_gate -e apply_edit -e CommittedDecision -e "/decision" -- src tests scripts` is empty |
| No polling job API | `git grep -n -e awaiting_approval -e _dispatch_or_run -e _advance -e DispatchEntry -- src tests scripts` is empty |
| No obsolete job statuses | `git grep -n -e "\"queued\"" -e "\"escalated\"" -e "\"degraded\"" -- src` is empty |
| No approval roles | `git grep -n -e ReviewerPrincipal -e Approver -e require_role -e idtyp -- src tests` is empty |
| Concurrency is one limit | `git grep -n -e per_user -e role_limit -- src` is empty and exactly one configured concurrency setting remains |
| Legacy contracts and console are gone | `git ls-files src/opspilot/contracts.py src/opspilot/static/console.html` is empty, or `contracts.py` contains only a re-export |
| Deprecated eval configuration is gone | `git grep -n -e EvalTargets -- src tests` is empty |
| No graph-dependent evaluation is active | `git ls-files eval tests` shows no `scenario_eval`, `record_single_agent`, `test_scenario_gate`, `test_single_agent_gate`, `wild`, or `harness` outside an archived, CI-excluded path |
| The accepted spine is the only evaluation | `uv run python -m eval.conformance` runs and reports categorical results with no numeric threshold |
| Tests for deleted behavior are gone | `git ls-files tests` shows none of the modules named above; `uv run pytest -m "not reranker and not llm"` is green |

### A-0 Minimal hosted alignment

- **Demonstrable outcome:** the deployed environment runs the streaming runtime at zero-to-one
  replicas behind Container Apps built-in authentication, with Application Insights receiving
  telemetry, and a reviewer can watch one grounded streamed turn complete against the hosted app.
- **Entry criteria:** the S-4 checkpoint is clean and the interim smoke passes locally against a
  container build.
- **Existing foundation retained:** the Bicep template and OIDC workflow, a sound keyless skeleton;
  the tracing seam, which needs an exporter rather than a rewrite; ACR, Log Analytics, the Cosmos
  account, and the Container App itself.
- **Code and data to delete:** the deprecated `/health` alias, once the Bicep probes and the
  documentation use the accepted health routes; the hand-rolled JWT validation and `pyjwt[crypto]`,
  once built-in authentication is verified in front of the app.
- **Code to replace:** the caller-identity seam left by S-4, superseded by trusting the platform
  identity header, with a documented local development bypass.
- **New implementation:** replica range set to zero-to-one; Container Apps built-in authentication
  with one app registration and no role machinery; an Application Insights component wired to the
  telemetry seam through `configure_exporter()` at startup; the lower-cost chat deployment added so
  that S-5 has a routing target; the interim smoke run as the post-deploy gate.
- **Smoke authentication, specified rather than discovered:** enabling built-in authentication
  makes the hosted smoke a real authenticated caller, and the repository has already been bitten
  once by an identity step that existed only in a failure string. Settle and document all five
  points in this slice:
  1. **caller identity:** the existing OIDC-authenticated CI principal that already performs the
     deployment, with no second identity created and no application roles reintroduced;
  2. **token acquisition:** that principal requests a token for the application registration
     through the same federated credential the deployment uses;
  3. **audience:** the application registration's own identifier, recorded in repository variables
     alongside the existing deployment variables;
  4. **local developer verification:** a documented interactive sign-in against the same
     registration, plus the documented local bypass for running the app outside Azure;
  5. **proof:** one hosted check asserting that the application receives a caller identity from the
     platform and authorizes on presence alone, with no role claim consulted anywhere.
  Any grant the CI principal needs is recorded in the deployment documentation, not left implicit.
- **Contract introduced or stabilized:** none. This slice makes the hosted environment match
  contracts already stabilized.
- **Telemetry and activity impact:** the existing spans reach a real sink for the first time. No
  new emission points; correlation must survive the exporter.
- **Deterministic tests:** unchanged. Hosted behavior is not re-asserted in deterministic tests.
- **Evaluation increment:** none.
- **Dataset or fixture work:** none.
- **Azure impact:** Hosted verification. This slice changes the deployed contract; A-1 is the only
  other slice that does.
- **Decision gates:** none.
- **Explicit non-goals:** no Cosmos container change, no embedding deployment, no eight-check
  smoke, no live container deletion, no Key Vault, no VNet.
- **Small PR breakdown:** (1) replicas, probes, and the `/health` alias removal; (2) built-in
  authentication, the documented smoke-caller identity and audience, and removal of the
  hand-rolled JWT path; (3) Application Insights and exporter wiring; (4) lower-cost chat
  deployment.
- **Completion evidence:** one hosted streamed turn observed end to end, with its spans visible in
  Application Insights and the interim smoke green in CD.
- **Status updates required after landing:** section 12 is rewritten from a fresh live inspection
  rather than from the template; the replica, authentication, and Application Insights rows in
  section 10.15 move to Implemented; record the `az` queries actually run.

#### Checkpoint after A-0

| Check | Proof |
| --- | --- |
| Replicas are zero to one | `az containerapp show -g rg-opspilot -n opspilot-api --query "properties.template.scale"` shows min 0, max 1 |
| Built-in authentication is enabled | `az containerapp auth show -g rg-opspilot -n opspilot-api` reports an enabled platform with one registration |
| Hand-rolled authorization is gone | `git grep -n -e pyjwt -e jwks -e ReviewerPrincipal -- src tests` is empty; `uv tree` shows no `pyjwt` |
| Application Insights is connected | `az monitor app-insights component show -g rg-opspilot --app <name>` resolves and one turn's spans are queryable |
| The lower-cost deployment exists | `az cognitiveservices account deployment list -g rg-opspilot -n <account> --query "[].name"` lists the primary and lower-cost chat deployments |
| The deprecated health alias is gone | `git grep -n -e "\"/health\"" -- src infra scripts` is empty |
| The smoke authenticates as a named identity | The workflow acquires its token for the recorded audience through the existing OIDC principal, and the interim smoke passes in CD without a manual step |
| No role taxonomy returned | `git grep -n -e roles -e app_role -e scp -- src` shows no authorization decision based on a role claim |

---

## Horizon 2: Capability-by-capability agentic growth

### S-5 Three agents, six bounds, free-text intake, and the fixed-script fixture

- **Demonstrable outcome:** Supervisor, Evidence Investigator, and RCA Analyst visibly collaborate
  inside the six logical boundaries. Two incidents take different evidence paths, a free-text
  submission is normalized and, where genuinely ambiguous, produces exactly one clarification, and
  activity entries show agent, capability, transport, and continuation or stop facts without hidden
  reasoning.
- **Course concepts:** multi-agent collaboration; planning and tools within guardrails.
- **Entry criteria:** the S-4 checkpoint is clean, so no old runtime remains; A-0 has provided the
  lower-cost deployment that intake normalization routes to.
- **Existing foundation retained:** the S-4 explicit turn controller and the S-2 contracts,
  including the Investigation Record port, which gives the sixth logical boundary a real
  implementation before this slice claims all six; the model-access seam, which gains task labels
  rather than being rebuilt; `LLMPlanner.plan`'s observation-driven selection, batching, and
  dedup-against-answered, harvested into the Investigator; `diagnosis/observe.py` summarizers and
  `diagnosis/render.py` projection.
- **Code and data to delete:** `triage.py`, `composition.py`, `diagnosis/planner.py`,
  `diagnosis/llm_planner.py`, `diagnosis/sufficiency.py`, `diagnosis/cycle.py`, the twin
  `KNOWN_IMPLEMENTATIONS` definitions, the old intent taxonomy and known-issue fast path, and their
  tests. The deterministic planner and cycle are deleted only after their behavior is captured as
  the fixed-script fixture below.
- **Model-seam narrowing, which has no other owner:** the runtime keeps one narrow Azure OpenAI
  adapter, the deterministic `FakeChatModel`, and cassette record and replay. Delete the Ollama
  branch, generic OpenAI-compatible provider selection, and the provider-choice configuration for
  providers the accepted design does not use. Delete `LLM_SEED` unless an accepted test or
  deployment need proves its value, in which case record that reason. Remove or replace the live
  Ollama tests, which are the tests that made the full suite take over nine hours (status 5), and
  update `test_llm_client.py` and `test_llm_e2e.py` accordingly. The seam stays replaceable in
  tests; the runtime stops being a multi-provider product.
- **Fixed-script capture precedes deletion:** `diagnosis/planner.py` and `diagnosis/cycle.py` are
  the accepted fixed-script baseline's behavioral source (status 6.11: same tools, predetermined
  order, currently living as a runtime fallback). Extract the first fixed-script evidence-plan
  fixture from them, commit it, and prove it reproduces the recorded plan before the modules are
  removed. S-13 expands the fixture set and runs the comparison.
- **Code to replace:** the deterministic and LLM dual implementation, superseded by the three-agent
  split; severity-scaled sufficiency, superseded by Supervisor authorization against computable
  conditions.
- **New implementation:** deterministic Supervisor control separated from Supervisor model
  judgments; Evidence Investigator proposal with question, action, and reason, plus optional
  informing-knowledge references; Supervisor authorization using the accepted computable
  conditions; independent authorized evidence actions executed in parallel within one authorized
  cycle; RCA Analyst as sole completed-turn semantic synthesis authority; free-text intake
  normalization producing the S-1 normalized context; at most one clarification; task labels for
  intake normalization, objective interpretation, source selection, synthesis, correction, and
  follow-up answering, with intake normalization routed to the lower-cost deployment and the rest
  to the primary.
- **Clarification mechanism:** prefer resubmission of the original input with the clarifying answer
  over a signed short-lived normalization token. A token is introduced only if resubmission
  demonstrably fails the requirement, and then only with an explicit signing, expiry, and payload
  contract (status 17.3).
- **Bounds:** exactly turn deadline, capability-call cap, model-call cap, per-operation retry cap,
  shared correction allowance, and further-evidence-cycle flag. The retained `MAX_TOOL_CALLS`
  setting is renamed to the capability-call cap and enforced here. Token use is measured; there is
  no token ledger.
- **Contract introduced or stabilized:** agent proposal and authorization; free-text normalization
  and the single-clarification flow.
- **Telemetry and activity impact:** agent identity on every operation; proposal, authorization,
  and refusal facts; bound-stop reason; task label on every model call. Clarification appears as an
  interaction fact, not as model content.
- **Deterministic tests:** authorization is required for continuation; model output alone cannot
  continue; the deadline reaches every operation; all six bounds are enforced; parallel independent
  actions inside one authorized cycle; turn isolation; at most one clarification per turn; no
  fourth agent and no seventh boundary.
- **Evaluation increment:** the fixed-script evidence-plan fixture is committed and proven to
  reproduce, ready for the S-13 comparison.
- **Dataset or fixture work:** cassettes for the two incidents that take different evidence paths;
  a free-text intake fixture and an ambiguous fixture that triggers the single clarification.
- **Azure impact:** Local deterministic. Routing targets the deployment A-0 already created; no new
  infrastructure.
- **Decision gates:** the clarification-token clarification (status 17.3) is settled here.
- **Explicit non-goals:** no further-evidence cycle, which is S-12; no retrieval; no Cosmos
  persistence.
- **Small PR breakdown:** (1) extract and commit the fixed-script fixture; (2) agent interfaces and
  the Supervisor control and judgment seam; (3) Investigator proposal and authorization loop with
  parallel actions; (4) Analyst synthesis and task-label routing; (5) provider narrowing and the
  live-model test removal; (6) free-text normalization and the single clarification; (7) bounds and
  their tests, and deletion of the superseded modules.
- **Completion evidence:** role-attributed feed, distinct execution paths for two incidents, one
  free-text submission normalized, and one clarification exchange.
- **Status updates required after landing:** sections 10.2, 10.3, and 10.5 move to Implemented for
  the roles and the proposal contract; the intake rows in section 10.1 move to Implemented; the
  six-boundary row in section 9 may now move to Implemented because the Investigation Record
  boundary exists; the planner and triage rows in section 7 move to Deleted; the provider rows in
  section 14 record the narrowed dependency set and the removal of the live-model lane.

### S-6 Cancellation, degradation, and honest partial or inconclusive results

- **Demonstrable outcome:** early cancellation before evidence completes yields a committed
  inconclusive completed turn with no assessment and no brief; later cancellation with admitted
  evidence may produce a committed partial result and brief; client disconnect discards active
  state and commits nothing; source failure becomes a recorded limitation rather than a fabricated
  observation.
- **Entry criteria:** S-5 agent boundaries and the six bounds are enforced and tested; the turn
  controller has identifiable safe boundaries to cancel at.
- **Existing foundation retained:** the S-1 in-process cancellation signal; the S-3 outcome
  vocabulary, which already carries inconclusive; the S-2 commit ordering, which cancellation
  outcomes reuse rather than bypass.
- **Code and data to delete:** none.
- **Code to replace:** none.
- **New implementation:** safe-boundary cancellation in the explicit controller; the materiality
  decision that separates partial from inconclusive; stop and inconclusive-reason vocabularies; no
  unsupported assertions anywhere in a degraded result.
- **Cancellation persistence matrix, stated exactly so the commit rule is unambiguous:**

  | Situation | Outcome | Assessment and brief | Committed |
  | --- | --- | --- | --- |
  | Cancelled before any evidence is admitted | Inconclusive completed turn | None | Yes |
  | Cancelled after evidence is admitted, material enough to support a result | Partial completed turn | Yes | Yes |
  | Cancelled after evidence is admitted, not material enough | Inconclusive completed turn | None | Yes |
  | Client disconnect | Not a completed turn | None | No; active state is discarded |
  | Persistent grounding failure | Failed execution, outside the three completed outcomes | None | No |

  "Nothing is persisted for non-completed execution" therefore excludes both cancellation rows that
  produce a completed outcome. Cancellation is a completed turn; disconnect is not.
- **Contract introduced or stabilized:** cancellation, degradation, and cancelled-turn persistence
  rules.
- **Telemetry and activity impact:** cancellation-received and cancellation-effective facts at the
  safe boundary, the materiality decision, and the stop reason.
- **Deterministic tests:** every row of the matrix above; disconnect discards and commits nothing;
  no fabricated evidence in a degraded result; the exact outcome vocabulary.
- **Evaluation increment:** cancellation outcomes are added to the conformance aggregation so that
  a wrong outcome class is caught by evaluation as well as by tests.
- **Dataset or fixture work:** a source-failure fixture for the degradation path.
- **Azure impact:** Local deterministic. No infrastructure change.
- **Decision gates:** none.
- **Explicit non-goals:** no persistence of active-turn state, no reattachment, no resumption of a
  cancelled turn.
- **Small PR breakdown:** (1) cancellation boundaries and signal handling; (2) materiality,
  degradation, and reason contracts; (3) the persistence matrix and its tests.
- **Completion evidence:** early-cancel and late-cancel demonstrations in the same one-screen UI,
  each with the committed record inspected afterwards.
- **Status updates required after landing:** the cancellation rows in section 10.7 move to
  Implemented; record which cancellation paths have deterministic tests.

### S-7 Durable completed-turn record and restart-safe reads

- **Demonstrable outcome:** completed turns are persisted in Cosmos and, after a container restart,
  a completed turn is read back and every citation still resolves.
- **Entry criteria:** S-6 outcome and cancellation semantics are stable, so the set of turns that
  must be committed is fixed; the Cosmos compatibility check below has been performed and its
  migration decision recorded before implementation starts.
- **Cosmos compatibility check, performed first and not assumed:** an `investigations` container
  already exists and stores the job-record shape. Determine whether the accepted artifact can reuse
  it in place, which depends on the existing partition key and indexing policy, neither of which
  this plan has verified. Record one of three outcomes before writing code, and let the outcome
  decide whether this slice is additive:
  1. **Compatible: reuse in place.** The partition key and indexing policy accept the accepted
     artifact. No new container, no migration, nothing deleted. The container holds mixed shapes
     until A-1 clears the old documents.
  2. **Incompatible, old data worth keeping: add a second container.** Create a distinct container
     alongside the existing one, write only accepted artifacts to it, and record the old container
     for A-1 deletion. Additive, and the only outcome for which "additive" is the accurate word.
  3. **Incompatible, old data worth nothing: replace it here, with narrow approval.** Every stored
     record belongs to the deleted job lifecycle and has no retention value, so building a
     migration mechanism to preserve dead data is waste. Delete and recreate the container with the
     accepted partition key and indexing policy in its own separately approved PR. This is the
     preferred outcome if compatibility fails, and it is the one named exception to the rule that
     nothing is deleted outside A-1. The approval is explicit, the PR does nothing else, and the
     deletion is recorded in `status.md` with the command run.
  Do not call the slice additive before the check answers, and do not invent a migration mechanism
  for data that outcome 3 says is worthless.
- **Existing foundation retained:** the Investigation Record port and its commit semantics from
  S-2, and the completed-turn artifact and terminal ordering from S-3, none of which change here;
  the ETag compare-and-swap technique and the keyless managed identity posture from the old
  repository; `azure-cosmos`, regrouped away from the deleted `checkpoint` dependency group.
- **Code and data to delete:** whatever remains of `cosmos_investigations.py` after the S-4
  removals, including any surviving lease, fencing, or multi-replica retry paths beyond the minimal
  retry a single-writer repository needs and proves with tests.
- **Code to replace:** the in-memory backend as the deployed backend, superseded by the Cosmos
  backend behind the same port. The in-memory implementation remains as the local and CI backend.
- **New implementation:** the Cosmos completed-turn repository with the Supervisor as sole writer;
  restart-safe read and citation resolution; the container or migration target chosen by the
  compatibility check; the minimal retry the single-writer path requires.
- **Contract introduced or stabilized:** Investigation Record storage layout and restart-safe
  resolution. The port and its commit semantics were stabilized at S-2, and the completed-turn
  artifact and terminal ordering at S-3; none of them is reopened here.
- **Telemetry and activity impact:** persistence result, backend identity, and retry facts on the
  commit span.
- **Deterministic tests:** one port contract suite run against the in-memory backend and against a
  fake or stub implementing the Cosmos port, so both satisfy one contract offline: commit ordering,
  persistence-failure behavior, nothing persisted for a disconnect, and resolver semantics after a
  simulated restart. Nothing in this lane touches a real Cosmos account.
- **Azure-assisted integration, deliberately not called deterministic:** a separate, separately
  named lane that verifies actual partition-key and indexing compatibility, writes and reads a real
  artifact, restarts the application process, and resolves citations against the live account. It
  is environment-dependent, is never a CI gate, and records the command and the resource used. No
  local Cosmos emulator was available at inspection time (status 16), so this lane runs against a
  real account or not at all.
- **Evaluation increment:** none. Persistence is proven by tests and by the hosted check in A-1.
- **Dataset or fixture work:** none.
- **Azure impact:** Azure-assisted local required for the compatibility check and integration
  tests. Whether this slice is additive is decided by that check: outcomes 1 and 2 add or reuse
  without deleting anything; outcome 3 performs the one narrowly approved destructive replacement
  this plan permits outside A-1, in its own PR. The interim smoke must still pass afterwards.
- **Decision gates:** none pending, but the compatibility outcome is recorded as a decision note in
  the owning document per operating rule 10, including which of the three branches was taken and
  why.
- **Explicit non-goals:** no follow-up, handoff, redirect, or supplied context, which are S-8; no
  checkpointing, reattachment, recovery scanning, or activity persistence; no unapproved container
  deletion.
- **Small PR breakdown:** (1) compatibility check and recorded outcome; (2) if outcome 3, the
  separately approved container replacement, doing nothing else; (3) Cosmos backend behind the
  existing port, with the shared contract suite run against the stub; (4) restart-safe read and
  citation resolution, with the Azure-assisted integration lane.
- **Completion evidence:** the port contract suite green against both offline backends, and one
  recorded Azure-assisted run in which a completed turn is written to Cosmos, the app restarted,
  and the same turn read back with resolving citations.
- **Status updates required after landing:** the persistence rows in section 10.11 move to
  Implemented; section 12 records the container change only if Azure was actually rechecked, and
  records which compatibility outcome was taken along with any deletion command run.

### S-8 Retained-state interactions: follow-up, handoff, redirect, and supplied context

- **Demonstrable outcome:** a follow-up question is answered from retained state without new
  evidence; a handoff summary is produced with no model call; a redirect and a supplied-context
  submission each seed a new investigative turn.
- **Entry criteria:** S-7 durable records exist and read back after restart, so retained state is
  real rather than in-process.
- **Existing foundation retained:** the S-1 request-shape interaction classification; the S-7
  record and its resolver; the S-2 brief projection, which handoff reuses as a projection rather
  than re-rendering.
- **Code and data to delete:** none.
- **Code to replace:** none.
- **New implementation:** the follow-up task on the primary deployment through the Supervisor; the
  retained-state validation rules; deterministic handoff projection; redirect and supplied-context
  seeding; the read endpoint.
- **Constraints stated explicitly, because the old intent taxonomy could otherwise reappear as a
  routing or grounding system:**
  - interaction kind is determined by request shape or an explicit UI action, never by a model
    classifier;
  - follow-up answering is a Supervisor primary-model task;
  - only retained assessment, evidence references, knowledge references, limitations, and
    recommendations may be used;
  - no new evidence may be gathered;
  - no new candidate cause or conclusion may be introduced;
  - no new retrieved-guidance recommendation may be introduced;
  - an unresolved question yields a recommendation to start a new investigative turn;
  - a follow-up is not a completed turn and does not run the four-check gate;
  - handoff performs no model call, no new synthesis, no ranking, no new evidence, and no new
    recommendation.
- **Contract introduced or stabilized:** follow-up, handoff, redirect, and supplied-context
  semantics.
- **Telemetry and activity impact:** interaction kind, retained-state validation result, and the
  fact that handoff made no model call.
- **Deterministic tests:** each constraint above as its own test; a follow-up that would require
  new evidence is refused with the new-turn recommendation; handoff output is byte-identical for
  identical retained state; redirect and supplied context create new turns rather than mutating the
  prior one.
- **Evaluation increment:** follow-up and handoff conformance added to the aggregation.
- **Dataset or fixture work:** retained-state fixtures covering answerable and unanswerable
  follow-ups; a recorded cassette for the follow-up model response, carrying prompt-version and
  manifest metadata like every other cassette, so that CI never calls a model for follow-up. The
  `FakeChatModel` covers the refusal path where no model output is needed.
- **Azure impact:** Local deterministic against the in-memory backend and the follow-up cassette,
  with one optional Azure-assisted run against the primary deployment and the Cosmos backend to
  verify the live follow-up path.
- **Decision gates:** none.
- **Explicit non-goals:** no new evidence path, no model call in handoff, no follow-up gate, no
  cross-turn memory store.
- **Small PR breakdown:** (1) follow-up task and retained-state validation; (2) deterministic
  handoff and the read endpoint; (3) redirect and supplied-context seeding.
- **Completion evidence:** complete a turn, restart, ask a follow-up answered under replay, be
  refused on an out-of-scope follow-up, and request a handoff that makes no model call. The
  follow-up cassette is committed and its manifest validates.
- **Status updates required after landing:** the follow-up and handoff rows in sections 9 and 10.7
  move to Implemented.

### S-9 Retrieval, deterministic reranking, and demonstrated retrieval influence

- **Demonstrable outcome:** categorized knowledge materially influences a live investigation using
  semantic retrieval, lexical retrieval, reciprocal-rank fusion, deterministic identifier and
  metadata promotion, then passage-budget truncation. The feed shows used knowledge and the next
  proposal's informing references.
- **Course concepts:** RAG and hybrid retrieval.
- **Entry criteria:** S-5 authorization is stable, and the minimum demonstration-data repair set is
  agreed before implementation starts. The knowledge metadata shape is **not** an entry criterion,
  because no earlier slice owns it; it is this slice's first decision, below.
- **First decision, taken inside this slice:** establish and record the minimal knowledge metadata
  contract that retrieval and admission actually require, then begin the vector and retrieval
  implementation. Today `kind` maps cleanly onto the three logical collections but no category or
  date metadata field exists (status 11), and no authoritative document fixes one. Keep the
  contract minimal: the identifier, the category the container filters on, the date the promotion
  rule needs, and the provenance admission records. Anything beyond that waits for a demand.
- **Existing foundation retained:** the BM25 scorer (`rank-bm25`), section-level chunking, the RRF
  implementation, KB identifiers and recurrence signatures, and the S-2 reference parser, which is
  extended rather than duplicated.
- **Code and data to delete:** `retrieval/embeddings.py` and the sentence-transformers stack,
  `retrieval/reranker.py` and the CrossEncoder path, `retrieval/index.py` and the local
  transformer vector-index stack, the unreachable rerank factory mode, the `reranker` test marker
  and its tests, `RERANK_CANDIDATES`, and the divergent `bge-*` configuration. Verify here whether
  `data/profiles/` calibration scripts are still an input to corpus regeneration; if they are not,
  S-12 archives them.
- **Code to replace:** the retrieval factory and adapter mapping, superseded by the D-003 stack;
  the pointer-only hit shape, superseded by passage-bearing results, since an agent cannot reason
  over a pointer.
- **Required pre-demonstration corpus repair:** before using `inc-007`, remove the log line that
  names `inc-003`, remove causal and red-herring spoilers from tool-visible deployment notes,
  correct the inc-003 and inc-007 throughput contradiction, and repair the timing needed for the
  recurrence chain. Apply the corpus repair protocol. Retrieval influence must not be claimed when
  ordinary evidence already states the answer. If the minimum repair cannot land in this slice, use
  a controlled credible `inc-004` fixture variant instead and record that limitation.
  Divergence: this minimum repair, and more of the full corpus repair besides, already landed ahead
  of this slice (2026-08-08) as horizontal-execution-plan.md's 1.1, merged to main 2026-08-09 (#56).
  The `evt-007-01` leak is removed, all five deployment-note causal/red-herring annotations are
  removed (not only the ones this slice needed), the inc-003/inc-007 `msg_processed_rate`
  contradiction is repaired, and the `active_message_count` onset now follows the causal log rather
  than preceding it. Entry into this slice no longer needs to redo or gate on this bullet; see
  `status.md` - "Data and Corpus
  Status" for the verification evidence.
- **New implementation:** the categorized `knowledge` container and its seed script; Azure OpenAI
  embeddings; Cosmos vector query; lexical scoring; RRF; deterministic identifier and metadata
  promotion; passage-budget truncation; knowledge admission; and informing references on proposals.
  Verify Cosmos vector viability first. If it is not viable, stop and make the explicit D-003
  revision before using an in-process cosine scan.
- **Corpus setup identity, settled here and reused by S-10:** seeding writes corpus data; the
  application only ever reads it. Use the simplest posture that holds that line:
  - the CI principal, or a documented developer setup principal, performs the seed;
  - the Container App managed identity receives read-only data-plane access to `knowledge` and
    later to `operational-records`;
  - no separate runtime service, setup application, or second managed identity is created;
  - write-role assignments are scoped to the specific containers, never to the account;
  - any temporary elevated assignment is either removed after seeding or explicitly recorded as
    retained deployment-time access, with the choice written down rather than left implicit.
  A-1 verifies that the application identity still holds read-only access on these containers.
- **Contract introduced or stabilized:** retrieval result and knowledge-reference model, as an
  extension of the S-2 reference model using the same parser and resolver.
- **Telemetry and activity impact:** retrieval query, fusion and promotion decisions, passage
  budget applied, and the informing references carried into the next proposal.
- **Deterministic tests:** identifier promotion above fused position; passage budget; category
  filtering; knowledge-reference closure through the single parser; retrieval floor fixtures.
- **Evaluation increment:** the lexical-only retrieval baseline and the retrieval-influence
  measurement, both recorded and advisory.
- **Dataset or fixture work:** the minimum repair set above through the corpus repair protocol;
  category and date metadata added to KB frontmatter; retrieval fixtures regenerated.
- **Azure impact:** Azure-assisted local required. The embedding deployment and the `knowledge`
  container are added additively; no replica, authentication, or deletion change.
- **Decision gates:** the minimal knowledge metadata contract is recorded in the first PR, before
  implementation. D-003 resolves in the first technical PR. D-006 retrieval-influence selection
  resolves after the minimum data repair. All three are written into the owning document per
  operating rule 10.
- **Explicit non-goals:** no structured query, no further-evidence cycle, no full corpus repair,
  which is S-12.
- **Small PR breakdown:** (1) the minimal knowledge metadata contract, recorded and applied to KB
  frontmatter; (2) minimum demonstration-data repair; (3) D-003 viability spike and the recorded
  outcome; (4) container, seed, and embedding setup; (5) retrieval, fusion, and deterministic
  promotion; (6) informing references, feed integration, and the lexical baseline.
- **Completion evidence:** the repaired `inc-007` or the controlled `inc-004` variant shows a
  different investigation action because of retrieved knowledge, with the informing reference
  visible in the feed.
- **Status updates required after landing:** the retrieval rows in section 10.8 move to
  Implemented; the retrieval dependency rows in section 14 move to Removed; record the D-003
  outcome and the D-006 retrieval-influence selection.

#### Checkpoint after S-9

The accepted design still performs reranking, deterministically. These checks therefore look for
the rejected implementation, never for the word `rerank`, which the accepted promotion code, its
tests, and its comments may legitimately use.

| Check | Proof |
| --- | --- |
| No cross-encoder or model reranker | `git grep -n -e CrossEncoder -e RERANK_CANDIDATES -e CrossEncoderReranker -e "mode == \"rerank\"" -- src tests eval` is empty, and `git ls-files src/opspilot/retrieval/reranker.py` is empty |
| No local embedding stack | `uv tree` shows no `sentence-transformers`, `torch`; `git grep -n -e SentenceTransformer -e VectorIndex -- src` is empty and `git ls-files src/opspilot/retrieval/index.py src/opspilot/retrieval/embeddings.py` is empty |
| No BGE configuration remains | `git grep -n -e "bge-" -- src eval` is empty, because the accepted stack is an Azure OpenAI embedding deployment, not a BGE model |
| One embedding owner | `git grep -n -e EMBEDDING_DEPLOYMENT -e EMBEDDING_MODEL -- src eval` returns exactly one configuration owner, naming the Azure deployment |
| Deterministic identifier promotion is tested | `uv run pytest -k identifier_promotion` passes and fails when promotion is disabled |
| Passages reach reasoning | A retrieval result asserted in tests carries passage text and provenance, not only `doc_id` and score |
| Answer leakage is gone from the demonstration set | `uv run pytest -k leakage` passes; `git grep -n -e "RED HERRING" -e "causal:" -e "same failure mode as" -- data` is empty |

### S-10 Governed structured query

- **Demonstrable outcome:** the Investigator executes lookup, filter, and COUNT over one approved
  operational-records surface with provenance; unsupported or mutating output fails structured
  decoding or validation before source execution and appears as a limitation.
- **Course concept:** reliable agentic data reasoning through a bounded canonical structure rather
  than arbitrary SQL.
- **Entry criteria:** S-5 proposal and authorization are stable, since a query is an authorized
  evidence action; the approved surface is agreed as `incidents.json`, `deployments.json`, and
  `alerts.json` (status 11).
- **Existing foundation retained:** the corpus loader in `data/repository.py` as the local fixture
  source; the capability result envelope and admission from S-2.
- **Code and data to delete:** none.
- **Code to replace:** none.
- **New implementation:** the approved surface and its schema context; predicates, projection, and
  COUNT; mandatory scope, result limit, and timeout; deterministic validation before execution;
  the `operational-records` container and its seed; task-labelled query generation. Grouping,
  ordering, MIN, MAX, SUM, AVG, joins, writes, and arbitrary SQL have no canonical representation
  and must remain unrepresentable rather than merely rejected.
- **Contract introduced or stabilized:** governed-query structure.
- **Telemetry and activity impact:** query validation result, rejection reason, scope and limit
  applied, and execution provenance.
- **Deterministic tests:** lookup, filter, and COUNT against fixture truth; rejection before
  execution; scope, limit, and timeout enforcement; read-only enforcement on this path as on every
  other.
- **Evaluation increment:** structured-query conformance added to the aggregation, including one
  recorded refusal.
- **Dataset or fixture work:** fixture truth tables for the approved surface; no corpus change.
- **Azure impact:** Local fixture adapter first, then Azure-assisted Cosmos integration. The
  `operational-records` container is added additively and is seeded under the same setup-identity
  posture S-9 settled: setup principal writes, application identity reads only.
- **Decision gates:** none.
- **Explicit non-goals:** no arbitrary SQL, no aggregation beyond COUNT, no write path, no second
  approved surface.
- **Small PR breakdown:** (1) query contract and validator; (2) fixture truth and rejection tests;
  (3) container, seed, execution, admission, and capability wiring.
- **Completion evidence:** one accepted question answered with provenance and one visibly rejected
  question surfaced as a limitation.
- **Status updates required after landing:** the rows in section 10.9 move to Implemented; record
  the approved surface.

### S-11 In-process MCP parity

- **Demonstrable outcome:** deployment-and-change-history is accessible through direct and MCP
  transports with identical canonical results and provenance; the feed reveals transport without
  changing semantics.
- **Course concept:** MCP as a real protocol boundary, not decorative infrastructure.
- **Entry criteria:** the D-004 library inspection is complete and recorded before implementation
  starts. In-process hosting inside the single application and process is frozen and is not part of
  the inspection; D-004 settles library mechanics, session and transport handling, and result
  carriage only. The existing server already demonstrates in-process execution, same-service
  delegation, and canonical envelope passthrough (status 6.7, 17.5).
- **Existing foundation retained:** parity by delegation to the same `ToolService.call()`, with the
  same validation and sanitized errors, and the parity test pattern.
- **Code and data to delete:** all three current MCP exposures, `get_incident`, `query_logs`, and
  `search_runbooks`. None of them is the accepted capability, so the correct action is to remove
  every existing registration rather than to narrow the set. The underlying direct capabilities are
  untouched and remain available through the Evidence Access Layer.
- **Code to replace:** the exposed surface of `mcp/server.py`, superseded by exactly one exposure.
- **New implementation:** one MCP exposure for deployment and change history over the same
  implementation and the same canonical result model; the transport tag in activity and telemetry;
  registration enforcement so an unregistered capability cannot be reached.
- **Contract introduced or stabilized:** MCP parity contract.
- **Telemetry and activity impact:** transport identity on the capability span, and MCP operation
  spans, which do not exist today.
- **Deterministic tests:** result, provenance, and permission parity between transports;
  registration enforcement; no MCP-only vocabulary; the three removed exposures are unreachable.
- **Evaluation increment:** parity is asserted by tests; no evaluation change.
- **Dataset or fixture work:** none.
- **Azure impact:** Local deterministic. No infrastructure change, because hosting is in process by
  decision and cannot become a companion process.
- **Decision gates:** D-004 resolves in the first PR, before implementation.
- **Explicit non-goals:** no companion process, no second business-logic path, no MCP-only result
  vocabulary, no additional exposed capabilities.
- **Small PR breakdown:** (1) D-004 inspection and decision update; (2) remove all three exposures
  and add the accepted one; (3) parity tests and the activity transport tag.
- **Completion evidence:** side-by-side direct and MCP invocation of deployment and change history
  produces the same canonical result and provenance.
- **Status updates required after landing:** the rows in section 10.10 move to Implemented; the
  three-wrong-capabilities row in section 8.3.1 moves to Replaced; section 16 records D-004 as
  resolved and drops it from the blocked list.

### S-12 Corpus reconciliation and the further-evidence cycle

- **Demonstrable outcome:** `inc-004` naturally triggers one authorized further-evidence cycle,
  changes the assessment of the deploy red herring, and completes after the single back-edge. The
  seven authored incidents and their named controlled variants credibly cover the accepted
  evaluation classes.
- **Entry criteria:** retrieval works end to end from S-9, and corpus chronology and leakage checks
  exist as automated gates rather than manual review.
- **Existing foundation retained:** the authored corpus, its answer key, and its closure gates; the
  S-5 authorization conditions, which the further-evidence cycle reuses rather than duplicates.
- **Scope guard:** keep exactly seven authored incidents across five families. Do not add an eighth
  or ninth incident in this plan.
- **Code and data to delete:** stale data documentation, including the `data/answer_key/README.md`
  claim of six scenarios and the provenance sources that `provenance.md` does not support; the
  `data/profiles/` external calibration pipeline and its cache dependence, if S-9 established that
  it is no longer an input.
- **Code to replace:** the affected generator inputs, per the corpus repair protocol; goldens
  regenerated rather than hand-edited.
- **New implementation:** the further-evidence proposal, the four authorization conditions, the
  one-cycle flag, and the final synthesis pass after the back-edge.
- **Contract introduced or stabilized:** evaluation scenario and fixture assignments, written into
  the evaluation artifact home settled in S-2.
- **Telemetry and activity impact:** further-evidence proposal, its authorization decision against
  the four conditions, and the one-cycle flag state.
- **Deterministic tests:** the one-cycle bound; each authorization condition; seven-incident and
  five-family counts; closure; chronology; leakage; and the scenario-versus-variant distinction.
- **Evaluation increment:** D-006 selections recorded for further evidence, retrieval influence,
  the change-time scenario subset, the milestone set, and the repeatability subset; the
  repeatability subset is wired and runnable.
- **Dataset or fixture work:** repair remaining mechanism-implied telemetry (inc-002 RU, inc-005
  hit rate, inc-006 cache evidence), remaining effect-before-cause orderings and postmortem
  timelines, stale data documentation, and templated leakage. Revise an existing scenario,
  preferably inc-006, to represent multiple contributing failures while retaining its family and
  identifier. Represent benign and transient behavior through a controlled non-incident fixture
  derived from existing ambient events, not a new authored incident. Execute every change through
  the corpus repair protocol.
  Divergence: everything in this bullet except templated leakage already landed ahead of this
  slice (2026-08-08) as horizontal-execution-plan.md's 1.1, merged to main 2026-08-09 (#56).
  inc-002 (`used_ru_pct`), inc-005 (`hit_rate`), and inc-006 (`stale_read_rate`) each gained the
  missing evidence reference; the inc-004/inc-006 log-ordering inversions and the inc-003/inc-007
  metric-onset-before-cause inversions are corrected; the three historical postmortem timelines are
  retimed within their telemetry window with real dates and resolvable deploy ids;
  `data/answer_key/README.md`'s stale scenario count is fixed; inc-006 is revised in place to
  require two independently evidenced contributing signals, retaining its family and identifier;
  and `data/answer_key/benign_fixture.yaml` represents the benign/transient class from the existing
  ambient events, structurally distinct from the seven scenarios and carrying no golden record.
  Templated noise realism (905 identical error strings, no pre-incident baseline history) is
  untouched and still this slice's to do. The D-006 remaining corpus selections, the repeatability
  subset, and the further-evidence mechanism itself are also still this slice's to do: the
  divergence covers only the dataset-repair bullet above. See `status.md` - "Data and Corpus
  Status" for verification evidence.
- **Azure impact:** Local deterministic plus selected Azure-assisted model verification for the
  live back-edge demonstration.
- **Decision gates:** D-006 remaining corpus selections resolve at the end of this slice, and are
  recorded in `decisions.md` per operating rule 10. The evaluation artifact home was settled in
  S-2; this slice only assigns scenarios into it.
- **Explicit non-goals:** no eighth incident, no new scenario family, no judge, no report assembly.
- **Small PR breakdown:** (1) remaining generator and chronology repair; (2) revise one existing
  incident for multi-contributor coverage and add the benign fixture variant; (3) the
  further-evidence mechanism and its authorization tests; (4) D-006 decision update, regenerated
  goldens, and the repeatability subset.
- **Completion evidence:** a live back-edge on inc-004, and the corpus audit passing without
  expanding the authored incident count.
- **Status updates required after landing:** the further-evidence row in section 9 moves to
  Implemented; the quality concerns in section 11 are struck item by item with the regeneration
  commands recorded; section 16 records D-006 as resolved.

---

## Horizon 3: Live reconciliation, evaluation completion, and showcase

A-1 runs before S-13. The milestone report aggregates hosted smoke, so the hosted environment must
be final before the report is assembled. Running S-13 first would stabilize the report contract and
then immediately require a regeneration against a changed environment.

### A-1 Live-resource cleanup and complete hosted verification

- **Demonstrable outcome:** the deployed environment matches the accepted composition exactly:
  three Cosmos containers, three model deployments, Application Insights, built-in authentication,
  zero-to-one replicas, and the eight hosted smoke checks passing.
- **Entry criteria:** S-7 persistence, S-9 retrieval, and S-10 governed query are stable and their
  containers are seeded, so nothing is deleted that a capability still needs.
- **Existing foundation retained:** the A-0 hosted alignment, which already settled replicas,
  authentication, and telemetry; the model-import trick and the az-CLI restart technique from the
  old smoke script, reused for the citations-resolve-after-restart check.
- **Code and data to delete:** performed only after the verification in each case: the live
  `checkpoints` and `investigation-index` containers; the old job-record data or container, per the
  S-7 migration decision; the interim smoke installed in S-4; the owner-confirmed orphan
  `rytesting`, only with explicit approval. Divergence: the `rytesting` deletion was completed
  ahead of this slice, during Preparation (2026-08-08), not withheld for A-1: user confirmed, then
  deleted via `az resource delete` on the nested `proj-default` project followed by
  `az cognitiveservices account delete`. `az cognitiveservices account show` returns
  `ResourceNotFound`; `az cognitiveservices account list-deleted` shows it soft-deleted, not yet
  purged.
- **Code to replace:** `scripts/smoke_deployment.py`, superseded by the eight accepted checks.
- **New implementation:** the eight-check hosted smoke: start, authentication, model reachability,
  Cosmos role access, one streamed turn, citations resolving after restart, telemetry arrival, and
  Bicep repeatability. Bicep converges on exactly the accepted resource set.
- **Contract introduced or stabilized:** none. This slice makes live state match contracts already
  stabilized.
- **Telemetry and activity impact:** none new. Telemetry arrival becomes a hosted check.
- **Deterministic tests:** unchanged. Exact ordering and persistence-failure branches remain
  deterministic-test responsibilities and are not re-asserted in smoke.
- **Evaluation increment:** the hosted smoke result becomes an input that S-13's report aggregates
  rather than reimplements. Because this slice precedes S-13, the report is assembled once against
  a final environment.
- **Dataset or fixture work:** reseed the live `knowledge` and `operational-records` containers from
  the repaired corpus.
- **Azure impact:** Hosted verification. This slice changes the deployed contract for the second
  and final time.
- **Decision gates:** none.
- **Explicit non-goals:** no Key Vault, VNet, second app, second frontend, or telemetry viewer; no
  new capability.
- **Small PR breakdown:** (1) Bicep convergence on the accepted resource set; (2) the eight-check
  smoke replacing the interim smoke; (3) separately approved live container deletion; (4)
  separately approved orphan cleanup (the `rytesting` orphan is already deleted as of 2026-08-08,
  ahead of this slice; see the divergence note above).
- **Completion evidence:** hosted streamed turn, persisted artifact, citations resolving after
  restart, telemetry correlation visible, and a repeated deployment that converges.
- **Status updates required after landing:** section 12 is rewritten from a fresh live inspection;
  the remaining rows in section 10.15 move to Implemented; record the `az` queries actually run.

#### Checkpoint after A-1

Live state is proven by query, not by reading Bicep.

| Check | Proof |
| --- | --- |
| Only three target containers remain | `az cosmosdb sql container list -g rg-opspilot -a <account> -d opspilot --query "[].name"` returns exactly `investigations`, `knowledge`, `operational-records` |
| Three model deployments exist | `az cognitiveservices account deployment list -g rg-opspilot -n <account> --query "[].name"` lists the primary chat, lower-cost chat, and embedding deployments |
| Replicas are still zero to one | `az containerapp show -g rg-opspilot -n opspilot-api --query "properties.template.scale"` shows min 0, max 1 |
| No orphan resources remain unapproved | `az resource list -g rg-opspilot --query "[].name"` matches the Bicep output set, or each difference is explicitly approved |
| Application identity is read-only on corpus containers | The role assignments show the app identity with data-reader scope on `knowledge` and `operational-records`, and no write scope |
| Hosted smoke is exactly the accepted suite | The smoke script defines eight checks and no assertion references approval, polling, or job status |
| Deployment is repeatable | `az deployment group what-if` against unchanged parameters reports no create, delete, or modify actions. Optionally follow with a real deployment and confirm that resource IDs and the properties the accepted design names are unchanged. A plain repeat deployment is not proof, because Azure records deployment operations even when effective properties do not change |

### S-13 Evaluation completion and the milestone report

- **Demonstrable outcome:** a milestone report over the seven authored incidents plus explicitly
  named controlled variants: deterministic conformance aggregation, categorical scenario outcomes,
  the D-005 judge, the lexical-only retrieval baseline, the fixed-script evidence-plan baseline,
  the repeatability subset, the retrieval-influence and further-evidence results, and the final
  hosted smoke result.
- **Entry criteria:** D-006 selections are recorded, the corpus gates pass, and A-1 is complete, so
  the evaluation set, its home, and the hosted environment are all final before measurement begins.
- **Existing foundation retained:** the conformance aggregation from S-3, extended rather than
  rebuilt; the golden records begun at S-2 in the artifact home settled there; the fixed-script
  fixture captured at S-5; the lexical baseline from S-9; cassette and replay machinery as
  change-time determinism aids.
- **Code and data to delete:** the material parked in S-4, now finally deleted or archived by
  explicit decision: old numeric scorecards, stale rerank claims, the RCAEval probe and its
  fixtures, and the stub harness. The standalone judge configuration retained since S-0 is removed
  here, replaced by D-005 task routing.
- **Code to replace:** the remaining scorecard vocabulary, superseded by the four accepted layers.
- **New implementation:** the versioned judge rubric on the primary deployment; the expanded
  fixed-script fixture set and its comparison; categorical result assembly; the report generator;
  and the advisory CI signal, with no thresholds set before the baselines exist. Evaluation
  aggregates deterministic tests and the final hosted smoke; it does not reimplement them.
- **Two report modes, because a live judge is not byte-stable:**
  1. **Deterministic report:** generated from committed judge fixtures or cassettes, with the
     hosted-smoke result read from a committed recorded run. Reproducible byte for byte, and the
     mode CI and the checkpoint use.
  2. **Live judge run:** a deliberate run against the real deployment, written to the gitignored
     run directory as a dated, attributable, non-authoritative artifact. Schema-stable, not
     byte-identical, and never the source of a committed comparison.
- **Contract introduced or stabilized:** evaluation result and report model.
- **Telemetry and activity impact:** judge calls carry a task label and usage totals like any other
  model call, and never appear in the live investigation path.
- **Deterministic tests:** fixture and report schema; ownership boundaries, so evaluation does not
  re-assert what deterministic tests own; deterministic aggregation; the deterministic report is
  reproducible.
- **Evaluation increment:** this slice is the evaluation increment: judge, baseline comparison,
  repeatability, and report assembly over the spine built since S-2.
- **Dataset or fixture work:** golden records completed to the accepted field model; judge fixtures
  committed; fixed-script evidence plans expanded across the selected subset; the A-1 smoke result
  recorded as a committed run input.
- **Azure impact:** Local deterministic report generation; deliberate Azure-assisted judge runs. No
  infrastructure change.
- **Decision gates:** D-005 judge rubric version is recorded in the first PR and written into
  `decisions.md` per operating rule 10.
- **Explicit non-goals:** no judge in the live path, no numeric gate thresholds, no merge ratchet,
  no infrastructure change, no revival of the held-out RCAEval probe, which requirements section 12
  defers.
- **Small PR breakdown:** (1) judge rubric, fixtures, and the D-005 record; (2) baseline
  comparisons and the repeatability run; (3) report assembly and the two modes; (4) final deletion
  or archival of the S-4 parked material.
- **Completion evidence:** a readable milestone report with named outcomes and limitations,
  regenerated deterministically from committed fixtures, covering the final hosted system.
- **Status updates required after landing:** the rows in section 10.13 move to Implemented; the
  named overclaims in section 13 are struck as removed; record the report artifact path.

#### Checkpoint after S-13

| Check | Proof |
| --- | --- |
| No numeric ratchet gates merges | `git grep -n -e assert_scorecard -e baseline_regression -- tests eval` is empty; CI has no evaluation gate |
| No self-baseline is presented as a comparison | The report's baseline section names only the lexical and fixed-script baselines |
| Deferred RCAEval work is deleted or archived | `git ls-files eval tests` shows no `wild` outside an archived, CI-excluded path |
| The deterministic report is reproducible | `uv run python -m eval.report --deterministic` regenerates the committed report byte for byte |
| Live judge runs are non-authoritative | Live-run artifacts land in the gitignored run directory, are dated, and are referenced by no committed comparison |
| The report covers the final system | The report's hosted-smoke input is the A-1 run, not an earlier interim smoke |

### A-2 Demonstration polish and final repository hygiene

- **Demonstrable outcome:** the demonstration works unrehearsed: the concise brief dominates,
  repeated operations are grouped in a compact feed, and model routing, retrieval influence, MCP
  transport, cancellation, follow-up and handoff, and further evidence are discoverable without raw
  reasoning.
- **Entry criteria:** the A-1 and S-13 checkpoints are clean, the hosted smoke is green, and the
  milestone report exists.
- **Existing foundation retained:** the one-screen client and the accepted activity projection.
- **Code and data to delete:** stale G-xx and stage vocabulary in Bicep comments, smoke strings,
  and prompt and module docstrings; any remaining unused outputs.
- **Code to replace:** `README.md`, superseded by a final accurate version with the demonstration
  script.
- **New implementation:** final feed grouping and progressive disclosure, the demonstration script,
  and screenshots if useful.
- **Contract introduced or stabilized:** none.
- **Telemetry and activity impact:** none.
- **Deterministic tests:** feed grouping remains covered by the S-1 projection fidelity tests.
- **Evaluation increment:** none.
- **Dataset or fixture work:** none.
- **Azure impact:** Hosted verification only; no infrastructure change.
- **Decision gates:** none.
- **Explicit non-goals:** no new capability, no contract change, no corpus change.
- **Demonstration journeys:** predefined investigation; free-text intake with at most one
  clarification; retrieval influence; direct versus MCP; follow-up and handoff; early and late
  cancellation; the further-evidence cycle.
- **Small PR breakdown:** (1) UI and demonstration polish; (2) final documentation and repository
  hygiene.
- **Completion evidence:** the demonstration script succeeds end to end against the hosted app.
- **Status updates required after landing:** the section 15 hygiene findings are closed; the final
  assessment in section 18 is rewritten against the reconciled repository.

---

## Dependency and ordering notes

- S-0 through S-4 are ordered. S-4 is the architectural cutover; no later slice may depend on the
  old async, HITL, or checkpoint runtime, or on the evaluation that asserted it.
- A-0 follows S-4 immediately. Deferring it would leave the deployed app running a contract that no
  longer matches the repository, which is the late-integration surprise this plan exists to
  prevent.
- S-5 follows A-0 because intake normalization routes to the lower-cost deployment A-0 creates. The
  three-agent split may legitimately claim all six boundaries because the Investigation Record port
  exists from S-2.
- S-6 precedes S-7 so that the set of turns requiring a commit is fixed before the durable backend
  is built. S-7 precedes S-8 so that retained state is durable before follow-up reads it.
- S-9 must include the minimum retrieval-demonstration repair before claiming `inc-007` influence.
- S-10 and S-11 are independent of each other and of S-9, and may be reordered inside Horizon 2.
- S-12 needs S-9 for the retrieval selection and S-5 for the authorization conditions the
  further-evidence cycle reuses.
- A-1 requires S-7, S-9, and S-10, because it deletes containers and seeds the ones those slices
  introduced.
- A-1 precedes S-13 even though its identifier sorts later. S-13's report aggregates the final
  hosted smoke and the final live environment, so assembling it before A-1 would produce a report
  that must be regenerated against a changed environment immediately after its contract was
  stabilized. S-13 also consumes the D-006 selections recorded at the end of S-12.
- Deletion is distributed and coherent: S-0 debris, dead configuration, and the WIP; S-4 the old
  orchestration, HITL, roles, polling, checkpointing, concurrency wrappers, dependencies, and
  graph-dependent evaluation; S-5 the planner, triage, and sufficiency modules after the
  fixed-script capture; A-0 the hand-rolled authorization; S-9 the rejected retrieval stack; S-13
  the parked evaluation material; A-1 the live resources after verification.
- Every temporary artifact is in the coexistence register with a named deletion slice. There are no
  others.
- Slices using paid model calls rely on replay cassettes for deterministic CI and use live calls
  only for deliberate local or hosted verification.

## Slice-size notes

Three slices are larger than the rest and are watched deliberately.

- **S-2** carries the most contract weight in the plan, because the accepted contracts must land
  together rather than as temporary schemas. Its five PRs are the smallest decomposition that keeps
  each contract compilable and testable. Moving first completion into S-3 already removed the gate,
  the outcome vocabulary, and the commit from it. If it still grows, split the Investigation Record
  port and its commit-ordering contract into their own slice between S-2 and S-3, keeping the
  ordering rule ahead of the first completed turn.
- **S-12** has two primary completion claims, corpus reconciliation and the further-evidence cycle.
  They interact, because the back-edge demonstration needs the repaired corpus. If the corpus work
  runs long, split the further-evidence mechanism into its own slice after the repairs land, rather
  than shipping either half unverified.
- **A-1** is now cleanup and verification only. If it still feels broad, the live container
  deletion is the separable half and may become its own approval-gated change.

## Execution readiness criteria

This plan is ready to execute when review confirms:

1. every slice is runnable or independently verifiable;
2. no completed turn is delivered before the full terminal ordering has run, and S-3 is the first
   slice that produces one;
3. the old architecture is cut over and removed by S-4, including the evaluation that asserted it;
4. no temporary assessment contract is introduced;
5. exactly seven authored incidents remain;
6. retrieval influence is demonstrated only after repairing answer leakage and contradictions;
7. the six bounds use the accepted names, including the per-operation retry cap;
8. grounding check two retains the exact operational-support meaning;
9. obsolete approval-role machinery is removed with HITL, and hand-rolled authorization is removed
   at A-0 rather than deferred to the end;
10. every slice uses the standard template, with the same fields in the same order and none
    omitted or renamed;
11. every slice has entry criteria and completion evidence;
12. every temporary artifact appears in the coexistence register with a named deletion slice, and
    every coexistence path is a named module or file rather than a described intent;
13. every deletion checkpoint names an exact, scoped proving command, and no checkpoint rejects an
    accepted implementation;
14. every contract has a stabilization point and is not reshaped afterwards;
15. D-003, D-004, D-005, and D-006 have resolution deadlines, each status section 17 clarification
    has an owning slice, and every resolution updates the owning authoritative document or
    `decisions.md`;
16. the local, Azure-assisted, and hosted posture is stated for every slice; destructive
    infrastructure cutovers and hosting or security contract changes are confined to A-0 and A-1,
    with the single narrowly approved S-7 exception; and the interim smoke stays green through
    S-12;
17. no environment-dependent test is labelled deterministic;
18. the corpus repair workflow is explicit and referenced rather than restated;
19. S-0 through S-5 and A-0 contain path-level execution detail;
20. telemetry emission is assigned per slice rather than deferred to the hosted sink;
21. the accepted evaluation grows with capability rather than arriving at the end, and its artifact
    home exists before its first artifact;
22. every existing test module has exactly one disposition and one owning slice;
23. no slice depends on a decision that no earlier slice or authoritative document owns;
24. every slice answers what a reviewer can run, see, or verify;
25. no slice is merely framework or infrastructure construction.

---

## Appendix: test disposition

Every test module at the inspected commit has one disposition and one owning slice, so that no old
suite silently disappears and none survives to enforce superseded semantics. Keep means the module
survives essentially as is; Port means it survives with its assertions rewritten against an accepted
contract; Delete means it dies with its subject.

| Existing test | Disposition | Owning slice | Note |
| --- | --- | --- | --- |
| `test_answer_key.py` | Keep | S-12 | Corpus gate; extended by the repairs |
| `test_api.py` | Port | S-1, S-4 | Health, version, and validation survive; approval cases die in S-4 |
| `test_auth.py` | Delete | S-4, A-0 | Role suites die in S-4; A-0 adds one caller-identity test with no roles |
| `test_bm25.py` | Keep | S-9 | The lexical scorer survives the retrieval replacement |
| `test_cassette.py` | Keep | S-2 | Replay remains a legitimate change-time aid |
| `test_checkpointer.py` | Delete | S-4 | Dies with the checkpointer |
| `test_closure.py` | Keep | S-9, S-12 | Extended to knowledge references and repaired corpus |
| `test_composition.py` | Delete | S-5 | Dies with `composition.py` |
| `test_conclusion_contracts.py` | Port then Delete | S-2, S-4 | Ported to the accepted assessment shape; the old-vocabulary remainder dies with the legacy contracts module |
| `test_conclusion_wiring.py` | Delete | S-4 | Wired to the old graph terminal path |
| `test_cycle_onset_clamp.py` | Delete | S-5 | Deleted once the onset-clamp behavior is captured in the fixed-script fixture, which happens earlier in the same slice |
| `test_diagnose.py` | Delete | S-5 | Dies with the graph diagnose node and planner |
| `test_evidence_coverage.py` | Port | S-2 | Retargeted at admitted-evidence coverage |
| `test_guardrails.py` | Port | S-3, S-4 | Read-only allowlist moves to the registry; approval cases die in S-4 |
| `test_incidents_alerts.py` | Keep | S-2 | Tool behavior; envelope assertions updated |
| `test_investigations.py` | Delete | S-4 | Dies with the job repository |
| `test_investigations_api.py` | Delete | S-4 | Dies with the async job API |
| `test_kb.py` | Keep | S-9 | Extended with category and date metadata |
| `test_llm_client.py` | Port | S-5 | Narrowed to the Azure adapter, the fake, and cassettes |
| `test_llm_e2e.py` | Port | S-5 | Ported to a replay-based end-to-end test; the live Ollama path is removed |
| `test_llm_planner.py` | Delete | S-5 | Dies with `llm_planner.py` |
| `test_mcp_parity.py` | Port twice | S-2, S-11 | S-2 updates it to the new canonical envelope; S-11 updates it to the single accepted exposure |
| `test_observe.py` | Port | S-5 | Summarizers move into the Investigator |
| `test_planner_seam.py` | Delete | S-5 | Dies with the planner protocol and factory |
| `test_prompts.py` | Keep | S-2 | Versioned prompt registry survives |
| `test_report_binding.py` | Delete | S-4 | Dies with the approval-bound report hash |
| `test_repository_factory.py` | Port | S-7 | Retargeted at the Investigation Record port selecting in-memory versus Cosmos |
| `test_retrieval.py` | Port | S-9 | Reranker-marked cases deleted; fusion and promotion cases rewritten |
| `test_retrieval_factory.py` | Port | S-9 | Retargeted at the accepted backend set |
| `test_runtime_assets.py` | Keep | S-4 | Updated for the new client file and packaged corpus |
| `test_scaffold.py` | Delete | S-4 | Dies with the stub harness |
| `test_scenario_gate.py` | Delete | S-4 | Numeric merge ratchet over the graph |
| `test_schema.py` | Port | S-2 | Model-response schemas change with the accepted contracts |
| `test_search_tools.py` | Port | S-9 | Extended to passage-bearing hits |
| `test_single_agent_gate.py` | Delete | S-4 | Numeric merge ratchet over the graph |
| `test_state.py` | Port concept then Delete | S-2, S-4 | The evidence dedup and merge concept ports into admission; the LangGraph state module dies in S-4 |
| `test_state_contract.py` | Delete | S-4 | Dies with the LangGraph state contract |
| `test_sufficiency.py` | Delete | S-5 | Dies with severity-scaled sufficiency |
| `test_telemetry.py` | Port | S-1 | Extended in every slice that adds an emission fact |
| `test_tool_chain.py` | Port | S-2 | Retargeted at the two-axis envelope |
| `test_tools.py` | Port | S-2 | Envelope assertions updated; behavior retained |
| `test_tools_operational.py` | Port | S-2 | Envelope assertions updated; behavior retained |
| `test_tracing.py` | Keep | S-1, A-0 | Extended for turn identity and the real exporter |
| `test_triage.py` | Delete | S-5 | Dies with `triage.py` |
| `test_triager.py` | Delete | S-5 | Dies with the LLM triager |
| `test_wild.py` | Park then Delete | S-4, S-13 | Parked with the RCAEval probe in S-4; final disposition in S-13 |
| `tests/fixtures/wild_ob/` | Park then Delete | S-4, S-13 | Same disposition as `test_wild.py` |
| `tests/conftest.py` | Keep | Across slices | Evolves with the fixtures it serves |

New suites are named in the path-level detail table. Any test module added after this plan was
written inherits the same rule: it has a disposition or it does not merge.
