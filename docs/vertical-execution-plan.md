# OpsPilot - Vertical Execution Plan

**Status:** Working implementation plan.

Vertical-slice implementation sequence derived from `docs/status.md` against the accepted
documentation baseline. The design is settled; this document owns order, dependencies, migration
mechanics, ownership, and PR structure. It does not restate the accepted design and it does not
record build progress, which belongs to `status.md`.

This is an execution specification, not a record of executing it. A reader should be able to take
any remaining slice and know what to build, in what order, and what it must leave behind, without
first working out which parts of the text have been overtaken.

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
9. No completed turn is delivered before the full accepted terminal ordering has run: synthesis and
   structural admission, an optional shared correction for a structural failure, the four grounding
   checks, an optional shared correction and re-check for a grounding failure, outcome assignment,
   commit, then terminal delivery. The one correction allowance is shared across both points and is
   spent at most once per turn. S-3 is the first slice that produces an accepted completed turn;
   nothing before it may deliver one. Backends may change; the ordering may not.
10. Any slice that resolves a pending decision or an implementation clarification must update the
    owning authoritative document, or `decisions.md`, before its implementation PR is complete.
    `status.md` records that the question was resolved; it is never the design authority for the
    answer.
11. `status.md` records current truth; this plan records remaining work. A completed slice retains
    only the dependency information a remaining slice consumes: the contracts and capabilities it
    stabilized, and a pointer to `status.md`. Merge history, verification evidence, test counts,
    divergence explanations, and current implementation detail belong exclusively to `status.md`
    and are not duplicated here.
12. When work a later slice owns lands early, rewrite that slice to its remaining scope. Delete the
    superseded branch of the plan rather than preserving it beside a note explaining that it no
    longer applies, and make what already exists an entry criterion the slice consumes. The history
    of why reality diverged is recorded in `status.md`, not carried in the plan as a correction
    paragraph. A slice that has been overtaken should read as though it had always been scoped to
    what is left.

Slice identifiers are stable labels, not an execution order. Execution order is the order slices
appear in this document, and it differs from numeric order in one place: A-1 runs before S-13, so
that the milestone report can include final hosted verification.

## Planning posture

- The plan is deletion-led: the old runtime is cut over and removed as soon as the replacement can
  execute one real investigation, rather than preserved as a safety blanket through several
  capability slices. S-0 through S-2 have already landed the replacement's foundation; the old
  LangGraph/HITL/job-runtime path still coexists temporarily and is owned by the S-4 cutover.
- Every slice ends with something a reviewer can run, see, or verify that was not available before.
- Existing code survives only when it directly supports the accepted design and is the simplest
  suitable realization. Production suitability is not a reason to retain it.
- Azure is reconciled incrementally rather than in one late slice. A-0 aligns the hosted
  environment immediately after cutover, each capability slice adds only the resource it needs and
  adds it additively, and A-1 performs live deletion and complete hosted verification.
- Evaluation grows with capability. A slice that materially changes an AI or agentic behavior adds
  the accepted evaluation increment for it; S-13 completes the judge, baselines, and report rather
  than building the evaluation system from nothing. Plumbing-only work that introduces no meaningful
  runtime behavior owes no new evaluation artifact.
- Telemetry is emitted where behavior is added, not retrofitted. The Application Insights sink can
  wait for the hosted slice; the emission semantics cannot. A slice that adds meaningful runtime
  behavior and leaves its telemetry thin has deferred its own diagnosability, and A-0 does not exist
  to catch up on it. Plumbing-only work owes no new telemetry assertion. The obligations are stated
  once under "Diagnosability obligations" below.
- The accepted corpus remains seven authored incidents across five families. Controlled fixture
  variants may fill evaluation classes, but the plan does not silently add authored incidents.
- Course-material sequencing is an aid, not a straitjacket.
- A pending decision stays open until a consuming slice has the evidence needed to resolve it. The
  decision-gates table below is the single list of which remain open and when each resolves; D-004
  is currently the only entry.

## Standard slice template

| Field | What it records |
| --- | --- |
| Outcome | What a reviewer can run, see, or verify that was not available before |
| Consumes | What must already be true and verified before the slice starts, and what existing code it retains, with its accepted-design justification |
| Build / replace / delete | What is built, what is superseded and by what, and what leaves the repository |
| Contracts affected | Which accepted contract becomes stable here |
| Tests and evaluation | Deterministic tests that must pass, and what the advisory accepted evaluation gains here |
| Telemetry/activity, when applicable | The authoritative instrumentation facts this slice must emit |
| Small PRs | The PR sequence, one primary completion claim each |
| Done when | The concrete artifact or run that closes the slice |

Azure impact, decision gates, dataset or fixture work, and explicit non-goals are added only to a
slice where they materially apply; a slice with none of these states nothing rather than writing
"None" for each. Status updates land in `status.md` at slice completion per the rule stated below;
they are not itemized per slice here, since `status.md` records current truth by inspection rather
than by a per-slice checklist derived from this plan.

S-3 below uses this reduced shape. Slices written before this template was adopted keep their fuller
historical field breakdown, which carries the same information under more granular headings; they
are not mechanically relabeled here, since doing so would risk rewording settled, precisely-worded
scope rather than only reformatting it.

## Diagnosability obligations

This section defines what a slice's telemetry field must contain. It is stated once and is not
repeated inside each slice; each slice names only the diagnostic facts its own behavior emits.

**The bar**, read operationally from `requirements.md` NFR-20: runtime behavior emits correlated
spans and events for turn, stage, agent, model, tool, retrieval, MCP, grounding, commit, and
terminal outcome, wherever the behavior at that link exists. Important decisions and failures carry
structured fields, not prose a reader would have to parse; errors are sanitized per
`code-guidelines.md` §9; no chain-of-thought, prompt, or raw model output is exposed, in telemetry or
in the activity projection it is derived from. No telemetry store, event bus, metric registry, or
observability screen is introduced by any slice. The correlation obligation, the emitted set and
sink, the instrumentation rules, and the activity projection are owned by `system-design.md` §10.3,
`runtime-and-deployment.md` §14, `code-guidelines.md` §10, and `system-design.md` §10.4
respectively, and are not restated here.

**The reconstruction chain**, so a deployment or runtime failure is diagnosable from telemetry alone
without a human reconstructing it first:

```
revision/startup -> request/turn -> stage/agent -> model call -> capability/tool
                 -> retrieval/MCP where applicable -> grounding -> commit -> terminal outcome
```

Every link is owned by the slice that builds the behavior at that link. A-0 makes the chain queryable
in a hosted environment; A-1 verifies it end to end; neither authors a link.

**The common attribute set** carries the chain. It grows only when a slice introduces the behavior an
attribute describes, and is not a telemetry domain model:

| Attribute | Present on | Owning slice |
| --- | --- | --- |
| `investigation_id`, `turn_id` | Every span and every log record emitted inside a turn | S-1 |
| Request or operation correlation, joining a turn to the HTTP request that owns it | Turn-scoped spans | S-1 |
| Stage | Stage spans and everything nested under them | S-4 |
| Active agent, where an agent owns the operation | Agent-attributable spans | S-5 |
| Capability or tool identity | Capability spans | S-2 |
| Transport (`direct`, `mcp`) | Capability spans | S-2 mints the attribute, S-11 makes it vary |
| Execution outcome and completeness, as two separate axes | Capability spans | S-2 |
| Continuation or stop reason, where an operation ends a loop or a turn | Controller and bound spans | S-4, S-5, S-6 |
| Duration | Every span | S-1 |
| Sanitized error category and reason | Any span whose status is error, and any recorded limitation | S-2 |
| Model deployment and task label | Model-call spans | S-2 mints the label, S-5 adds the deployment |
| Backend identity, so a fixture or in-memory run is never mistaken for a live one | Persistence, retrieval, and structured-query spans | S-2 mints it on the commit span, S-7, S-9, and S-10 make it vary |
| Retrieval leg, fusion, and promotion facts | Retrieval spans | S-9 |

**Two evidence surfaces stay separate, never duplicated:** GitHub Actions owns build and deploy
evidence; OpsPilot and Application Insights own application evidence from startup onward. They join
on the revision identity, so a deployment can be traced from the failing workflow step to that
revision's startup and runtime behavior without either surface copying the other's output.

**Completion evidence.** A slice with meaningful runtime behavior closes on a telemetry assertion as
well as a functional one: the deterministic suite asserts that the facts the slice named are emitted,
with correlation attributes present, through the in-memory exporter fixture. A-0 and A-1 close on a
real query against Application Insights.

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
| Stream envelope, turn identity, live-session presentation state, activity projection | S-1 |
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

D-004 is the only decision `decisions.md` still carries as pending; it is listed here so "pending"
does not become "forgotten". D-005 and D-006 are both Accepted, with every D-006 selection criterion
already naming a real incident identifier: no slice below resolves either, and where a slice
mentions one it is consuming an accepted answer, not making one.

| Decision | Resolve when | Blocks |
| --- | --- | --- |
| D-004 MCP library mechanics and transport carriage | Before S-11 implementation | Library usage, session handling, result carriage |

A gate that would force a documented design revision rather than a recorded selection is stopped
on and revised explicitly, never worked around with a runtime fallback.

D-004 does not reopen hosting. One real in-process MCP boundary inside the single application and
process is frozen; D-004 settles library mechanics, session and transport handling, and result
carriage only.

## Implementation clarifications and their owners

Questions the repository exposed that a slice must answer before code invents an incompatible one.

| Clarification | Owning slice | Default position |
| --- | --- | --- |
| Stateless clarification token | S-5 | Prefer simple resubmission of the original input; introduce a signed short-lived token only if resubmission demonstrably fails the requirement |
| Minimal knowledge metadata contract | S-9, first PR | Identifier, container category, promotion date, and admission provenance only. No authoritative document fixes this today, so S-9 records it before implementing rather than treating it as a precondition |
| D-004 library evidence | S-11 | In-process hosting is fixed; record the library findings |

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
| S-7 | Deterministic contract tests over the port; a separate Azure-assisted Cosmos integration lane |
| S-8 | Local deterministic, with one optional Azure-assisted follow-up verification |
| S-9 | Azure-assisted local required for embedding and vector queries; deterministic fixtures for CI |
| S-10 | Local deterministic. The query engine's own Azure-assisted Cosmos integration already ran; what remains is the authorization wiring, which needs no new infrastructure |
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
| Two-axis to binary capability-result shim for old consumers | The old planner and claim admission read `status: ok\|error` | S-2 | S-4 |
| Deprecated `EvalTargets` numeric thresholds | The old scenario and single-agent gates still consume them; removing the configuration before its consumers would break the S-0 baseline | Pre-existing, frozen and marked deprecated at S-0 | S-4, with the gates that read it |
| Three incorrect MCP exposures (`get_incident`, `query_logs`, `search_runbooks`) | Parity must survive the S-2 envelope change continuously; narrowing the exposed set is a separate concern | Pre-existing, carried through S-2 | S-11 |
| Old `safety_validate` wrapper delegating to the four-check gate | The old graph path still calls a safety step after S-3 replaces the policies | S-3 | S-4 |
| Legacy claim admission and template rendering (`diagnosis/admission.py`, `diagnosis/render.py`) | The old report/claim model still needs them while the graph path runs; the accepted brief projection is `assessment/brief.py` and does not use either | Pre-existing, frozen at S-2 | S-3 for claim admission if the gate makes it redundant; `render.py` when S-4 and S-5 delete its two remaining callers |
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

These slices restructure the repository, so their paths are named now. A path marked "proposed" is
not yet created; a path with no such mark is landed and confirmed against the current repository.
S-6 onward keeps provisional placement until this structure exists.

| Concern | Path | Owner slice | Note |
| --- | --- | --- | --- |
| Stream envelope and activity contract | `src/opspilot/stream/contracts.py` | S-1 | Landed |
| Activity projection from instrumentation facts | `src/opspilot/stream/projection.py` | S-1 | Landed. Derives from `obs/tracing.py` span facts |
| Turn identity and live-session presentation state | `src/opspilot/turn/identity.py` | S-1 | Landed |
| Normalized incident context and intake classification | `src/opspilot/intake/contracts.py` | S-1 | Landed for predefined intake only; S-5 adds free text and clarification |
| Telemetry seam | `src/opspilot/obs/tracing.py` | S-1 | Retained as the one emission seam. Every later slice adds its facts here and asserts them through the in-memory exporter |
| Application startup hook and exporter wiring | `src/opspilot/api.py` | A-0 | No startup hook exists today. A-0 adds one and calls `configure_exporter()` from it, alongside the startup, configuration-validation, and readiness records that need the same hook. Before A-0 there is no sink to select |
| Streaming endpoint | `src/opspilot/api.py` | S-1 | Landed beside the old routes; old routes removed in S-4 |
| One-screen client | `src/opspilot/static/investigation.html` | S-1 | Landed. Single file, no build step. The old console keeps working until S-4 |
| Old approval console deletion | `src/opspilot/static/console.html` | S-4 | Deleted when the new screen becomes the sole client |
| Evidence reference model, parser, resolver | `src/opspilot/evidence/references.py` | S-2 | Landed as the single owner. Duplicate parsing that once lived in `diagnosis/admission.py` and `diagnosis/sufficiency.py` is retired with those modules at S-3/S-5 |
| Evidence admission (observations) | `src/opspilot/evidence/admission.py` | S-2 | Landed, Evidence Access Layer owned. Not `diagnosis/admission.py`, which admits model-proposed claims, a different thing that S-3 folds into the grounding gate or deletes |
| Capability result envelope | `src/opspilot/tools/contracts.py`, `tools/service.py` | S-2 | Landed. Two-axis execution-outcome and completeness replaces `ok`/`error` |
| Capability registry | `src/opspilot/tools/__init__.py` | S-2 | Landed. Registry and `READ_ONLY_TOOLS` duplication collapsed to one source |
| Final assessment contracts | `src/opspilot/assessment/contracts.py` | S-2 | Landed. `src/opspilot/contracts.py` is frozen as legacy-only and deleted in S-4 |
| Investigation Record port and in-memory backend | `src/opspilot/record/` | S-2, S-3 | Port and commit-ordering rule landed at S-2, over the in-memory backend; the completed-turn artifact and the first real commit are S-3; the Cosmos backend is S-7 |
| MCP result serialization | `src/opspilot/mcp/server.py` | S-2, S-11 | S-2 carries the new canonical envelope through unchanged; S-11 changes only the exposed capability set |
| Evaluation artifact home | `eval/fixtures/`, `eval/reports/`, and a gitignored `eval/runs/` (proposed) | S-2 | Layout settled by `decisions.md` D-009; the directories are created when a slice first commits an artifact to one, not before |
| Model-access seam and task labels | `src/opspilot/llm/` | S-2, S-5 | Retained; task-label routing and provider narrowing in S-5 |
| Provider narrowing | `src/opspilot/llm/client.py`, `config.py` | S-5 | One Azure OpenAI adapter plus the fake and cassette seams; Ollama and generic OpenAI selection removed |
| Grounding gate | `src/opspilot/grounding/checks.py` (proposed) | S-3 | Absorbs `guardrails/policies.py`; exactly four checks |
| Claim admission | `src/opspilot/diagnosis/admission.py` | S-3 | Folded into the gate or deleted if the assessment and gate make it redundant |
| Deterministic brief projection | `src/opspilot/assessment/brief.py` | S-2 | Landed: projects the admitted assessment by traversal alone. `diagnosis/render.py` is unrelated legacy template rendering for the old report/claim model; it is still called by the graph path and by `llm_planner.py` and is orphaned once S-4 and S-5 delete both callers |
| Explicit turn controller | `src/opspilot/turn/controller.py` (proposed) | S-4 | Replaces `graph.py` and `router.py`. `src/opspilot/turn/synthesis_step.py` already exists as the gather/admit/synthesize step the streamed path calls directly; the controller is a distinct, not-yet-built piece that will own stage sequencing around it |
| Old orchestration deletion | `src/opspilot/graph.py`, `nodes/investigation.py`, `router.py`, `checkpoint.py` | S-4 | Deleted; ingest/gather/synthesize logic already harvested into `turn/synthesis_step.py` |
| Old API deletion | `src/opspilot/api.py` async job routes, `investigations.py`, `cosmos_investigations.py`, `repository.py` | S-4 | Job lifecycle, decision endpoint, outbox, lease and fencing removed |
| Legacy contract module deletion | `src/opspilot/contracts.py` | S-4 | Deleted with the old runtime; a narrow re-export from `assessment/contracts.py` is permitted if imports are widespread |
| Authorization reduction | `src/opspilot/auth.py` | S-4, A-0 | Three-role surface deleted in S-4; minimal caller-identity seam replaced by built-in authentication in A-0 |
| Concurrency reduction | `src/opspilot/api.py`, `config.py` | S-4 | Per-user and role-based admission collapsed to one configured application-level limit |
| Dead configuration removal | `src/opspilot/config.py` | S-0, S-4, S-5, S-13 | Severity routing, numeric confidence, and dispatch keys in S-0; deprecated `EvalTargets` in S-4 with the gates that read it; six bounds in S-5; standalone judge configuration in S-13 |
| Dependency removal | `pyproject.toml`, `uv.lock`, `Dockerfile` | S-4, S-9, A-0 | Graph and checkpoint groups in S-4; the local embedding stack in S-9; `pyjwt` in A-0 |
| Agent modules | `src/opspilot/agents/supervisor.py`, `investigator.py`, `analyst.py` (proposed) | S-5 | Split from the S-4 single-flow controller |
| Free-text normalization and clarification | `src/opspilot/intake/normalize.py` (proposed) | S-5 | Produces the S-1 normalized incident context |
| Fixed-script evidence plan fixture | `eval/fixtures/evidence_plans/` (proposed) | S-5 | Extracted from `diagnosis/planner.py` and `cycle.py` before they are deleted |
| Test deletion | `tests/test_investigations_api.py`, `test_investigations.py`, `test_report_binding.py`, `test_checkpointer.py`, `test_auth.py`, `test_scenario_gate.py`, `test_single_agent_gate.py` | S-4 | Deleted with their subjects, not rewritten |
| Test deletion, second wave | `tests/test_triage.py`, `test_triager.py`, `test_composition.py`, `test_sufficiency.py`, `test_planner_seam.py`, `test_diagnose.py`, `test_llm_planner.py` | S-5 | Deleted with the planner and triage subjects |
| Test replacement | `tests/test_stream_projection.py`, `test_evidence_references.py`, `test_record_commit.py`, `test_grounding_gate.py`, `test_turn_controller.py` (proposed) | S-1, S-2, S-3, S-4 | New deterministic suites |
| Every other existing test module | `tests/` | Various | Disposition is stated inside the slice that deletes or supersedes its subject, not tracked separately |
| Bicep and hosted alignment | `infra/main.bicep`, `scripts/smoke_deployment.py` | S-4, A-0 | Interim smoke in S-4; replicas, authentication, App Insights, lower-cost deployment in A-0 |

---

## Horizon 1: Foundation cleanup, first executable flow, cutover, and hosted alignment

## Completed slices

Retained only for what remaining slices consume. Current implementation truth, landed PRs,
verification evidence, and the history of where reality diverged from the original text are in
`status.md`.

| Slice | Provides to the remaining plan |
| --- | --- |
| S-0 | A clean `main`-based baseline: the authoritative documentation committed, the rejected dispatch skeleton absent, dead severity-tier configuration and corpus-path duplication removed, and a green lint, type, and test baseline to build on. |
| S-1 | Turn identity; the stream envelope and its ordering, identities first and close marker last; the normalized incident-context contract (`decisions.md` D-007); the `InteractionKind` type, shape only; the activity projection; client-disconnect detection; and the one-screen client at `/investigation`. |
| S-2 | The evidence reference model with one parser and one resolver, including the `absence:` form that makes an authoritative empty result citable (`decisions.md` D-008); the two-axis capability result vocabulary and the Evidence Access Layer admission that assigns every reference and records a limitation for every operation that did not answer; the assessment, candidate-cause, recommendation, limitation, and brief contracts, with qualitative support labels and no numeric confidence; the task-labelled `rca_synthesis` call and the deterministic brief projection; the Investigation Record port, its commit semantics, and the commit-before-delivery ordering rule; the capability, model, and admission spans of the common attribute set, with `investigation_id` and `turn_id` inherited by every span emitted inside a turn; the evaluation artifact layout settled as `decisions.md` D-009, whose directories are created by the first slice that commits an artifact to one; and the replay cassette that keeps the synthesis path deterministic in CI. |

**The one telemetry seam.** `obs/tracing.py` is the single emission seam every later slice attaches
to, never a second one. It provides OTLP-shaped spans with nesting through context variables, an
exporter selected by configuration, and the in-memory exporter that deterministic telemetry
assertions run against. `standard_attributes` carries `investigation_id`, `incident_id`,
`workflow_version`, and `turn_id`; `span()` carries duration. Those are the correlation columns of
the common attribute set under "Diagnosability obligations"; every other column is minted by the
slice that introduces the behavior it describes. Request-to-turn correlation rides the same
identifiers, since one streaming request owns one turn.

### S-3 Four grounding checks, correction allowance, outcomes, and the first completed turn

- **Outcome:** the first accepted completed turn. Every delivered assessment passes exactly four
  deterministic checks, is assigned complete, partial, or inconclusive, is committed, and only then
  produces the terminal event. A deliberately malformed synthesis spends the turn's one shared
  correction allowance before the checks run and, if still invalid, produces failed execution with
  no completed artifact, no commit, and no delivered brief. The full terminal ordering is realized
  here in full and no later slice may reorder it: synthesis and structural admission, the shared
  correction allowance if a structural failure spends it, the four checks, the same allowance and a
  re-check if a grounding failure spends it, outcome assignment, commit, then terminal delivery.
- **Consumes:** the accepted assessment contract, one real structured synthesis completing end to
  end under replay, and the Investigation Record port's commit semantics and lifecycle
  delivery-ordering contract test, all from S-2. The port gains its first real writer and first
  real artifact here; the produced-reference discipline is a real ancestor of the reference
  resolution this slice needs.
- **Build / replace / delete:** build citation and reference resolution with permitted role and
  type pairing; required operational support for grounded elements marked established;
  recommendation-provenance presence; disclosure of recorded limitations; the one shared correction
  allowance; deterministic outcome assignment; the completed-turn artifact the port stores; the
  commit itself; terminal delivery after the commit; and failed-execution behavior outside the
  three completed outcomes. Do not add semantic entailment, temporal coherence, or a fifth check.
  Replace `guardrails/policies.py` citation grounding with the four-check gate; delete the
  two-policy surface and its tests once the gate subsumes it, and `diagnosis/admission.py` claim
  admission if the accepted assessment and the gate make it redundant, which is the expected
  outcome. The read-only allowlist behavior moves to the capability registry rather than being
  deleted. The old graph path keeps a thin `safety_validate` wrapper delegating to the new gate
  until S-4 deletes it with the graph; it is registered in the coexistence register.
- **Contracts affected:** grounding result, completed-outcome vocabulary, the completed-turn
  artifact, and terminal ordering become stable here. S-4 moves this exact ordering into the
  permanent turn controller without reopening it; S-5's six bounds reuse the correction allowance
  rather than creating a second one; S-6's cancellation and degradation outcomes reach the same
  three-outcome vocabulary and artifact rather than a parallel one; S-7 persists exactly this
  artifact shape; S-8 answers follow-up and handoff only from a completed turn this contract
  produces; S-13 aggregates this conformance entry point rather than building a second one.
- **Tests and evaluation:** each of the four checks independently, and the fixed set with no fifth;
  single-spend correction allowance; rendering remains a projection; the full terminal ordering
  asserted end to end; persistent failure delivers nothing, commits nothing, and is not one of the
  three completed outcomes; a commit failure after a passing gate also delivers nothing; at least
  one deterministic, replayed end-to-end incident demonstrating the completed path. A
  malformed-synthesis fixture drives the correction demonstration. Advisory evaluation increment:
  the deterministic conformance aggregation entry point, covering grounding results and completed
  outcomes over the S-2 golden record, written into the evaluation artifact home settled in S-2.
- **Telemetry/activity:** grounding result per check, naming which check failed rather than a bare
  pass/fail; correction-allowance spend, and whether it was the first or a refused second; outcome
  assignment and its deterministic reason; the commit result; the terminal shape decision. Failed
  execution emits its own terminal fact with a sanitized failure category, so a turn that delivered
  nothing is distinguishable from one that completed inconclusively, and a persistent grounding
  failure is distinguishable from a commit failure after a passing gate.
- **Explicit non-goals:** no fifth check, no semantic entailment, no Cosmos persistence, no agent
  split, no cancellation semantics.
- **Small PRs:** (1) grounding result contracts; (2) the four checks and correction routing, with
  the old-path wrapper; (3) outcome assignment, the completed-turn artifact, commit, and terminal
  delivery; (4) failed-execution behavior and conformance aggregation.
- **Done when:** exactly four grounding checks exist; one shared correction allowance exists per
  turn across structural-synthesis correction and grounding correction;
  complete/partial/inconclusive outcomes are assigned correctly;
  failed execution stays outside the three completed outcomes; a real completed-turn artifact
  exists; the commit occurs before terminal delivery; a persistent grounding failure commits and
  delivers nothing; deterministic tests cover the four checks, correction exhaustion, outcome
  derivation, and commit/delivery ordering; and at least one deterministic, replayed end-to-end
  incident demonstrates the completed path, diagnosable from its spans alone: which check failed,
  that the correction allowance was spent, that no commit was attempted, and the sanitized failure
  category.

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
  The Cosmos containers, their Bicep declarations, the two deployment settings that selected
  them, and the hosted smoke's durable-pause assertion are already gone; this slice's remaining
  work here is the code deletion above.
- **Graph-dependent evaluation removed or parked in the same slice:** `eval/scenario_eval.py`,
  `eval/record_single_agent.py`, `tests/test_scenario_gate.py`, `tests/test_single_agent_gate.py`,
  the committed numeric scorecards, and the stub `eval/harness.py` with
  `tests/test_scaffold.py`. Parked material moves under a clearly archived path excluded from CI;
  S-13 makes the final keep-or-delete call. Leaving these active would
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
- **Contract introduced or stabilized:** turn-controller and terminal-delivery ordering; the sole
  streaming runtime; the application-level concurrency posture; the interim hosted smoke contract.
  **Who builds on each:** S-5 extends this same controller into the three-agent realization rather
  than replacing it with a second one; S-6 adds cancellation behavior at this controller's safe
  boundaries rather than a new control structure; A-0 verifies the interim smoke hosted, and A-1
  replaces it with the eight-check suite once later capabilities exist to check. This slice adds no
  agent and no cancellation semantics itself; both are named here only so the next two slices know
  exactly what they extend.
- **Telemetry and activity impact: diagnostic continuity through the cutover is this slice's
  obligation, not a side effect of it.** Deleting the graph deletes `traced_node`, the wrapper that
  today establishes the root span and attaches the correlation attributes to everything nested
  under it. The controller takes over that job, and the swap is complete only when the replacement
  emits at least what the wrapper emitted:
  - one root turn span the whole turn nests under, carrying the correlation attributes, replacing
    the wrapper's per-node root;
  - a stage span per controller stage, with a stable stage name as an attribute rather than
    encoded into the span name, covering objective, evidence, synthesis, gate, and commit;
  - stage entry and exit with duration, the transition taken, and the stop reason when a stage
    ends the turn, so an unfinished turn shows where it stopped;
  - a sanitized failure category on any stage that errors, and error status propagated to the root
    span, replacing the wrapper's reflection of a node's `error`/`degraded` return;
  - the same attributes on nested capability, model, and commit spans as before, since the
    controller establishes the context they inherit.
  Adding `stage` to the common attribute set is this slice's contribution to it. This closes the
  `request/turn` and `stage` links of the reconstruction chain, and it is why the swap loses
  nothing.
- **Deterministic tests:** one complete streamed turn; one gate failure; old route absence; no
  runnable approval or checkpoint behavior; the suite green after obsolete tests are removed rather
  than rewritten to validate deleted behavior. One continuity test that a reviewer would not
  predict: capture the node wrapper's emitted fact set before it is deleted, then assert that a turn
  run through the controller against the in-memory exporter emits at least that set, with the
  correlation attributes present on every span. The cutover then fails the suite rather than
  silently going dark. `test_telemetry.py` and `test_tracing.py` keep their own scope; this is a new
  assertion, not a re-owned module.
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
#### Checkpoint after S-4

This is the architectural cutover; nothing later may depend on the deleted runtime. Required: the
graph runtime, checkpointer, HITL surface, polling job API, approval roles, legacy contracts module,
and old console are removed from `src/`; `langgraph`, `langchain-core`, `langgraph-checkpoint-sqlite`
are removed from `pyproject.toml`/`uv.lock`; concurrency is one configured limit rather than
per-user/per-role admission; deprecated `EvalTargets` and the graph-dependent evaluation it fed are
gone or archived outside CI's path; `uv run pytest -m "not reranker and not llm"` is green with none
of the deleted subjects' test modules present; and the continuity test asserts the turn controller
emits at least what `traced_node` emitted before deletion (a root turn span, a span per stage with a
stable name, duration, stop reason where a stage ends the turn, and `investigation_id`/`turn_id` on
every span). One targeted search proves the most load-bearing rejection actually left the tree:
`git grep -n -e hitl_gate -e apply_edit -e CommittedDecision -e "/decision" -- src tests scripts` is
empty.

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
  telemetry seam through `configure_exporter()`; the lower-cost chat deployment added so that S-5
  has a routing target; the interim smoke run as the post-deploy gate.
  **The application startup hook is built here, and it is a precondition for the rest of this
  slice rather than an incidental.** `api.py` constructs its application object and registers no
  startup hook at all, and `configure_exporter()` is called only by `tests/conftest.py`, so the
  process exporter is the no-op in every non-test run today. One hook serves four things this slice
  needs: exporter selection, the startup record, configuration validation, and readiness. No
  earlier slice needs it, because before this slice there is no sink an exporter could select.
  The exporter is the smallest one that carries the seam's spans to Application Insights with the
  correlation attributes intact. Adopting a vendor telemetry SDK is justified only if the existing
  seam demonstrably cannot reach the sink, and that finding is recorded in the owning document per
  operating rule 10 before the dependency is added. No second emission path is created either way.
  **Who builds on each:** S-5's intake-normalization task label routes to the lower-cost deployment
  created here, and to no other; A-1 verifies, rather than creates, the zero-to-one replica posture,
  built-in authentication, and Application Insights sink this slice establishes, and replaces this
  slice's interim smoke with the eight-check suite once S-7/S-9/S-10 give it something to check. The
  zero-to-one posture is not revisited by a later slice: it stays the single-writer, ephemeral-
  active-state runtime shape the whole design assumes.
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
- **Telemetry and activity impact: hosted telemetry availability, plus the hosting facts no earlier
  slice could emit.** The application-level spans S-1 through S-4 already emit reach a real sink for
  the first time, and correlation must survive the exporter: `investigation_id` and `turn_id` must
  be queryable as fields in Application Insights, not buried in a message string, and parent and
  child spans must still resolve into one trail after export. That is the larger half of this slice.
  The smaller half is that "no new emission points" would be a false claim, because nothing before
  this slice runs in a hosted environment and therefore nothing emits the facts that make a
  deployment failure diagnosable. This slice adds those, and only those:
  - **Startup:** one startup record naming the running revision, the image tag, and the environment,
    so a workflow step that deployed a revision can be joined to the application that started from
    it. Without this join, a failed deployment is diagnosable only from the workflow side.
  - **Configuration validation:** the result of the startup validation
    `runtime-and-deployment.md` §13 already requires, and on refusal, which setting or posture was
    unacceptable, by name and never by value. A refusal to start is the most common deployment
    failure and the least self-explanatory one.
  - **Readiness:** the readiness result and, on failure, the reason category, so a revision that
    starts but never becomes ready is distinguishable from one that never started.
  - **Uncaught runtime exceptions:** a sanitized record with the error category, the operation, and
    the correlation attributes if the failure occurred inside a turn. An unhandled exception that
    reaches no sink is the single largest opaque case.
  Nothing else is added. No hosting metric, no dashboard, no alert rule, no log-analytics workbook,
  and no telemetry viewer, per `runtime-and-deployment.md` §14.
- **Deterministic tests:** hosted behavior is not re-asserted in deterministic tests. Two things
  this slice adds are application behavior rather than hosted behavior and are tested offline: that
  a configuration refusal emits the offending setting by name and never its value, and that a
  sanitized exception record carries a category and correlation attributes and carries no secret,
  prompt, or raw payload.
- **Evaluation increment:** none.
- **Dataset or fixture work:** none.
- **Azure impact:** Hosted verification. This slice changes the deployed contract; A-1 is the only
  other slice that does.
- **Decision gates:** none.
- **Explicit non-goals:** no Cosmos container change, no embedding deployment, no eight-check
  smoke, no live container deletion, no Key Vault, no VNet. No dashboard, workbook, alert rule,
  retention tier, or telemetry viewer, and no copying of GitHub Actions build or deploy output into
  Application Insights; the two evidence surfaces stay separate per "Diagnosability obligations".
- **Small PR breakdown:** (1) replicas, probes, and the `/health` alias removal; (2) built-in
  authentication, the documented smoke-caller identity and audience, and removal of the
  hand-rolled JWT path; (3) the application startup hook, Application Insights, exporter wiring on
  that hook, and the startup, configuration-validation, readiness, and sanitized-exception records;
  (4) lower-cost chat deployment.
- **Completion evidence:** one hosted streamed turn whose complete diagnostic trail is queryable in
  Application Insights, and the interim smoke green in CD. "Complete" means the trail reconstructs
  the chain named under "Diagnosability obligations" as far as this slice's capabilities reach:
  the revision's startup record, the request and turn, each stage, the model call, each capability
  call, the grounding result, the commit, and the terminal outcome, retrieved by querying on
  `investigation_id` or `turn_id` and not by reading raw message text. The queries actually run are
  recorded, so A-1 verifies rather than rediscovers them.
#### Checkpoint after A-0

| Check | Proof |
| --- | --- |
| Replicas are zero to one | `az containerapp show -g rg-opspilot -n opspilot-api --query "properties.template.scale"` shows min 0, max 1 |
| Built-in authentication is enabled | `az containerapp auth show -g rg-opspilot -n opspilot-api` reports an enabled platform with one registration |
| Hand-rolled authorization is gone | `git grep -n -e pyjwt -e jwks -e ReviewerPrincipal -- src tests` is empty; `uv tree` shows no `pyjwt` |
| Application Insights is connected | `az monitor app-insights component show -g rg-opspilot --app <name>` resolves and one turn's spans are queryable |
| Correlation survives export | A query filtering on `turn_id` returns that turn's spans, and their parent and child relationships still resolve into one trail. Message-text matching is not accepted as proof |
| The revision joins to its deployment | The startup record names the running revision and image tag, and matches what the deploying workflow run reported |
| Configuration and readiness failures are legible | A deliberate local run with a required setting removed emits a refusal naming that setting and not its value, and the readiness failure reason is a category rather than prose |
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
  Ollama tests, which are the slowest tests in the full suite by a wide margin, and update
  `test_llm_client.py` and `test_llm_e2e.py` accordingly. The seam stays replaceable in tests; the
  runtime stops being a multi-provider product.
- **Fixed-script capture precedes deletion:** `diagnosis/planner.py` and `diagnosis/cycle.py` are
  the accepted fixed-script baseline's behavioral source (same tools, predetermined order,
  currently living as a runtime fallback). Extract the first fixed-script evidence-plan
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
  every task this slice actually calls a model for: intake normalization, objective interpretation,
  source selection, synthesis, and correction, with intake normalization routed to the lower-cost
  deployment and the rest to the primary. `decisions.md` D-002 already fixes the deployment for
  every task in its routing table, including ones no slice yet calls (follow-up answering,
  structured-query generation, the offline judge), so nothing about their eventual routing is
  rediscovered later; only their labels are deferred to the slice that introduces the task, per
  operating rule 8 and the vertical-slice discipline this plan follows throughout.
- **Clarification mechanism:** prefer resubmission of the original input with the clarifying answer
  over a signed short-lived normalization token. A token is introduced only if resubmission
  demonstrably fails the requirement, and then only with an explicit signing, expiry, and payload
  contract.
- **Bounds:** exactly turn deadline, capability-call cap, model-call cap, per-operation
  transport-retry cap, shared correction allowance, and further-evidence-cycle flag. The retained
  `MAX_TOOL_CALLS` setting is renamed to the capability-call cap and enforced here. The shared
  correction allowance is the one S-3 already defined, reused here rather than a second mechanism;
  the further-evidence-cycle flag is minted here as a bound with nothing behind it yet, so S-12 has
  a flag to authorize against instead of inventing one. Token use is measured; there is no token
  ledger.
- **Contract introduced or stabilized:** agent proposal and authorization; free-text normalization
  and the single-clarification flow; the task-labelled model-access seam, extended with routing.
  **Who builds on each:** S-9, S-10, and S-12 each propose their own evidence or query action
  through this same proposal/authorization contract rather than a bespoke one; S-12 authorizes its
  one further-evidence cycle against the flag this slice mints; S-8's follow-up task, S-10's
  structured-query task, and S-13's judge task each add their own label to this same routing seam
  rather than building a second one.
- **Telemetry and activity impact:** agent identity as an attribute on every operation an agent
  owns, which is this slice's addition to the common attribute set; the handoff between agents as
  its own fact, so a turn that stalled between two agents is visible; proposal, authorization, and
  refusal each as separate facts, with the refusal carrying which computable condition failed rather
  than a bare refusal; the bound-stop reason naming which of the six bounds stopped the turn; the
  task label and the resolved deployment on every model call, so a routing mistake is visible in
  telemetry rather than only in a bill. Clarification appears as an interaction fact, not as model
  content, and no proposal, authorization, or refusal fact carries the model's reasoning for it.
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
- **Decision gates:** the stateless clarification token clarification is settled here.
- **Explicit non-goals:** no further-evidence cycle, which is S-12; no retrieval; no Cosmos
  persistence.
- **Small PR breakdown:** (1) extract and commit the fixed-script fixture; (2) agent interfaces and
  the Supervisor control and judgment seam; (3) Investigator proposal and authorization loop with
  parallel actions; (4) Analyst synthesis and task-label routing; (5) provider narrowing and the
  live-model test removal; (6) free-text normalization and the single clarification; (7) bounds and
  their tests, and deletion of the superseded modules.
- **Completion evidence:** role-attributed feed, distinct execution paths for two incidents, one
  free-text submission normalized, and one clarification exchange. The two divergent paths are
  distinguishable from their spans alone, with agent identity, the authorization decisions, and the
  routed deployment per model call visible without reading the feed.
### S-6 Cancellation, degradation, and honest partial or inconclusive results

- **Demonstrable outcome:** early cancellation before evidence completes yields a committed
  inconclusive completed turn with no assessment and no brief; later cancellation with admitted
  evidence may produce a committed partial result and brief; client disconnect discards active
  state and commits nothing; source failure becomes a recorded limitation rather than a fabricated
  observation.
- **Entry criteria:** S-5 agent boundaries and the six bounds are enforced and tested; the turn
  controller has identifiable safe boundaries to cancel at.
- **Existing foundation retained:** client-disconnect detection on the streaming endpoint, which
  stops emission but is not the accepted cancellation-request mechanism; the S-3 outcome
  vocabulary, which already carries inconclusive; the S-2 commit ordering, which cancellation
  outcomes reuse rather than bypass.
- **Code and data to delete:** none.
- **Code to replace:** none.
- **Missing foundation this slice must build first, before safe-boundary semantics:** the accepted
  explicit cancellation-request mechanism does not exist yet. `runtime-and-deployment.md` names it
  as its own transport, a small ordinary request distinct from the streaming request the turn owns,
  that signals one small in-memory map from active turn identity to a cancellation signal, alive
  only while that streaming request is active, not durable, not a job registry, not used for
  recovery or reattachment. PR 1 of this slice owns minting that map and the signalling endpoint;
  everything else in this slice is safe-boundary behavior that reads the signal PR 1 writes.
- **New implementation:** the explicit cancellation-request endpoint and its in-memory signal map
  (PR 1, above); safe-boundary cancellation in the explicit controller, which checks the signal at
  each boundary rather than the disconnect flag S-1 left; the evidence-admitted decision that
  separates partial from inconclusive on the cancellation path (a binary check, not a materiality
  judgment: materiality is a separate mechanism gating the source-failure degradation path in this
  same slice, not cancellation); stop and inconclusive-reason vocabularies; no unsupported
  assertions anywhere in a degraded result.
- **Cancellation persistence matrix, stated exactly so the commit rule is unambiguous:**

  | Situation | Outcome | Assessment and brief | Committed |
  | --- | --- | --- | --- |
  | Cancelled before any evidence is admitted | Inconclusive completed turn | None | Yes |
  | Cancelled after evidence is admitted | Partial completed turn | Yes | Yes |
  | Client disconnect | Not a completed turn | None | No; active state is discarded |
  | Persistent grounding failure | Failed execution, outside the three completed outcomes | None | No |

  "Nothing is persisted for non-completed execution" therefore excludes the cancellation row that
  produces a completed outcome. Cancellation is a completed turn; disconnect is not.
  **Blocker for the design authority, not resolved here:** an earlier version of this matrix split
  the evidence-admitted cancellation row further, into a materiality-gated partial-versus-
  inconclusive choice. `workflow-design.md`'s own rule is a plain binary: at least one admitted
  piece of evidence delivers a partial brief, full stop; no design document gates that specific
  branch on materiality (materiality gates the source-failure path instead). The row is removed
  above to keep the plan consistent with the currently accepted authority. If the finer split was
  actually intended, `workflow-design.md` needs an explicit revision recording it; this plan does
  not invent one.
- **Contract introduced or stabilized:** the explicit cancellation-request mechanism; cancellation,
  degradation, and cancelled-turn persistence rules. **Who builds on each:** this fixes the
  complete, closed set of situations that produce a completed turn (normal completion, cancellation,
  or degradation, always one of the three accepted outcomes), and S-7 persists exactly that set;
  nothing later adds a new way to reach a completed turn.
- **Telemetry and activity impact:** three separable facts, because collapsing them is what makes a
  cancelled turn look like a crashed one. First, receipt of the cancellation request on the
  signalling endpoint, correlated to the target `turn_id` even though it arrives on a different
  request than the turn owns, including the case where the target turn is not active. Second,
  observation of the signal at a named safe boundary, with which boundary observed it and how long
  after receipt. Third, the terminal cancellation outcome, the evidence-admitted decision that chose
  partial over inconclusive, and the commit result, so the persistence matrix row that was taken is
  readable from telemetry. The materiality decision on the source-failure path and the stop reason
  are recorded alongside. Cancellation is a normal outcome and is categorized as one, never as an
  error status.
- **Deterministic tests:** the cancellation-request signal reaches a running turn from a separate
  request and is distinguishable from a disconnect in the resulting outcome; every row of the
  matrix above; disconnect discards and commits nothing; no fabricated evidence in a degraded
  result; the exact outcome vocabulary.
- **Evaluation increment:** cancellation outcomes are added to the conformance aggregation so that
  a wrong outcome class is caught by evaluation as well as by tests.
- **Dataset or fixture work:** a source-failure fixture for the degradation path.
- **Azure impact:** Local deterministic. No infrastructure change.
- **Decision gates:** none.
- **Explicit non-goals:** no persistence of active-turn state, no reattachment, no resumption of a
  cancelled turn.
- **Small PR breakdown:** (1) the explicit cancellation-request signal and its endpoint, consumed
  by nothing yet; (2) safe-boundary cancellation in the controller, reading that signal, plus
  disconnect and materiality-gated degradation contracts; (3) the persistence matrix and its tests.
- **Completion evidence:** early-cancel and late-cancel demonstrations in the same one-screen UI,
  each with the committed record inspected afterwards, plus one demonstration that cancellation and
  a bare disconnect produce different recorded outcomes. The two are also distinguishable in
  telemetry: cancellation shows receipt, a named safe boundary, and a commit; disconnect shows
  neither a cancellation receipt nor a commit.
### S-7 Durable completed-turn record and restart-safe reads

- **Demonstrable outcome:** completed turns are persisted in Cosmos and, after a container restart,
  a completed turn is read back and every citation still resolves.
- **Entry criteria:** S-6 outcome and cancellation semantics are stable, so the set of turns that
  must be committed is fixed; a fresh `investigations` container partitioned by
  `/investigation_id` already exists and holds nothing, so this slice writes the accepted artifact
  into current infrastructure rather than migrating onto it. There is nothing to reuse, migrate, or
  delete, and no compatibility question to answer first.
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
  restart-safe read and citation resolution; the minimal retry the single-writer path requires; the Container App
  managed identity's write-role assignment on the `investigations` container, scoped to that
  container alone. This is the opposite posture from S-9's
  and S-10's corpus containers, where the same identity is deliberately read-only, and it is settled
  here rather than left for A-1 to discover: the deployed app cannot write a completed turn without
  it, so the role assignment is part of this slice's own Bicep work, not a later cleanup task.
- **Contract introduced or stabilized:** Investigation Record storage layout and restart-safe
  resolution. The port and its commit semantics were stabilized at S-2, and the completed-turn
  artifact and terminal ordering at S-3; none of them is reopened here.
  **Who builds on each:** S-8 reads and resolves citations against exactly this storage layout when
  it answers a follow-up or handoff from retained state; A-1 verifies the write-role assignment and
  the container this slice chose, rather than inventing or granting it for the first time.
- **Telemetry and activity impact:** the commit span gains the facts that make a hosted persistence
  failure diagnosable without a local repro: the commit attempt and its result as separate facts, so
  an attempt that never returned is distinguishable from one that failed; backend identity, so an
  in-memory run is never mistaken for a durable one; the container and partition key written to;
  each retry with its attempt number and outcome; and a sanitized Cosmos access-failure category
  separating authorization refusal, throttling, timeout, and not-found from each other and from a
  contract or serialization failure. Never the artifact body, the account key, or the connection
  string. The activity projection continues to show only that persistence succeeded or failed.
- **Deterministic tests:** one port contract suite run against the in-memory backend and against a
  fake or stub implementing the Cosmos port, so both satisfy one contract offline: commit ordering,
  persistence-failure behavior, nothing persisted for a disconnect, and resolver semantics after a
  simulated restart. Nothing in this lane touches a real Cosmos account.
- **Azure-assisted integration, deliberately not called deterministic:** a separate, separately
  named lane that verifies actual partition-key and indexing compatibility, writes and reads a real
  artifact, restarts the application process, and resolves citations against the live account. It
  is environment-dependent, is never a CI gate, and records the command and the resource used. No
  local Cosmos emulator has been available in this project, so this lane runs against a real
  account or not at all.
- **Evaluation increment:** none. Persistence is proven by tests and by the hosted check in A-1.
- **Dataset or fixture work:** none.
- **Azure impact:** Azure-assisted local required for the integration tests. This slice is
  additive: it writes into an existing empty container and deletes nothing. The interim smoke must
  still pass afterwards.
- **Decision gates:** none.
- **Explicit non-goals:** no follow-up, handoff, redirect, or supplied context, which are S-8; no
  checkpointing, reattachment, recovery scanning, or activity persistence; no unapproved container
  deletion.
- **Small PR breakdown:** (1) Cosmos backend behind the existing port, including the write-role
  assignment, with the shared contract suite run against the stub; (2) restart-safe read and
  citation resolution, with the Azure-assisted integration lane.
- **Completion evidence:** the port contract suite green against both offline backends, and one
  recorded Azure-assisted run in which a completed turn is written to Cosmos, the app restarted,
  and the same turn read back with resolving citations. The offline suite also asserts that each
  Cosmos access-failure category above reaches the commit span distinctly, driven from the stub
  rather than by revoking a live role assignment.
### S-8 Retained-state interactions: follow-up, handoff, redirect, and supplied context

- **Demonstrable outcome:** a follow-up question is answered from retained state without new
  evidence; a handoff summary is produced with no model call; a redirect and a supplied-context
  submission each seed a new investigative turn.
- **Entry criteria:** S-7 durable records exist and read back after restart, so retained state is
  real rather than in-process.
- **Existing foundation retained:** the `InteractionKind` type, whose shape is fixed and not
  reopened here; the S-5 task-labelled model-access seam, which gains the follow-up label this
  slice was the one deferred to add (`decisions.md` D-002 already fixed its deployment); the S-7
  record and its resolver; the S-2 brief projection, which handoff reuses as a projection rather
  than re-rendering.
- **Code and data to delete:** none.
- **Code to replace:** none.
- **New implementation:** the request-shape classifier, producing a value of the existing
  `InteractionKind` type from request shape or explicit UI action; the follow-up
  task on the primary deployment through the Supervisor; the retained-state validation rules;
  deterministic handoff projection; redirect and supplied-context seeding; the read endpoint.
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
- **Forward compatibility with S-9, which follows this slice:** knowledge references do not exist
  yet, so "retained evidence references" here means only the operational evidence references S-2
  fixed. Retained-state validation reads references generically, by the S-2 parser and resolver,
  not by an operational-only shape hard-coded into this slice. When S-9 extends that same parser
  and resolver to knowledge references, a retained knowledge reference becomes readable through the
  identical validation path with no reshaping of this slice's interaction semantics. If that
  genuinely cannot hold, S-9 owns the fix, not a return trip through this slice.
- **Contract introduced or stabilized:** follow-up, handoff, redirect, and supplied-context
  semantics.
- **Telemetry and activity impact:** the classified interaction kind and what determined it, request
  shape or explicit UI action, so a misrouted interaction is diagnosable without guessing; which of
  the four retained-state paths was taken; the identity of the prior turn the retained state came
  from, which is the only correlation link between two turns of one investigation and is what makes
  a follow-up traceable back to the turn it answers from; the retained-state validation result and,
  on refusal, which constraint refused it; and the fact that handoff made no model call, recorded
  positively rather than inferred from an absent span.
- **Deterministic tests:** the classifier maps each of the five request shapes to the correct
  `InteractionKind` value, with an ambiguous ordinary follow-up defaulting to a question; each
  constraint above as its own test; a follow-up that would require new evidence is refused with the
  new-turn recommendation; handoff output is byte-identical for identical retained state; redirect
  and supplied context create new turns rather than mutating the prior one.
- **Evaluation increment:** follow-up and handoff conformance added to the aggregation; both
  results are S-13 report inputs, not reimplemented there.
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
- **Small PR breakdown:** (1) the request-shape classifier, the follow-up task, and retained-state
  validation; (2) deterministic handoff and the read endpoint; (3) redirect and supplied-context
  seeding.
- **Completion evidence:** complete a turn, restart, ask a follow-up answered under replay, be
  refused on an out-of-scope follow-up, and request a handoff that makes no model call. The
  follow-up cassette is committed and its manifest validates.
### S-9 Retrieval, deterministic reranking, and demonstrated retrieval influence

- **Demonstrable outcome:** categorized knowledge materially influences a live investigation using
  semantic retrieval, lexical retrieval, reciprocal-rank fusion, deterministic identifier and
  metadata promotion, then passage-budget truncation. The feed shows used knowledge and the next
  proposal's informing references.
- **Course concepts:** RAG and hybrid retrieval.
- **Entry criteria:** S-5 authorization is stable. The demonstration-data repair this slice once
  had to perform is already in the corpus: the cross-incident log leak is gone, the deployment-note
  causal and red-herring annotations are removed, the inc-003 and inc-007 throughput contradiction
  is repaired, and the recurrence-chain timing follows its causal log. `inc-007` is usable as
  authored and needs no fixture variant. The knowledge metadata shape is **not** an entry
  criterion, because no earlier slice owns it; it is this slice's first decision, below.
- **First decision, taken inside this slice:** establish and record the minimal knowledge metadata
  contract that retrieval and admission actually require, then begin the vector and retrieval
  implementation. Today `kind` maps cleanly onto the three logical collections but no category or
  date metadata field exists, and no authoritative document fixes one. Keep the contract minimal:
  the identifier, the category the container filters on, the date the promotion rule needs, and the
  provenance admission records. Anything beyond that waits for a demand.
- **Existing foundation retained:** the BM25 scorer (`rank-bm25`), section-level chunking, the RRF
  implementation, KB identifiers and recurrence signatures, and the S-2 reference parser, which is
  extended rather than duplicated.
- **Code and data to delete:** `retrieval/embeddings.py` and the sentence-transformers stack,
  `retrieval/reranker.py` and the CrossEncoder path, `retrieval/index.py` and the local
  transformer vector-index stack, the unreachable rerank factory mode, the `reranker` test marker
  and its tests, `RERANK_CANDIDATES`, and the divergent `bge-*` configuration. `data/profiles/`
  is retained: `rcaeval_profile.json` is a live input to corpus regeneration, so it is not part of
  this deletion set and S-12 does not archive it.
- **Code to replace:** the retrieval factory and adapter mapping, superseded by the D-003 stack;
  the pointer-only hit shape, superseded by passage-bearing results, since an agent cannot reason
  over a pointer.
- **New implementation:** the categorized `knowledge` container and its seed script; Azure OpenAI
  embeddings; Cosmos vector query; lexical scoring; RRF; deterministic identifier and metadata
  promotion; passage-budget truncation; knowledge admission; and informing references on proposals.
  The dense-retrieval stack is settled and verified against a live vector-capable container, so
  this slice implements it rather than spiking it.
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
  **Who builds on each:** S-12's further-evidence cycle reasons over the informing references this
  slice starts carrying into proposals, so a further-evidence demonstration can cite retrieved
  knowledge rather than only operational evidence; S-13 aggregates the lexical-only baseline and
  the retrieval-influence measurement recorded here as report inputs, not new measurements; A-1
  verifies the read-only posture and the seeded `knowledge` container this slice creates, rather
  than inventing either; A-2's retrieval-influence demonstration journey runs against exactly the
  repaired scenario this slice's completion evidence names.
- **Telemetry and activity impact:** retrieval is the slice with the most ways to fail quietly, so
  its spans carry each stage separately rather than one retrieval result:
  - the retrieval query executed, by its structured parameters and category filter, never as raw
    passage text;
  - the lexical and vector legs as separate facts, each with its own candidate count, duration, and
    outcome, so a leg that returned nothing is distinguishable from a leg that failed and from a
    leg that never ran;
  - the fusion result and the deterministic identifier and metadata promotion decisions, including
    what was promoted above its fused position, which is the check that proves the promotion stage
    did not silently disappear;
  - the passage budget applied and what truncation dropped;
  - retrieval influence: which admitted knowledge references informed the next proposal, carried on
    the proposal span, so influence is a recorded fact rather than a claim made in the report;
  - embedding and vector-query failures as their own sanitized categories, separating an embedding
    deployment failure, a vector-query failure, and an empty-but-successful result, since all three
    otherwise present as an investigation that simply found no knowledge.
  The backend identity attribute is set here, so a run against fixtures is never mistaken for a run
  against the live `knowledge` container.
- **Deterministic tests:** identifier promotion above fused position; passage budget; category
  filtering; knowledge-reference closure through the single parser; retrieval floor fixtures.
- **Evaluation increment:** the lexical-only retrieval baseline and the retrieval-influence
  measurement, both recorded and advisory.
- **Dataset or fixture work:** the minimum repair set above through the corpus repair protocol;
  category and date metadata added to KB frontmatter; retrieval fixtures regenerated.
- **Azure impact:** Azure-assisted local required. The embedding deployment and the `knowledge`
  container are added additively; no replica, authentication, or deletion change.
- **Decision gates:** the minimal knowledge metadata contract is recorded in the first PR, before
  implementation, and written into the owning document per operating rule 10. D-006 already names
  `inc-007` for retrieval influence; this slice demonstrates that selection rather than making it.
  Vector viability is already settled and is consumed here, not re-established.
- **Explicit non-goals:** no structured query, no further-evidence cycle, no full corpus repair,
  which is S-12.
- **Small PR breakdown:** (1) the minimal knowledge metadata contract, recorded and applied to KB
  frontmatter; (2) retrieval, fusion, and deterministic promotion over the seeded container; (3)
  informing references, feed integration, and the lexical baseline.
- **Completion evidence:** `inc-007` shows a
  different investigation action because of retrieved knowledge, with the informing reference
  visible in the feed and the same influence readable from the run's spans, the promotion decision
  included.

#### Checkpoint after S-9

Required: the cross-encoder reranker, the local embedding/vector-index stack, and their dependencies
(`sentence-transformers`, `torch`) are removed from `src/` and `pyproject.toml`; the accepted stack
(Azure OpenAI embeddings, one embedding configuration owner) is the only one configured; deterministic
identifier-promotion and passage-carrying retrieval tests pass; and the demonstration corpus is free
of answer leakage. One targeted search proves the rejected model reranker actually left the tree,
looking for the implementation rather than the word `rerank`, which the accepted deterministic
promotion code may legitimately use: `git grep -n -e CrossEncoder -e RERANK_CANDIDATES -- src tests eval`
is empty, and `git ls-files src/opspilot/retrieval/reranker.py` is empty.

### S-10 Governed structured query

**Its construction has already landed, ahead of this slice.** The governed query structure, its
deterministic validator, its translation to one parameterized read-only Cosmos query, and its
execution are implemented (`data/structured_query.py`, `tools/structured_query.py`), verified
against the live `operational-records` container across six cases, and covered by
`tests/test_structured_query.py`. The approved surface (`incidents`, `deployments`, `alerts`), the
container and its seed, and the read-only application/setup-identity posture are also already in
place; see `status.md`. What remains below is not new construction: it is wiring this capability
into a live authorized turn once S-5's agent proposal/authorization exists, and the
evaluation-conformance entry once S-3's aggregation exists. Neither dependency is this slice's own
to build; this slice only consumes each once its owner lands.

- **Demonstrable outcome:** the Investigator proposes, and is authorized to run, lookup, filter, and
  COUNT over the approved operational-records surface, with provenance; unsupported or mutating
  output fails structured decoding or validation before source execution and appears as a
  limitation.
- **Course concept:** reliable agentic data reasoning through a bounded canonical structure rather
  than arbitrary SQL.
- **Entry criteria:** S-5's proposal and authorization contract is stable, since a query becomes an
  authorized evidence action only through it; the query engine, the approved surface, the container,
  and the read-only setup-identity posture are already implemented and verified (above), so this
  slice starts with nothing left to build in them.
- **Existing foundation retained:** the capability result envelope and admission from S-2; the
  already-implemented query contract, validator, and execution from `data/structured_query.py` and
  `tools/structured_query.py`.
- **Code and data to delete:** none.
- **Code to replace:** none.
- **New implementation:** the Investigator's proposal of a structured-query action as one authorized
  evidence action, through the S-5 proposal/authorization contract; nothing in the query engine
  itself changes.
- **Contract introduced or stabilized:** none new; this slice consumes the already-stable
  governed-query structure. A-1 verifies the `operational-records` container and its read-only
  application access, rather than creating either; A-2's demonstration journey runs against exactly
  the approved surface and refusal case this slice's completion evidence names.
- **Telemetry and activity impact:** already emitted by the landed capability: acceptance or
  rejection as an explicit fact, naming whether a rejection failed structured decoding or validation
  and which rule refused it; the approved surface, scope, limit, and timeout applied; the execution
  outcome and completeness with row count and provenance; a sanitized failure category on error. This
  slice adds only the proposal and authorization facts around the call, matching every other
  Investigator-proposed action.
- **Deterministic tests:** already exist for lookup, filter, COUNT, rejection, and scope/limit/timeout
  enforcement (`tests/test_structured_query.py`). This slice adds authorization-path tests: a
  structured-query proposal refused when authorization fails, and one accepted end to end through
  the Investigator.
- **Evaluation increment:** structured-query conformance added to the aggregation once S-3's
  aggregation entry point exists, including one recorded refusal; an S-13 report input, not
  reimplemented there.
- **Explicit non-goals:** no arbitrary SQL, no aggregation beyond COUNT, no write path, no second
  approved surface, no change to the query engine itself.
- **Small PR breakdown:** (1) the Investigator's structured-query proposal and its authorization
  tests; (2) the evaluation-conformance entry, once S-3's aggregation exists.
- **Completion evidence:** one accepted question answered with provenance and one visibly rejected
  question surfaced as a limitation, both reached through a live authorized turn rather than a
  direct capability call.

### S-11 MCP parity and the single accepted exposure

- **Demonstrable outcome:** deployment-and-change-history is accessible through direct and MCP
  transports with identical canonical results and provenance; the feed reveals transport without
  changing semantics.
- **Course concept:** MCP as a real protocol boundary, not decorative infrastructure.
- **Entry criteria:** the D-004 library inspection is complete and recorded before implementation
  starts. In-process hosting inside the single application and process is frozen and is not part of
  the inspection; D-004 settles library mechanics, session and transport handling, and result
  carriage only. The existing server already demonstrates in-process execution, same-service
  delegation, and canonical envelope passthrough.
- **Existing foundation retained:** parity by delegation to the same `ToolService.call()` and the
  S-2 canonical two-axis result envelope, unchanged here; the same validation and sanitized errors;
  the parity test pattern; the activity and telemetry projection seams from S-1, which the new
  transport tag rides on rather than a second emission path.
- **Code and data to delete:** all three current MCP exposures, `get_incident`, `query_logs`, and
  `search_runbooks`. None of them is the accepted capability, so the correct action is to remove
  every existing registration rather than to narrow the set. The underlying direct capabilities are
  untouched and remain available through the Evidence Access Layer.
- **Code to replace:** the exposed surface of `mcp/server.py`, superseded by exactly one exposure.
- **New implementation:** one MCP exposure for deployment and change history over the same
  implementation and the same canonical result model; the transport tag in activity and telemetry;
  registration enforcement so an unregistered capability cannot be reached.
- **Contract introduced or stabilized:** MCP parity contract: exactly one MCP exposure, held to the
  same canonical result and provenance as the direct path. **Who builds on each:** A-2's
  direct-versus-MCP demonstration journey runs against exactly this one exposure; nothing later
  adds a second one.
- **Telemetry and activity impact:** the transport attribute S-2 minted now actually varies, so
  `direct` and `mcp` are distinguishable on the capability span for the one shared implementation.
  MCP operation spans, which do not exist today, cover invocation and result under the same
  correlation attributes, so an MCP call is traceable to its turn like any other operation.
  Failures separate into three sanitized categories that would otherwise be one: an MCP invocation
  failure at the transport, a result-carriage or deserialization failure, and a parity divergence
  where the two transports returned different canonical results. Registration refusal of an
  unregistered capability is its own fact, not a generic error.
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
  produces the same canonical result and provenance, and the two runs are distinguishable only by
  the transport attribute on their spans.
### S-12 Corpus reconciliation and the further-evidence cycle

- **Demonstrable outcome:** `inc-004` naturally triggers one authorized further-evidence cycle,
  changes the assessment of the deploy red herring, and completes after the single back-edge. The
  seven authored incidents and their named controlled variants credibly cover the accepted
  evaluation classes.
- **Entry criteria:** retrieval works end to end from S-9, and corpus chronology and leakage checks
  exist as automated gates rather than manual review.
- **Existing foundation retained:** the authored corpus, its answer key, and its closure gates; the
  S-4 explicit turn controller, which the back-edge runs inside rather than a second control
  structure; the S-5 authorization conditions and the further-evidence-cycle flag S-5 already
  mints, both reused rather than duplicated; S-9 retrieval and the informing references it carries
  into a proposal, which is what the further-evidence proposal reasons over; the S-3 terminal
  lifecycle, grounding gate, correction allowance, outcome vocabulary, and commit ordering, all of
  which the final re-synthesis after the back-edge runs through unchanged rather than a shortened
  path.
- **Scope guard:** keep exactly seven authored incidents across five families. Do not add an eighth
  or ninth incident in this plan.
- **Code and data to delete:** the provenance sources that `provenance.md` does not support.
  `data/profiles/` is retained as a live corpus-generation input and is not deleted here.
- **Code to replace:** the affected generator inputs, per the corpus repair protocol; goldens
  regenerated rather than hand-edited.
- **New implementation, and nothing beyond it:** the further-evidence proposal; authorization
  against the four accepted conditions, enforced against the one-cycle flag S-5 already minted
  rather than a newly built one; exactly one back-edge; the final synthesis pass after it, which
  completes the turn through the existing S-3 terminal lifecycle rather than a second one; the
  remaining corpus and evaluation assignments below. No second controller, second authorization
  mechanism, second correction allowance, or new loop framework is introduced here.
- **Contract introduced or stabilized:** evaluation scenario and fixture assignments, written into
  the evaluation artifact home settled in S-2.
- **Telemetry and activity impact:** the further-evidence proposal, its authorization decision
  naming which of the four conditions decided it, the one-cycle flag state before and after, and the
  back-edge itself as a stage transition, so a turn that took the back-edge is distinguishable from
  one that ran long. A refusal to authorize a second cycle is recorded as a normal bound stop, not
  an error. The corpus half of this slice adds no runtime telemetry: corpus gates report through the
  test suite, and evaluation artifacts do not become runtime telemetry.
- **Deterministic tests:** the one-cycle bound; each authorization condition; seven-incident and
  five-family counts; closure; chronology; leakage; and the scenario-versus-variant distinction.
- **Evaluation increment:** the repeatability subset D-006 already names (`inc-005`, `inc-004`,
  `inc-006`) is wired and runnable here. It is a direct S-13 input: S-13 assembles its report from
  it rather than re-deriving the subset.
- **Dataset or fixture work:** repair templated noise realism, which is the last outstanding
  corpus defect: 905 identical error strings and no pre-incident baseline history. Mechanism-implied
  telemetry, effect-before-cause orderings, postmortem timelines, stale data documentation, the
  multi-contributor revision of inc-006, and the benign non-incident fixture are already in the
  corpus and are consumed here rather than performed. Execute any change through the corpus repair
  protocol.
- **Small PR breakdown:** (1) templated-noise repair and regenerated goldens; (2) the
  further-evidence mechanism and its authorization tests; (3) the repeatability subset wiring.
- **Completion evidence:** a live back-edge on inc-004, and the corpus audit passing without
  expanding the authored incident count.

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
  authentication, and telemetry; the S-7 `investigations` container and its write-role assignment;
  the S-9 `knowledge` container, embedding deployment, and read-only application access; the S-10
  `operational-records` container under the same read-only posture; the model-import trick and the
  az-CLI restart technique from the old smoke script, reused for the citations-resolve-after-restart
  check. This slice verifies each of these; it does not create any of them for the first time.
- **Code and data to delete:** performed only after the verification in each case: the interim
  smoke installed in S-4, and any orphaned resource confirmed with the owner, only with explicit
  approval. No rejected-architecture container remains to delete; the live resource set is already
  the accepted one.
- **Code to replace:** `scripts/smoke_deployment.py`, superseded by the eight accepted checks.
- **New implementation:** the eight-check hosted smoke: start, authentication, model reachability,
  Cosmos role access, one streamed turn, citations resolving after restart, telemetry arrival, and
  Bicep repeatability. Bicep converges on exactly the accepted resource set.
- **Check 7 is diagnosability, not arrival.** `runtime-and-deployment.md` §16 states check 7 as
  "telemetry reconstructs one turn", and "some telemetry exists" does not satisfy that. This slice
  implements it as two verifications, both against the live component:
  1. **Locate a known turn by correlation.** Take the `investigation_id` and `turn_id` the smoke's
     own streamed turn returned, query Application Insights for them, and assert that the trail
     contains the startup record for the running revision, the request and turn, each stage, the
     model call, each capability call, retrieval and MCP where the turn used them, the grounding
     result, the commit, and the terminal outcome. Filtering is on fields; a check that passes by
     matching message text does not count.
  2. **Prove a failure path is legible.** Drive one deterministic, reversible failure and assert
     that its sanitized telemetry identifies where it failed, what category of operation failed, the
     correlation identity it belonged to, and a non-secret reason. Use a safe mechanism: a request
     that fails validation deterministically, a capability deliberately configured as unavailable
     for the check, or the application's own configuration-refusal path exercised against a
     throwaway local start. Do not revoke a role assignment, delete a container, corrupt a
     deployment, or otherwise break a production-like Azure resource to produce the failure.
  If either verification cannot be satisfied, the missing emission point belongs to the slice that
  owns the behavior, and that is a defect in that slice rather than new work invented here.
- **Contract introduced or stabilized:** none. This slice makes live state match contracts already
  stabilized.
- **Telemetry and activity impact:** no new emission point, and any that proves to be needed is
  raised against its owning slice rather than added here. What is new is verification: A-0 proved
  telemetry arrives with correlation intact, and this slice proves the arrived telemetry is
  sufficient to diagnose both a healthy turn and a failing one.
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
  smoke replacing the interim smoke; (3)
  separately approved orphan cleanup, if any orphan remains.
- **Completion evidence:** hosted streamed turn, persisted artifact, citations resolving after
  restart, and a repeated deployment that converges. For telemetry, the concrete artifact is the two
  recorded queries themselves, with their text and their returned trails: one that reconstructs a
  named healthy turn from its `investigation_id` or `turn_id`, and one that locates the deliberate
  failure and shows its stage, operation category, correlation identity, and sanitized reason.
  Someone handed only those two queries and the deployment must be able to repeat the diagnosis
  without further explanation, which is the whole point of the exercise.
#### Checkpoint after A-1

Live state is proven by query, not by reading Bicep.

| Check | Proof |
| --- | --- |
| Only three target containers remain | `az cosmosdb sql container list -g rg-opspilot -a <account> -d opspilot --query "[].name"` returns exactly `investigations`, `knowledge`, `operational-records` |
| Three model deployments exist | `az cognitiveservices account deployment list -g rg-opspilot -n <account> --query "[].name"` lists the primary chat, lower-cost chat, and embedding deployments |
| Replicas are still zero to one | `az containerapp show -g rg-opspilot -n opspilot-api --query "properties.template.scale"` shows min 0, max 1 |
| No orphan resources remain unapproved | `az resource list -g rg-opspilot --query "[].name"` matches the Bicep output set, or each difference is explicitly approved |
| Application identity is read-only on corpus containers | The role assignments show the app identity with data-reader scope on `knowledge` and `operational-records`, and no write scope |
| Application identity can write completed turns | The role assignments show the app identity with data-write scope on `investigations` and no other container |
| Hosted smoke is exactly the accepted suite | The smoke script defines eight checks and no assertion references approval, polling, or job status |
| A known turn is reconstructable by correlation | Querying Application Insights on the smoke turn's `turn_id` returns startup, request and turn, stage, model, capability, grounding, commit, and terminal outcome, joined by fields rather than by message text |
| A failure is diagnosable from telemetry alone | The deliberate, reversible failure check yields the stage, the operation category, the correlation identity, and a sanitized reason, and the emitted record contains no secret, token, prompt, or raw payload |
| Deployment evidence joins to application evidence | The workflow run's deployed revision matches the revision named in that revision's startup record, and no GitHub Actions build or deploy output has been copied into Application Insights |
| Deployment is repeatable | `az deployment group what-if` against unchanged parameters reports no create, delete, or modify actions. Optionally follow with a real deployment and confirm that resource IDs and the properties the accepted design names are unchanged. A plain repeat deployment is not proof, because Azure records deployment operations even when effective properties do not change |

### S-13 Evaluation completion and the milestone report

- **Demonstrable outcome:** a milestone report over the seven authored incidents plus explicitly
  named controlled variants: deterministic conformance aggregation, categorical scenario outcomes,
  the D-005 judge, the lexical-only retrieval baseline, the fixed-script evidence-plan baseline,
  the repeatability subset, the retrieval-influence and further-evidence results, and the final
  hosted smoke result.
- **Entry criteria:** D-006 selections are recorded, the corpus gates pass, and A-1 is complete, so
  the evaluation set, its home, and the hosted environment are all final before measurement begins.
- **Existing foundation retained, all of it aggregated here rather than rediscovered:** the golden
  records and the evaluation artifact home from S-2; the grounding and outcome conformance
  aggregation from S-3; the fixed-script baseline fixture from S-5; the cancellation conformance
  from S-6; the follow-up and handoff conformance from S-8; the lexical-only retrieval baseline and
  the retrieval-influence result from S-9; the governed-query conformance and refusal result from
  S-10; the D-006 selections and the repeatability subset from S-12; the final hosted smoke result
  from A-1; cassette and replay machinery as change-time determinism aids. This slice's own job is
  the judge, the baseline comparisons, and report assembly over that spine, not re-measuring any
  item on it.
- **Code and data to delete:** the material parked in S-4, now finally deleted or archived by
  explicit decision: old numeric scorecards, stale rerank claims, and the stub harness. The standalone judge configuration retained since S-0 is removed
  here, replaced by D-005 task routing.
- **Code to replace:** the remaining scorecard vocabulary, superseded by the four accepted layers.
- **New implementation:** the versioned judge rubric, dispatched through the existing S-5
  task-labelled model-access seam on the primary deployment, not a separate runtime model path; the
  expanded fixed-script fixture set and its comparison; categorical result assembly; the report
  generator; and the advisory CI signal, with no thresholds set before the baselines exist.
  Evaluation aggregates deterministic tests and the final hosted smoke; it does not reimplement
  them.
- **Two report modes, because a live judge is not byte-stable:**
  1. **Deterministic report:** generated from committed judge fixtures or cassettes, with the
     hosted-smoke result read from a committed recorded run. Reproducible byte for byte, and the
     mode CI and the checkpoint use.
  2. **Live judge run:** a deliberate run against the real deployment, written to the gitignored
     run directory as a dated, attributable, non-authoritative artifact. Schema-stable, not
     byte-identical, and never the source of a committed comparison.
- **Contract introduced or stabilized:** evaluation result and report model.
- **Telemetry and activity impact:** judge calls carry a task label and usage totals like any other
  model call, and never appear in the live investigation path. Nothing further is added. Evaluation
  results, scores, baselines, and report contents are artifacts, not telemetry, and no runtime
  emission point is created to carry them; a report is diagnosed by reading it, not by querying
  Application Insights.
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
- **Explicit non-goals:** no judge in the live path, no numeric gate thresholds, no merge ratchet,
  no infrastructure change, no revival of the held-out RCAEval probe, which requirements section 12
  defers.
- **Small PR breakdown:** (1) judge rubric and fixtures, with the first rubric version recorded in
  `decisions.md` under the already-accepted D-005 policy; (2) baseline comparisons and the
  repeatability run; (3) report assembly and the two modes; (4) final deletion or archival of the
  S-4 parked material.
- **Completion evidence:** a readable milestone report with named outcomes and limitations,
  regenerated deterministically from committed fixtures, covering the final hosted system.

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
- **Deterministic tests:** feed grouping remains covered by the existing projection fidelity tests.
- **Evaluation increment:** none.
- **Dataset or fixture work:** none.
- **Azure impact:** Hosted verification only; no infrastructure change.
- **Decision gates:** none.
- **Explicit non-goals:** no new capability, no contract change, no corpus change.
- **Demonstration journeys:** predefined investigation, ending in a grounded completed-turn outcome
  with visible three-agent collaboration and model routing in the feed; free-text intake with at
  most one clarification; retrieval influence; governed structured query, including one visible
  refusal; direct versus MCP; follow-up and handoff; early and late cancellation; the
  further-evidence cycle. Governed structured query was missing from this list until this pass;
  S-10 already built the capability, so this adds only the journey, not new implementation.
- **Small PR breakdown:** (1) UI and demonstration polish; (2) final documentation and repository
  hygiene.
- **Completion evidence:** the demonstration script succeeds end to end against the hosted app.

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
- S-10's remaining work depends only on S-5's proposal and authorization contract, since its query
  engine, container, and read-only setup-identity posture have already landed. It is therefore no
  longer ordered behind S-9 and may run any time after S-5. S-11 is independent of both S-9 and S-10
  and may be reordered inside Horizon 2.
- S-12 needs S-9 for the retrieval selection and S-5 for the authorization conditions the
  further-evidence cycle reuses.
- A-1 requires S-7 and S-9, because it verifies and reseeds the containers those slices introduce;
  the `operational-records` container S-10 governs already exists and is verified rather than
  created.
- A-1 precedes S-13 even though its identifier sorts later. S-13's report aggregates the final
  hosted smoke and the final live environment, so assembling it before A-1 would produce a report
  that must be regenerated against a changed environment immediately after its contract was
  stabilized. S-13 also consumes the repeatability subset wired at the end of S-12.
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

This plan's own operating rules are the readiness bar: every slice leaves the tree green, produces
a verifiable outcome, and deletes what it supersedes (operating rules 1-7). The plan has already
executed successfully through S-2, which is the standing evidence that the structure works; a
standalone audit checklist proving the plan is executable is redundant with that evidence and is
not maintained here.

Test disposition for a module a slice deletes or supersedes is stated inside that slice's own
"Code and data to delete" or "Code to replace" field. A global Keep/Port/Delete census of every test
module in the repository is not maintained: it duplicates what each slice already states about its
own subject, and a module no slice has touched yet needs no disposition until a slice reaches it.
