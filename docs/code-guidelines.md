# OpsPilot - Code Guidelines

**What rules bind the implementation to the accepted design, and what must a change meet to merge?**

## 1. Purpose and Document Boundaries

The other documents describe the system. This one binds it. It states the rules a contributor must
follow when implementing any part of the design, and the standard a change must meet to merge.

This document references canonical contracts and never redefines them. Where a rule exists because a
contract says something, the owning document is cited and the contract is not restated. Component
responsibilities belong to `system-design.md`. Stage sequencing, routing, continuation, and outcomes
belong to `workflow-design.md`. Evidence semantics, tool-result vocabulary, citation rules, and the
brief contract belong to `data-and-evidence.md`. Hosting, identity realization, telemetry backends,
and deployment belong to `runtime-and-deployment.md`. Metric definitions and scoring belong to
`evaluation.md`. Requirements and acceptance expectations belong to `requirements.md`.

MUST and MUST NOT are binding: a change that violates one does not merge. SHOULD is a strong default
that may be departed from with a stated reason in the change.

The guiding rule:

> A change is not complete because its happy path works. It must preserve authority boundaries,
> deterministic control, bounded execution, evidence integrity, correlation, and the read-only
> boundary.

Where this document and a design document disagree, the design document defines the intent and this
document defines the implementation obligation. A contributor who finds a genuine conflict raises it
rather than choosing one silently.

## 2. Dependency Direction

The codebase is layered and dependencies point inward, toward contracts and away from adapters.

```text
  contracts and domain rules        depends on nothing in the layers below
            ▲
            │
  components and agent roles        depends on contracts and on seams
            ▲
            │
  adapters and entry points         model access, capability adapters,
                                    persistence, protocol boundary, API surface
```

Rules:

* Contracts and domain rules MUST NOT import an adapter, a client, or a cloud interface.
* Component code MUST reach models, sources, and persistence through the seams and boundaries
  `system-design.md` §3 names, not through concrete adapters. All three agents reach models through
  one shared seam (`system-design.md` §10.1); the Evidence Investigator reaches sources only through
  the Evidence Access Layer (`system-design.md` §3).
* Adapters MUST NOT contain decisions that belong to a component. An adapter does not decide whether
  evidence is sufficient, whether a turn continues, or what a turn's outcome is.
* The call directions in `system-design.md` §3's component table are the permitted ones. Code MUST
  NOT create a call path that table does not allow, and in particular MUST NOT let the RCA Analyst
  reach a capability or the Evidence Investigator reach the engineer.
* Cyclic dependencies between layers MUST NOT be introduced. A cycle usually means a decision leaked
  into an adapter.

Module and package organization beyond this direction is a code concern, not a design one.

## 3. Authority Enforcement

`architecture.md` §5 assigns one authority per concern, and `system-design.md` §4 states what each
component owns and must not do. The implementation MUST make those boundaries structural rather than
conventional: if a component must not do something, the code MUST make it unable to.

| Owner | Code MUST prevent |
| --- | --- |
| Supervisor | Any other component setting the turn objective, authorizing continuation, running the grounding gate, choosing the terminal shape, or writing a completed turn |
| Evidence Investigator | Any other component originating a capability or structured-query request (`system-design.md` §8.2) |
| Evidence Access Layer | Evidence entering turn state by any path other than its admission code (`data-and-evidence.md` §6) |
| RCA Analyst | Any other component authoring, editing, supplementing, or replacing the assessment or the brief's analytical content |
| Investigation Record | Any writer other than the Supervisor, and any write before turn completion (`system-design.md` §9) |

Three consequences are load-bearing and each MUST be enforceable by review or by a test.

**Single synthesis authority is absolute.** Only the RCA Analyst produces the assessment and the
brief's analytical content (`architecture.md` §5). Code MUST NOT synthesize substitute content when
the model's output disappoints, because that would make code a second synthesis authority.

The line falls between semantics and presentation, and `data-and-evidence.md` §15 draws it: the
brief introduces nothing the assessment does not contain and omits, reorders, or alters nothing it
does. Deterministic rendering in the Engineer Interaction Interface stays on the presentation side
of that line.

The implementation rule is that the rendering path MUST be a projection of the assessment. Brief
content MUST be derived from assessment fields by traversal alone, and code MUST NOT construct it by
any route that could add, drop, reorder, or alter what §15 fixes. Re-ranking, filtering,
deduplicating, summarizing, and length-truncating an analytical collection are all such routes and
are prohibited on that path, whatever their intent. Length limits and escaping MAY be applied to
diagnostic and source-detail views, which are not assessment content.

**The grounding gate validates; it does not repair.** The gate is deterministic code holding exactly
the four grounding checks the design defines; the check contract is `data-and-evidence.md` ("Claims,
Citations, and Grounding"), and the sequencing and correction routing are `workflow-design.md`
("Grounding Gate and Outcome Validation"). Code MUST NOT add a fifth check, make the set
configurable, run a model call inside the gate, or let a model influence a check's result. A failed
check spends the turn's one shared correction allowance (§7), and there is no other path; a brief
that still fails, or that fails with the allowance already spent, MUST NOT be delivered, downgraded,
repaired, or persisted: the attempt becomes a failed execution and creates no completed turn. The
gate MUST NOT choose the turn's outcome shape, which belongs to the Supervisor.

**Coordination stays mediated.** Assignments, results, continuation decisions, and synthesis requests
pass through the Supervisor (`architecture.md` §5). Code MUST NOT create a side channel, a shared
mutable conversation, or a path by which one agent selects its own successor.

**The Supervisor separates control from judgment.** Inside the one Supervisor boundary, the
deterministic turn controller (stage sequencing, budgets, continuation and further-evidence
authorization, the grounding gate, and the persistence trigger) MUST be kept separate in code, as
modules or functions, from the Supervisor's model-assisted judgments (objective interpretation and
follow-up answering). This is a code seam only: no fourth agent, no seventh runtime boundary, and no
new deployed component.

## 4. Typed Boundaries

Everything crossing a boundary in `system-design.md` §6 MUST carry a defined type: the normalized
incident context, classified follow-ups, evidence assignments and results, capability requests and
results, admitted evidence, retrieved passages, the assessment, the further-evidence need, the
grounding-gate result, the brief, the handoff summary, activity events, and the completed-turn
artifact.

Rules:

* Inbound data MUST be validated at the boundary it enters, before any decision reads it. That
  applies to engineer input, model output, and source results alike.
* Required and optional fields MUST be explicit. Optional means the system behaves correctly when the
  field is absent, not that it is sometimes forgotten.
* Turn working state and the completed-turn artifact MUST NOT be typed as untyped maps or free-form
  documents. `data-and-evidence.md` §17 defines what a completed turn carries; the type MUST express
  it.
* A value that drives a decision MUST arrive in a structured field. Code MUST NOT parse
  decision-driving state out of prose.
* Completed records must remain intact and readable after the code that wrote them changes
  (NFR-58). This document requires that to be achieved through versioning: persisted types MUST
  carry enough version information for later code to read what earlier code wrote.

**Working state stays separate from user-facing output.** Working hypotheses, the tool-operation
history, drafts, and intermediate reasoning are turn working state (`system-design.md` §5,
`data-and-evidence.md` §5). They MUST be typed separately from the brief and MUST NOT be reachable
from what the engineer is shown except where the design says they are (NFR-11). A working hypothesis
MUST NOT be representable as an admitted observation or as a candidate.

**Investigations stay isolated.** Turn working state MUST be local to the turn that owns it, and no
mutable structure may be shared across investigations running concurrently (NFR-12,
`runtime-and-deployment.md` §1). Isolation MUST be structural, not a convention about keys.

## 5. Model-Output Admission and Deterministic Control

Model output is proposed data until deterministic code admits it (`architecture.md` §5). Before it
can affect anything it MUST be parsed into a typed contract, structurally validated, checked against
the authority of the role that produced it, and admitted by code.

**Structural admission is not a grounding check.** Whether model output parses into a valid structure
is settled before the gate runs (`workflow-design.md` §7). Code MUST keep the two separate: a parse
or contract failure MUST NOT be reported as a grounding-check failure, and the four checks MUST NOT
be used to catch malformed output.

A model MUST NOT be able to mutate, directly or by proposing a value that code applies without
evaluation:

* execution budgets or bounds;
* the turn's live status or terminal outcome;
* admitted evidence or evidence references;
* grounding-gate results;
* the completed-turn artifact;
* capability permissions or the approved schema context.

A model proposing any of the above is making a request, evaluated by the code that owns it (NFR-10).

**Untrusted content is data, never instruction.** Retrieved passages, source results, incident text,
and engineer-supplied context are untrusted (`architecture.md` §5, `data-and-evidence.md` §2, §8).
The separation MUST be structural: untrusted content enters a prompt as clearly delimited data, and
the authority to act on it lives in code the content cannot reach. A prompt instruction to ignore
malicious text MAY be added, but it is not a control and MUST NOT be the only defense.

**Invalid output spends the turn's correction allowance.** A structurally unusable synthesis result
may be corrected only by spending the turn's one correction allowance (§7), and only where that
allowance is unspent. The correction MUST reuse the same budget, MUST NOT add a retry allowance, and
MUST NOT create another gathering or synthesis cycle. Output that remains invalid, or that arrives
with the allowance already spent, degrades the turn under `workflow-design.md` §10; code MUST NOT
patch it into shape by inferring what the model probably meant.

## 6. Capability and Adapter Rules

The Evidence Access Layer is the only path to RetailEase sources (`system-design.md` §8). Its
adapters carry the rules that keep evidence trustworthy.

**The registry is the reachability boundary.** A capability is reachable only by being registered
(`system-design.md` §8.1). Code MUST validate a request against its registry description before
anything executes, and MUST NOT provide a bypass, a raw client, an escape hatch, or a debug path
that reaches a source without passing dispatch. A capability absent from the registry MUST be
unreachable by every path, including the protocol boundary. The registry is implemented as an
explicit static mapping or switch: no dynamic registration, no plugin discovery, and no factory
hierarchy.

**Every capability is read-only.** No adapter may expose a mutating operation under any configuration
(FR-102, NFR-1). The structured-query path MUST validate deterministically before execution, execute
read-only, and carry a result limit and timeout (`system-design.md` §8.2). Read-only is enforced by
the data-plane role assignment as well as by code (`runtime-and-deployment.md`, "Identity, Secrets,
and Network Posture"), so no write
permission exists to guard; code MUST NOT weaken that by holding a broader credential or by
constructing a mutating request that only the source refuses.

**Adapters preserve result distinctions.** `data-and-evidence.md` §4 defines the execution-outcome
and completeness axes and the pairings that are valid. Adapters MUST translate provider-specific
statuses, error codes, and partial-result conventions into that canonical form, and MUST NOT
collapse it to success or failure. Code MUST NOT treat a source that answered with nothing as
equivalent to a source that did not answer, and MUST reject an invalid pairing at the adapter
boundary as a defect in that adapter.

**Nothing provider-shaped escapes the boundary.** A raw exception, stack trace, provider status,
provider syntax, or infrastructure error message MUST NOT reach a prompt, an admitted observation,
an activity event shown to the engineer, or the brief (`data-and-evidence.md` §4,
`system-design.md` §8.2). Adapters sanitize before anything leaves them.

**Admission is the only way in.** Evidence enters turn state through the admission code
(`data-and-evidence.md` §6) and nowhere else. Code MUST NOT construct an admitted observation
directly, MUST NOT admit a result whose execution outcome is not `succeeded`, and MUST record a
limitation for every operation that produced no evidence (FR-68, FR-69, NFR-8). Fabricating a
substitute result when a call fails is prohibited.

**The protocol boundary is a transport, not a second implementation.** The MCP path MUST reach the
same capability implementation, carry the same validation, permission, normalization, provenance,
and admission, and differ only in recorded transport (`system-design.md` §8.3). A capability
reachable through that boundary but not directly, or reachable there with wider permission, is a
defect. Code MUST NOT introduce an MCP-specific evidence concept or result model.

## 7. Bounds, Budgets, and Loops

`workflow-design.md` §5 defines what the bounds are and when they apply. This section states how
code holds them.

**Budgets live in code and are unreachable from a prompt.** Every bound is established by
deterministic code when the turn opens and is stored in turn state no model can write (NFR-10). Code
MUST NOT read a bound, a remaining allowance, or a continuation decision out of model output. An
agent MAY report that further work is or is not useful; it MUST NOT change what it is permitted to
spend, and it MUST NOT extend, reset, or widen its own bounds (FR-56).

**Every loop is bounded by two independent conditions.** Continuation requires a proposal and an
authorization against computable conditions, which `workflow-design.md` §5 defines. Code MUST decide
authorization without re-deriving the judgment behind the proposal, and a construct whose
continuation depends only on model output is prohibited.
This applies to gathering continuation, the one authorized further-evidence cycle, the bounded
correction path, and any transport retry.

**The further-evidence cycle is one edge, not a loop.** At most one may occur per turn, it draws on
the existing budget, it adds no retry allowance, and the synthesis pass that follows cannot request
another (`workflow-design.md` §6). Code MUST make a second cycle structurally impossible within a
turn rather than relying on a counter that a later change might not check.

**The correction allowance is one per turn and shared.** `workflow-design.md` §5 defines the
allowance and which failures consume it. Code MUST hold it as a single piece of turn state that both
correction paths read and spend, so that neither the model-output path nor the grounding-gate path
can grant its own. A failure arriving with the allowance spent MUST NOT be corrected, and nothing
replenishes it: not a further-evidence cycle, not a transport retry, not a later stage.

**Deadlines propagate into operations.** Every model and source operation receives a timeout no
greater than the turn's remaining time, and operations issued together share the turn's remaining
deadline rather than each carrying an independent one
(`runtime-and-deployment.md` §4). Checking a deadline only between stages is insufficient: a single
call that outlives the turn is a bound violation. Where a grouped operation times out, completed
results from that group MUST be preserved rather than discarded with the group.

**Reaching a bound never improves an answer.** Code MUST NOT let bound exhaustion convert
insufficient evidence into a supported conclusion (FR-25), or let it present a best guess as an
established finding (FR-41). What a turn does when a bound is reached belongs to
`workflow-design.md`.

## 8. Error Handling and Failure Legibility

Errors are classified by what they cost the investigation. Generic handling that treats every
failure alike erases the distinctions the design depends on.

| Condition | Obligation |
| --- | --- |
| A source fails, times out, is unavailable, or is refused | Record the canonical outcome and a limitation; admit no evidence (`data-and-evidence.md` §4, §5) |
| Model output is structurally unusable | Spend the turn's correction allowance if unspent, then degrade (§5, §7) |
| A grounding check fails | Spend the turn's correction allowance if unspent; if it still fails or the allowance is gone, a failed execution, never a repaired or downgraded delivery (§3, §7) |
| The turn can still be synthesized, grounded, persisted, and delivered | It completes with the failure disclosed as a limitation; the outcome follows materiality (`runtime-and-deployment.md` §5) |
| It cannot | Controlled execution failure: no completed-turn artifact, visible to the engineer and in telemetry (`runtime-and-deployment.md` §5) |
| Persistence of a completed turn fails | Never report the turn as successfully completed (`runtime-and-deployment.md` §5) |

Three rules follow.

**A failure is never hidden, and materiality decides the outcome.** A source failure MUST always be
recorded and disclosed. It prevents a complete outcome only when it materially limits the turn
objective or the supported assessment; a nonmaterial failure MAY leave the turn complete with the
limitation stated. An initially failed grounding check that passes after the permitted correction
likewise does not prevent a complete outcome. The final admitted turn state determines the outcome.

Persistence is different: code MUST NOT report a turn as completed when its commit failed, and MUST
make it impossible to emit a completed outcome before the persistence operation succeeds.

**Exceptions are not workflow routing.** A stage that reaches a normal alternative outcome MUST
return that outcome. Exceptions are for conditions the code cannot continue past. Outcome shapes are
`workflow-design.md`'s, and code MUST NOT invent one to represent an error.

**Failures name what could not be established.** A limitation MUST identify the question it was meant
to answer, not the provider mechanics that prevented it (`data-and-evidence.md` §5). The provider
detail belongs in telemetry, sanitized, and nowhere else.

## 9. Security Rules

**The read-only boundary.** OpsPilot reaches RetailEase read-only on every path, under every
configuration, including the protocol boundary (`architecture.md` §3, §5). Code MUST hold no
credential and construct no request that could mutate an observed source. The data-plane role
assignment is the enforcement, and code MUST NOT be written in a way that would work if a broader
role were ever granted.

**Credentials.** Credentials MUST NOT appear in source control, committed configuration files,
container images, logs, traces, health responses, completed-turn artifacts, or evaluation artifacts.
Runtime secret injection through the approved local-secret and Container Apps secret mechanisms is
permitted (`runtime-and-deployment.md` §12).

Code MUST read the model-provider key from configuration rather than hardcoding it, and MUST NOT
hold a broader credential than its role requires. The runtime is not secretless, so this obligation
is a live one rather than a formality.

**Caller identity.** Caller authentication is enforced at the entry point
(`runtime-and-deployment.md`, "Identity, Secrets, and Network Posture"). Code MUST NOT treat a
caller-supplied field as establishing who the caller is, and MUST NOT accept an unauthenticated
request by omission.

**Untrusted content.** Incident text, engineer-supplied context, retrieved passages, and source
output are data and never instructions (§5). The authority to act on them lives in code the content
cannot reach.

**Telemetry hygiene.** Secret values and raw source content MUST be filtered before anything is
emitted (`runtime-and-deployment.md`, "Observability"). Telemetry records references and summaries;
it MUST NOT carry full prompts, complete briefs, or raw evidence bodies indiscriminately.

**Startup refuses an unsafe posture.** The application MUST refuse to start with an undefined
authorization posture or an unapproved capability enabled (`runtime-and-deployment.md`,
"Configuration"). A configuration that would weaken a hard boundary MUST fail loudly rather than
degrade quietly.

## 10. Observability Obligations

Every component emits through the one telemetry seam (`system-design.md` §10.3). Instrumentation
built by hand at each call site drifts, and drifted attributes cannot be correlated, so emission
MUST come from shared wrappers at the boundaries rather than from ad hoc calls.

**Correlation context crosses every boundary.** The investigation and turn identity MUST travel with
the work and appear on what each of these emits:

* component dispatch;
* tool and capability execution;
* model access;
* the protocol boundary.

Context MUST be attached where the work enters a boundary, not reassembled by inference at read
time. An operation that cannot be attributed to an investigation and turn is not adequately
instrumented.

What must be reconstructible end to end is stated in `architecture.md` §5 and
`system-design.md` §10.3; telemetry backends, event schemas, and health endpoints belong to
`runtime-and-deployment.md`. Code's obligation is that the seam is used, the context is present, and
errors stay legible and attributable.

**The activity stream is a projection, not a second emitter.** Activity events MUST be produced at
the same instrumentation points as telemetry, from the same recorded facts, carrying the shared
identifiers (`system-design.md`, "Activity projection"). Code MUST NOT emit a stream-only fact that
telemetry does not record, generate activity prose with a model call, or let an event carry prompts,
hidden reasoning, provider-shaped content, or secrets.

**Telemetry is not evidence.** OpsPilot's own telemetry describes OpsPilot. Code MUST NOT make it
reachable as evidence about the incident under investigation.

## 11. Testing Expectations

Core behavior MUST be protected by deterministic tests. Tests that depend on live model behavior are
supplementary and MUST NOT be the only protection for any guarantee, because a guarantee protected
only by sampling is only as stable as the sample.

The obligation is to make silent failure impossible at the points where it would otherwise be
invisible. Each of the following MUST be deterministically testable, and the reason is that a
regression there produces output that still looks correct:

| What must be testable | Why it must be |
| --- | --- |
| Evidence reference resolution | A brief with an unresolvable citation reads exactly like a grounded one |
| The read-only boundary on every path, including the protocol boundary | A widened permission changes nothing visible until something is written |
| Bound enforcement, including deadline propagation into operations | An unbounded run looks like a thorough one until it does not stop |
| Tool-result fidelity through adapters | A source that did not answer, collapsed into one that found nothing, turns an unreachable source into a clean bill of health |
| Grounding-gate outcomes, including which check failed | A gate that silently passes everything is indistinguishable from a strict one on good input |
| Parity between the protocol boundary and the direct path | Divergence appears only in the case the direct path was never exercised |
| Turn isolation across concurrent investigations | Cross-contamination surfaces as a plausible but wrong brief |
| That a turn which never completes leaves nothing persisted | An orphan artifact is only noticed when something later reads it |
| Brief rendering fidelity from the structured assessment | A projection that drops, reorders, or alters assessment content still renders a plausible brief |
| Follow-up answer validation | An answer citing an unretained reference or introducing a new conclusion reads exactly like a valid restatement |
| Activity projection fidelity and sanitization | A stream event that diverges from recorded facts, or carries prompts, hidden reasoning, provider content, or secrets, looks like ordinary activity |
| Structured-query fixture truth and rejection | A wrong normalized result, or an accepted out-of-surface query, still returns something plausible |
| Cancellation with and without admitted evidence | Each path ends in a tidy-looking outcome whether or not the required synthesis and grounding actually ran |
| Commit-before-terminal ordering, including persistence-failure branches | A terminal success emitted before persistence, or after a failed commit, looks identical to a durable one |
| Reranking exact-identifier promotion | Plain truncation still returns passages, so the claimed reranking stage can silently disappear |

Models, capability sources, and persistence MUST be replaceable at their seams so these tests can
run without live dependencies (`system-design.md` §10.1). Prompts and output contracts live behind
the model seam for the same reason.

Hosted deployment verification is defined in `runtime-and-deployment.md` ("Verification Suite") and
is not duplicated here; these deterministic tests own the environment-independent behavior that
suite excludes, and evaluation aggregates both result sets.

Every feature ships with tests for how it refuses or degrades, not only for how it succeeds. A
change that adds a path which can fail MUST cover the failing path.

Test frameworks, file layout, naming, and any coverage figure are not design concerns and are not
prescribed here. Corpus, metrics, baselines, and scoring belong to `evaluation.md`.

## 12. Plan Vocabulary Stays Out of the Repository

**Execution-plan vocabulary MUST NOT appear in the repository or in any change description.** Slice,
stage, phase, layer, gap, and PR-sequence identifiers, and references to a plan document or one of
its sections, MUST NOT appear anywhere in the repository or in any change description. This covers
commit titles and bodies, pull-request titles and bodies, source code, tests, configuration,
infrastructure templates, prompts, log and telemetry strings, identifiers, and API and domain names,
in comments, docstrings, string literals, and names alike.

A change is described by what it does and why that is correct: the behavior it establishes and the
contract it satisfies. Plan position is never a technical justification, and no traceability line
names it.

Requirement, non-functional-requirement, and decision identifiers, and named sections of the design
documents, remain permitted. They resolve in the documentation set and are stable. Plan vocabulary
does not resolve and is not permitted.

```text
Prohibited title:   S-1 PR 2 - Add streaming endpoint
Permitted title:    Add streaming investigation endpoint

Prohibited body:    Implements slice 5.2 of the execution plan. Removes the
                     job record per the plan's deletion register.
Permitted body:      The completed turn becomes the only durable artifact,
                     written once by the Supervisor at turn completion. The
                     job record, its status machine, and its idempotency
                     index are removed with it.

Prohibited comment: # Temporary adapter until S-4
Permitted comment:  # Adapts the legacy report shape while both API
                     # contracts coexist.
```

**The scan obligation is bounded, not repository-wide.** A change MUST NOT perform a repository-wide
sweep for these references. Every file the change already modifies MUST be scanned in full and
cleaned, not only the lines the change touches. A prohibited reference in a comment, docstring, or
string literal is removed and the surrounding text rewritten to state what the code does. A
prohibited reference inside an identifier or a name is reported in the change description rather than
renamed, unless the change already modifies that identifier for its own reasons.

## 13. Merge Standards

A change is complete when it demonstrates the following, and states which items do not apply and
why:

* authority boundaries remain intact, and no component gained a decision it does not own (§3);
* affected typed boundaries are updated, and persisted types remain readable (§4);
* deterministic control still holds: nothing a model proposes is applied without code evaluating it
  (§5);
* bounds remain enforceable and no loop gained an unbounded path (§7);
* the read-only boundary is unchanged, and no credential entered code, configuration, logs, traces,
  or an artifact (§9);
* new operations emit through the telemetry seam with correlation context (§10);
* deterministic tests cover the behavior added, including how it refuses or degrades (§11);
* the design documents are updated where a contract or a decision changed;
* no file the change touches carries prohibited plan vocabulary, the change description carries
  none, and any name-level occurrence found has been reported (§12).

The advisory evaluation signal informs a change; it does not gate the merge
(`runtime-and-deployment.md`, "Build and Deployment").

A change that reports a passing happy path and nothing else has not met this standard.

## 14. Prohibited Patterns

Each has a specific failure mode, and each has a defined alternative earlier in this document.

| Prohibited | Because |
| --- | --- |
| A loop whose continuation depends only on model output | The model extends its own budget |
| Reading a bound, budget, or remaining allowance out of model output | Authority moves out of code |
| A second further-evidence cycle in one turn | A bounded edge becomes an open loop |
| Code editing, stripping, truncating, or supplementing brief content | Code becomes a second synthesis authority |
| Adding, removing, or reconfiguring a grounding check | The gate stops being the fixed set the design relies on |
| Reporting a parse or contract failure as a grounding-check failure | Two different failures become indistinguishable |
| Untyped maps or free-form documents for turn state or the completed artifact | Boundaries stop being checkable |
| Parsing decision-driving state out of prose | State becomes a matter of interpretation |
| Any path to a source that bypasses registry validation | The read-only guarantee becomes conventional |
| Collapsing tool-result axes into success or failure | An unreachable source reads as a clean bill of health |
| Constructing an admitted observation outside admission | Fabricated evidence becomes indistinguishable from observed evidence |
| Fabricating a substitute result when a call fails | The same, with the failure hidden |
| A raw exception, provider status, or infrastructure message reaching a prompt, an observation, or the brief | Unsanitized provider content reaches reasoning |
| A second implementation behind the protocol boundary | The two paths drift and parity stops being checkable |
| Recording a working hypothesis or a model summary as evidence | The evidence set stops meaning "observed" |
| Sharing mutable state across concurrent investigations | Isolation becomes a convention about keys |
| A component writing the Investigation Record, or any write before turn completion | The single-writer guarantee and the no-orphan property both fail |
| Reporting a turn complete when persistence failed | A turn that was never durable looks durable |
| Exceptions as ordinary workflow routing in domain code | Normal outcomes become indistinguishable from defects |
| A credential in code, configuration, logs, traces, health output, or an artifact | Unrecoverable once distributed |
| Live-model tests as the only protection for core behavior | The guarantee is only as stable as the sampling |
