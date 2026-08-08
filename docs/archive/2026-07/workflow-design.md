# OpsPilot — Workflow Design

**Part of the OpsPilot architecture set.** Control flow, the stop/coherence algorithms, subagents, and the human-in-the-loop protocol. The graph state contract itself lives in [`data-and-evidence.md`](./data-and-evidence.md) § 4.

> **Document map & `§N` resolver:** the map in [`architecture.md`](./architecture.md).

---

<a id="sec-5"></a>
## 5. Control flow — nodes, edges & the stop rule

> **Status:** `deployed` — routing, diagnosis loop, coverage gate · `proposed` — every coherence
> check, the verification node, severity revision · gaps: [G-07](./status.md#g-07), [G-09](./status.md#g-09), [G-10](./status.md#g-10), [G-12](./status.md#g-12)

### Nodes

| Node | Type | Responsibility |
|---|---|---|
| `ingest` | entry | Normalize alert event → state; **receive and validate** the API-minted `investigation_id` (it does **not** mint one — R-01); derive `thread_id` from it; dedup on `idempotency_key`. |
| `triage_router` | supervisor | **Scope-pinned**: data extraction (severity/category/affected-services/onset) stays deterministic; only the *classification* — intent + the known-issue **candidate** — is behind the `Triager` seam. `DeterministicTriager` matches an incident only to its own postmortem; `LLMTriager` reasons over surfaced candidates and catches a genuine recurrence (inc-007 → `postmortem:inc-003` — a **KB doc id**, which is cited as `past_incident:inc-003`; the two namespaces are distinct, Appendix D) the self-match misses. |
| `retrieve` | tool-calling | Delegate to retrieval subagents-as-tools, and **place the retrieved passages where the diagnosis loop will read them** — this node's output is knowledge for the model, not just citable refs. |
| `candidate_known_issue` | store read + verify | On a candidate match, **verify current signals** against the stored issue's `required_signals` / `disqualifying_signals` / `affected_versions` before emitting its resolution; on any miss, fall through to full diagnosis. A match score alone is never confirmation. |
| `diagnose` | **agentic, bounded per round** | Behind the `Planner` seam: `DeterministicPlanner` (frozen deploy-regression path) or `LLMPlanner`, which proposes a **batch** of tool calls per round (already-answered/duplicate calls dropped). It maintains *candidate* hypotheses to steer the next batch and **never emits the final conclusion** — see *One reasoning authority* below. Tool results surfaced as `signal [ref]` summaries so the model reasons over *values*, not opaque ids. |
| `contradiction_check` | deterministic detector | Per round, over the accumulated trail: emit the *evidence-level* `Contradiction` set the gate consumes — value-direction only, at this phase. Design below. |
| `gathering_sufficiency` | deterministic gate | Decides whether the agent is *allowed* to stop **gathering** — over evidence and plan state only, never over a conclusion that does not exist yet. Derives `unresolved_critical_questions` from plan bookkeeping (a **coverage** fact, not a contradiction — see below). Also the **severity re-evaluation point**: the bar can rise mid-run. |
| `synthesize_claims` | **LLM — the only conclusion in the run** | Reads the full observation trail and emits the [§4](data-and-evidence.md#sec-4) claim structure: one `CausalClaim`, typed citations with roles, structured caveats. This is the single reasoning authority; every node after it validates or renders, none re-interprets. |
| `coherence_check` | deterministic detector | The *conclusion-level* checks that cannot run before a conclusion exists (causal-order, entity-support, role admissibility). Routes back to re-synthesis or re-gathering on failure, bounded; escalates with the contradiction set. |
| `render_report` | deterministic | Renders every `statement` (root cause **and** each `ReportClaim`) **from** its structured fields into `IncidentReport` + `report_hash`. **Template substitution, not generation** — the prose cannot contradict the structure ([G-50](./status.md#g-50)), and it introduces no claim the coherence gate did not see. |
| `safety_validate` | guardrail | Citation resolution + unsupported-claim + schema + PII checks over **every `ReportClaim`, not just the root cause** — so G2's "every claim is grounded" is enforced, not assumed ([G-51](./status.md#g-51)). Re-run after any human edit. |
| `hitl_gate` | **interrupt** | Pause; await approve / edit / request-more-evidence / reject. The run *ends* here ([§8](workflow-design.md#sec-8)). |
| `apply_edit` | transform | Re-validate a reviewer's edits into a **new** frozen report with a new hash; route back through `safety_validate`. |
| `finalize_report` | output | Emit the approved object — exactly the bytes bound by `approved_report_hash`. |
| `publish` | output | Publish the **preliminary** investigation report. **The investigation graph terminates here** (see below). |
| `escalate` | terminal | Hand to human on reject / breaker trip / unresolved contradictions — always with an explicit machine-readable reason, never silently. |

### One reasoning authority

> **Status:** `proposed` — the built system has **two** authorities: the loop concludes on its
> stopping turn and a report node was scheduled to conclude again · gap: [G-40](./status.md#g-40)

**Exactly one node in the graph decides what caused the incident.** Everything before it gathers;
everything after it validates, formats, or routes. This is a hard structural rule, not a style
preference, because the alternative is silent disagreement between two model calls:

```
diagnose (stopping turn)   →  root cause: the payment gateway timed out
synthesize_report          →  blamed_entity: checkout-api's 14:02 deploy
```

Both are grounded. Both cite real refs. Nothing compares them. The first drove *which evidence was
gathered and when the run stopped*; the second is what the coherence gate checks and the human
approves. The run's stop decision and its published conclusion then rest on different reasoning, and
no artifact records that they diverged — the audit trail says one thing happened.

> **Rule.** `diagnose` may hold **candidate** hypotheses — they are how the planner decides what to
> ask next — but a candidate is scoped to the loop: it steers the next batch, is never cited, never
> reaches the report, and is never what the gate grades. `synthesize_claims` reads the completed
> trail and produces **the** conclusion, once. `render_report` formats it. Neither `coherence_check`,
> `render_report`, nor `safety_validate` may introduce, revise, or reinterpret a claim.

**The rejected alternative was the cheaper one.** Letting `diagnose` produce the final typed
hypothesis and demoting the report node to a renderer also yields a single authority, and it is
closer to what exists today. It was rejected because the loop concludes *while reasoning under a
still-incomplete trail* — its stopping-turn synthesis sees the evidence in arrival order, mid-plan,
with the last batch's observations often the freshest thing in context. A separate node reading the
finished trail is the one place in the run where the whole picture is available at once. The cost is
one extra model call per investigation, funded by the `synthesis_reserve` below.

**The deterministic floor moves with it.** `synthesize_claims` is a *node*, not a model call — it sits
behind the same implementation seam as the planner, so the floor supplies a deterministic synthesizer
(its frozen deploy-regression conclusion, emitted as a `CausalClaim`) while `single_agent` supplies
the LLM one. Both implementations then run the identical graph, which is what keeps the scorecard a
comparison of *reasoning* rather than of two different pipelines — and it keeps the floor's
grounded-but-wrong conclusion (inc-004) in exactly the place the coherence gate can catch it.

**What is built today is the two-authority version** — `run_cycle` synthesizes on the stopping turn,
and Stage 5's LLM report node was scheduled to synthesize again. That is [G-40](./status.md#g-40),
and it is the reason [G-30](./status.md#g-30) (coherence checks running against a placeholder) exists
at all: the placeholder is a symptom of the loop owning a conclusion it should not own.

### Routing

The known-issue path is a **candidate + verification** flow; the stop rule is a **deterministic
gathering gate**, with conclusion validation after synthesis; a human **edit re-enters validation**
rather than shortcutting to finalize.

```python
def route_by_intent(state) -> str:
    if state.intent == "info_only":
        return "service_answer"          # deterministic service Qs only (§10) — not incident claims
    if state.intent == "known_issue" and state.candidate_incident:
        return "candidate_known_issue"   # verify signals before trusting the stored resolution
    return "retrieve"                    # novel → full investigation

def diagnose_continue(state) -> str:
    s = state.sufficiency                # computed deterministically each turn
    # GATHERING sufficiency ONLY. Every conjunct is a fact about the evidence trail or the plan —
    # nothing here inspects a conclusion, because no conclusion exists yet (see the split below).
    gathered = (
        s.evidence_coverage >= s.required_coverage       # severity-scaled (bar may have RISEN)
        and s.independent_observations >= s.required_independent
        and s.unresolved_critical_questions == 0         # a required class the plan could not answer
        and s.evidence_contradictions_unresolved == 0    # value-direction only, over evidence pairs
    )
    # The planner decides when to stop GATHERING (an exhausted plan — the model said `done` or has
    # nothing new to run); code decides whether that stop is LEGITIMATE. The budget is the breaker.
    # While the plan can still advance, keep gathering even once coverage is met — so a dependency-
    # chain investigation can dive into the implicated service rather than stopping at first sufficiency.
    if state.iteration.gathering_exhausted or not s.plan_can_advance:
        # Finalization is FUNDED, not hoped for: the reserve was withheld from the gathering budget,
        # so an exhausted gathering budget can still afford synthesis + coherence + safety.
        return "synthesize_claims" if gathered else "escalate"   # reason = failing dimensions
    return "diagnose"
```

> **The gate is split because the conclusion does not exist yet.** An earlier draft put
> `citation_coverage` and the full contradiction set in this expression — that is circular: it grades
> the citations and coherence of a conclusion the run has not produced, using `run_cycle`'s
> *provisional* hypothesis, which the same section calls a placeholder. Conclusion-level dimensions
> moved to `coherence_check`, after synthesis ([G-41](./status.md#g-41)). What remains here is
> answerable from evidence and plan state alone.
>
> **Three of these four conjuncts have no producer today** — [G-07](./status.md#g-07) for the
> contradiction and critical-question counts, and nothing computes independent observations at all.
> The effective built rule is coverage alone, which by construction cannot fail a grounded-but-wrong
> hypothesis. Read the rest of this section as design, not as enforcement.

### The two gates, and what each may look at

Splitting them is not tidiness — it is what makes each one implementable.

| | **Gathering sufficiency** (before synthesis) | **Conclusion validation** (after synthesis) |
|---|---|---|
| **Question** | Have we gathered enough to reason at all? | Does the conclusion the model reached survive checking? |
| **Inputs** | evidence trail, plan bookkeeping, severity bar, budget | the `CausalClaim`, its citations and their roles, the evidence they resolve to |
| **Checks** | required evidence classes present · required deterministic questions answered · minimum independent observations · plan cannot usefully advance · gathering allocation spent (the reserves are withheld, so finalization is **funded by construction**) | every claim ref resolves to tool-produced evidence · each ref *admissibly* supports its assigned role · causal ordering · entity support · counter-evidence resolved or structurally acknowledged · schema + safety |
| **On failure** | keep gathering, or escalate with the failing dimensions | re-reason → re-gather → escalate, bounded (`after_coherence` below) |
| **Runs in** | `gathering_sufficiency` | `coherence_check`, then `safety_validate` |

**A budget that funds gathering only is a budget that strands runs.** `state.iteration.exhausted`
routing straight into an LLM synthesis call is a contradiction: the run is out of budget and about to
make its most important model call. The `IterationBudget` therefore carries **four reservations** —
`gathering_budget`, `synthesis_reserve`, `coherence_reserve`, `safety_reserve` — and gathering may only
spend the first. `gathering_exhausted` means *the gathering allocation* is gone, not the run: the
reserves are still there precisely so the run can conclude, validate, and stop honestly rather than
escalating for lack of the calls needed to finish.

### Sufficiency: coverage, and why coverage is not enough

Severity scales the bar — SEV1 requires logs + metrics + dependency impact + a recent-change check;
SEV2 requires ≥2 independent evidence classes; SEV3/4 require ≥1 — and per the revision rule below,
that bar can rise mid-run.

But coverage measures *how much* was gathered, never *whether it hangs together*. A well-cited, fully
covered, false conclusion satisfies it. That is precisely the red-herring failure below — and it is
why the second gate exists at all. Coverage can only ever say the run had enough to reason with.

**Contradiction handling.** An earlier draft required `contradictory_evidence_count == 0` to stop —
which means any genuine contradiction can *never* satisfy the gate, so the loop silently burns its
budget and escalates with no explanation. Each gate instead tracks its *unresolved* count —
`evidence_contradictions_unresolved` before synthesis, `coherence.unresolved` after — under one
shared rule: a contradiction is *resolved* when subsequent evidence discriminates between the
readings, or *acknowledged* when **policy or a human** admits it under the rules below.
Contradictions that are neither block progress at whichever gate found them; exhausting the budget
with unresolved contradictions escalates **with the contradiction set attached** as the reason.

### Acknowledgment is admitted, never asserted

> **Status:** `proposed` · gap: [G-44](./status.md#g-44)

`acknowledged` is the one state that lets a contradiction stop blocking, so **whoever controls it
controls the gate.** If the model both writes the caveat and thereby sets the state, the deterministic
stop rule has a one-sentence bypass:

```
"The metrics contradict this conclusion. I acknowledge this contradiction."
→ caveat recorded → contradictions_unresolved = 0 → publish
```

That is model self-certification wearing the shape of rigor — the same failure as a model-assigned
citation role ([G-43](./status.md#g-43)), one level up, and worse in consequence: a role gets a claim
past one check, an acknowledgment gets a *known-contradicted* claim all the way to a human who is
being told the system already handled it.

> **Rule.** The model may **propose** a caveat. Only `coherence_check` (policy) or a verified reviewer
> (human) may set `state = "acknowledged"`, and every acknowledgment records **which rule or which
> principal** admitted it. A caveat whose `acknowledgment` is absent is `unresolved`, whatever the
> prose says.

**Not every kind is admissible.** Acknowledgment means *this tension is real and the conclusion still
stands* — which is only coherent for some contradictions:

| Kind | Policy-admissible? | Why |
|---|---|---|
| `value_direction` | **Yes**, under the preconditions below | Two real observations genuinely disagree. Reporting the disagreement is honest analysis. |
| `causal_order` | **Never** | The effect precedes the cause. Acknowledging it publishes a claim already known to be causally impossible — that is not a caveat, it is a refutation. |
| `entity_support` | **Never** | No evidence supports the blamed entity. Acknowledging it publishes an unsupported conclusion, which is exactly what G2 forbids. |
| `role_inadmissible` | **Never** | A validity error, not a substantive tension. The fix is a correct label, not acceptance. |

**Policy admission has structural preconditions, all code-checked:**

1. **Both sides are cited.** The supporting ref *and* the opposing ref appear in `citations`, and the
   opposing one is listed in `causal.counter_refs`. Counter-evidence is carried in the structure, not
   narrated in a sentence.
2. **The claim is not SEV1.** At SEV1 — including a run **revised up** to SEV1 mid-run ([§5](workflow-design.md#sec-5)) — no
   contradiction is policy-admissible. A human accepts it or the run escalates. An upgrade
   *invalidates* an acknowledgment already granted at a lower bar; the bar rose, so the acceptance
   must be re-earned.
3. **Confidence is capped by code.** An acknowledged caveat caps `confidence` at a configured
   ceiling. The cap is applied to the object, not requested of the model — a model that asserts 0.95
   alongside a live contradiction has its number reduced, and the reduction is recorded.
4. **Disposition degrades.** `disposition` becomes `qualified` (or `inconclusive` where the caveat
   undercuts the causal claim itself). A qualified claim is rendered as such, and downstream — the
   memory-admission gate in particular ([§5](workflow-design.md#sec-5)) — treats it as a weaker artifact than a conclusive RCA.

**Human acceptance is per-contradiction, not per-report.** Approving a whole report is not evidence
that the reviewer saw the tension inside it. The HITL payload carries the contradiction set
explicitly, and the decision names the ids being accepted ([§8](workflow-design.md#sec-8)) — an `approve` that leaves a
human-acceptance-required contradiction unaccepted is **incomplete, not implicit consent**.

**Abuse is a trend, not an event.** A single acknowledgment can be legitimate; a rising rate of them
is a model learning the cheap path. `acknowledgment_rate` is therefore a scored axis per
implementation (§10), and a regression in it fails CI the same way a correctness drop does.

**Who produces a contradiction matters.** The two candidate producers are not equivalent:

- **Model-flagged** contradictions would make a model judgment an input to the stop rule — precisely
  what the deterministic gate exists to avoid. Admissible only as a *hint* a deterministic check then
  confirms, never as the gate input.
- **Code-flagged** contradictions keep the gate deterministic, but require a concrete, falsifiable
  check.

**The detector is deliberately narrow.** It does not need to find every contradiction to earn its
place; it needs to never assert one that isn't there. Every check below is a comparison between
**typed fields** — never a parse of an excerpt, a service name pulled out of a sentence, or a
timestamp inferred from a ref string. That is a hard constraint on [§4](data-and-evidence.md#sec-4): each row's *Needs* column
names structure that must exist before the check can be written at all
([G-42](./status.md#g-42), [G-43](./status.md#g-43)).

| Check | Fires when | Needs | Phase |
|---|---|---|---|
| **Value-direction** | Two `MetricEvidence` facts, same `service` + `metric_name` + `dimensions`, **overlapping `[window_start, window_end)`**, opposite `direction` against `baseline_value` | typed metric facts | **per round** |
| **Causal-order** | The claim's `cause_event_ref` resolves to a `DeploymentEvidence` whose `started_at` is **after** the earliest onset of any `role="effect"` citation. Effect preceded cause. Compared as **intervals**, not points — a deploy that starts before onset and completes after it does not fire. *(Generalizes [G-18](./status.md#g-18) — same check, on the claim rather than the plan.)* | `CausalClaim.cause_event_ref` + deployment intervals + effect onsets | **post-synthesis** |
| **Entity support** | No `role="cause"` citation resolves to a fact scoped to `cause_entity`, or to a dependency edge incident on it that was **valid at onset** (`valid_from ≤ onset < valid_to`) | `CausalClaim.cause_entity` + typed facts + versioned topology | **post-synthesis** |
| **Role admissibility** | Any citation carries a role its evidence type cannot support (table below) | evidence type + asserted role | **post-synthesis** |

Each yields a typed `Contradiction` ([§4](data-and-evidence.md#sec-4)) — and those four are exactly the members of its `kind`
literal — so an escalation carries the *set* rather than a bare count, satisfying the
never-escalate-silently rule (§10).

### Roles are proposed by the model and admitted by code

> **Status:** `proposed` · gap: [G-43](./status.md#g-43)

Typed output is not trustworthy output. Every conclusion-level check keys off `Citation.role`, and
the model assigns it — so a model that would fail causal-order can relabel the inconvenient effect
citation as `context`, or promote a weak observation to `cause`, and pass a gate described as
deterministic. **A deterministic check over a model-controlled input is deterministic in form only.**

The role therefore has two producers, and the second one is code:

| Evidence type | `cause` | `effect` | `baseline` | `context` |
|---|:---:|:---:|:---:|:---:|
| `DeploymentEvidence` | ✅ | — | — | ✅ |
| `MetricEvidence` | — | ✅ *only if* anomalous **and** `window_start ≥ onset` | ✅ *only if* at baseline **and** window **precedes** onset | ✅ |
| `LogEvidence` | ✅ *only if* it carries an error/config signal on `cause_entity` | ✅ *if* post-onset | — | ✅ |
| `DependencyEvidence` | — *(topology is never direct causal proof)* | — | — | ✅ |
| `KnowledgeEvidence` (runbook, past incident) | — | — | — | ✅ |

> **Rule.** The model **proposes** a role; `coherence_check` **admits** it against the typed fact.
> An inadmissible role is a `Contradiction`, not a silent downgrade — relabeling to pass is then
> itself a detectable event rather than a way through. Where the fact determines the role outright
> (a pre-onset metric at baseline *is* a baseline; a post-onset anomaly *is* an effect), code derives
> it and the model's assertion is checked against the derivation, not trusted in place of it.
>
> The residue is honest: `context` is admissible for everything, so a model can always retreat to it.
> That is fine — a `context` citation supports no causal claim, so retreating there costs the model
> the entity-support check instead. The gate is closed by making every escape route lead to a
> different failing check, not by trusting the label.

> **A critical question is not a contradiction.** An evidence class the severity bar requires
> (SEV1's four) that the plan proposed and could not answer is a **gap in coverage**, not two pieces
> of evidence that disagree. It mints no `Contradiction`, has no `resolved`/`acknowledged` semantics,
> and is derivable from plan/answered bookkeeping alone — so it belongs in `gathering_sufficiency`,
> which already reads that bookkeeping, and feeds its own conjunct (`unresolved_critical_questions`).
> Filing it under the detector would put a coverage fact in a coherence structure and make the
> `Contradiction` type mean two things.

> **Three of these cannot run in the diagnosis loop, and this is a real ordering constraint.** They
> interrogate a `CausalClaim`, and under the one-authority rule no claim exists until
> `synthesize_claims` runs. (In the *built* two-authority system they would interrogate `run_cycle`'s
> provisional hypothesis — a placeholder the system already knows is a placeholder, which is
> [G-30](./status.md#g-30) and, underneath it, [G-40](./status.md#g-40).) Coherence checks that
> depend on the conclusion must run **after** the conclusion exists.

**Where each phase runs:**

- **Per round** — after the batch's observations land ([§3](architecture.md#sec-3)), not per action, since batching removed
  that seam. Value-direction only: it compares evidence to evidence and needs no conclusion. It feeds
  `sufficiency.evidence_contradictions_unresolved`, the gathering conjunct.
- **Post-synthesis** — in a dedicated `coherence_check` node between `synthesize_claims` and
  `render_report`, with a **bounded back-edge**:

```python
def after_coherence(state) -> str:
    c = state.coherence                       # contradictions found against the FINAL claim
    if not c.unresolved:                      # resolved or structurally acknowledged (§4 caveats)
        return "render_report"                #    deterministic formatting — no reinterpretation
    if state.resynth_attempts < MAX_RESYNTH:  # 1: re-reason over the SAME evidence, with the
        return "synthesize_claims"            #    contradiction set injected into context
    if state.iteration.can_afford_round():    # 2: the conclusion may be under-evidenced, not wrong
        return "diagnose"                     #    — gather again against the raised question
    return "escalate"                         # 3: with the contradiction set as the reason
```

Both back-edges spend the **coherence reserve**, not the gathering budget — re-reasoning after an
exhausted gathering allocation is exactly the case the reserve exists for. The re-gather leg is the
one exception: it re-enters `diagnose`, so it must be funded like a round, and `can_afford_round()`
is checked against what remains rather than against the reserve.

The ladder is deliberate: **re-reason before re-gathering, re-gather before escalating.** A
contradiction most often means the model drew the wrong conclusion from adequate evidence (cheap to
fix), sometimes that the evidence was genuinely insufficient (expensive), and only then that a human
is needed. `resynth_attempts` is bounded so a model that cannot produce a coherent conclusion
escalates rather than looping, and the re-gather leg is budget-gated like any other round. The counter
is scoped **per evidence-epoch** ([G-60](./status.md#g-60)) — a re-gather that lands new evidence bumps
the epoch and starts a fresh budget, so synthesis over a larger evidence set is not refused because an
earlier synthesis over *less* evidence exhausted the count.

### Severity re-evaluation

Severity is set from the incident record at triage and then **governs the rigor of everything
downstream** — the sufficiency bar, and the model tier once tiering is wired (§11). But the incident
record's `priority` is a *reported* severity; blast radius is **discovered**.
`get_service_dependencies` is in the plan precisely to find it, and the corpus generator itself
computes severity as emergent blast-radius × path-criticality (§11) — so the system already treats
severity as derived everywhere except at runtime.

Without a revision step, a mis-triaged SEV3 that turns out to touch a critical path keeps the
≥1-class bar all the way to publication. That inverts the intent: severity tiering is meant to be an
economy measure on the low-severity tail, but a frozen severity also **caps rigor exactly where a
mistake is most expensive**.

**Reachability is not impact.** The obvious rule — re-derive severity from dependency fan-out ×
criticality of the reached services — is wrong, and wrong in a direction that costs money. A
dependency edge means service X *can* affect Y, not that it *did*. Under a fan-out rule, any incident
on a well-connected service upgrades; combined with monotonic-upward and tier routing, **escalation
becomes the equilibrium** — inverting the economy the tiering exists to create, and handing an
unauthenticated endpoint ([G-03](./status.md#g-03)) a spend-amplification lever. The predicate must be
evidential, not topological.

> **Rule.** Severity is re-derived when **anomalous evidence is observed on a reached critical
> service** — not when a critical service is merely reachable. Concretely: a citable
> `metrics:`/`logs:` ref showing degradation on a service that (a) is on the dependency path from the
> failing service and (b) carries a criticality marker. Topology selects *candidates*; evidence
> triggers the *upgrade*.
>
> Severity may only move **up** mid-run — a downgrade would retroactively excuse evidence already
> judged necessary. An upgrade raises `required_coverage` and `diagnose_continue` re-checks against
> the new bar *on the same turn*, so a run that had just satisfied SEV3 keeps gathering against
> SEV2/SEV1 rather than publishing. The revision is recorded (`severity_revisions`, [§4](data-and-evidence.md#sec-4)) with the
> **evidence refs that triggered it** — which is also what makes the upgrade auditable and, if wrong,
> falsifiable after the fact. It feeds the escalation reason: "insufficient at the *revised* bar" is
> a more informative outcome than "insufficient".

> **The model tier does NOT follow the revision — v1 pins it.** Severity governs two things, and they
> must be decoupled here: the **sufficiency bar** (revisable) and the **model tier** (fixed at the
> first LLM call of the run). Mid-run tier switching would break two properties the project depends
> on: cassette replay keys on the model (part of the cassette manifest, §10), so a mid-run switch
> splits one run across two manifests and makes the recording unreplayable and un-gateable in CI; and
> per-implementation baselines assume one model per run, so a scorecard row would no longer describe a
> single system.
> **Working default: tier fixes at the first LLM call; a severity revision moves the bar only.** This
> is an **open decision, not a settled one** — [§13.2](decisions.md#sec-13) (C) states what would settle it. Nothing selects a
> tier today ([G-21](./status.md#g-21)), so neither position is implemented.

### Memory admission is a separate component, not a second pause

> **Status:** `proposed` — the node is a no-op and no Store exists · gaps: [G-27](./status.md#g-27), [G-33](./status.md#g-33)

The two-phase verified-postmortem lifecycle ([§13](decisions.md#sec-13)) needs a trigger, and the flow in [§3](architecture.md#sec-3) previously
implied the graph itself waits for incident closure. **It does not, and it must not.** Closure arrives
days later, from an external system, and parking a LangGraph thread across that interval breaks three
things at once:

1. **Cosmos TTL** ([§12](deployment.md#sec-12), [§13](decisions.md#sec-13)) would garbage-collect a legitimately-waiting thread. Suppressing TTL for
   these threads means suppressing it for the store that also holds abandoned ones.
2. **The async resource contract** would have no terminal state — an investigation would sit
   non-terminal for days, and a poller could never stop.
3. **Identity** — the writer of verified memory is a *separate privileged identity* ([§12](deployment.md#sec-12)). A component
   that runs inside the investigation graph runs as the investigation's identity, which is precisely
   the separation the anti-poisoning design depends on.

> **Decision.** The investigation graph **terminates at `publish`**. Memory admission is a separate
> **closure-event-driven component**: an incident-closed event (ITSM → Event Grid) triggers
> reconciliation of predicted vs. confirmed RCA, an admission gate, and only then the write + index —
> running under the privileged publisher identity, against the preliminary record the investigation
> left behind. **What that gate is — policy, human, or a split by reconciliation outcome — is open
> decision [§13.2](decisions.md#sec-13) (E).** The *placement* is settled; the *control* is not.

This also makes the anti-poisoning property *testable in isolation*: admission can be exercised
without running an investigation, and an investigation cannot reach the index even in principle.

### The iteration budget is the circuit breaker — and it is partitioned

Calls, tokens, cost, **and** wall-clock deadline — the one mechanism that kills the cost-explosion and
infinite-loop failure modes at the architecture level, enforced in one place. Accounted **per round**
for the reason given in [§3](architecture.md#sec-3). Currently a call count only — [G-08](./status.md#g-08).

**A single pooled budget is a bug, not a simplification.** Gathering is the elastic part of a run:
it will consume whatever it is allowed to. If it may consume everything, then the moment the loop
stops is the moment the run can no longer afford to conclude, validate, or safety-check — and the
budget that exists to make runs terminate cleanly instead makes them terminate *dirty*, escalating
for want of the one call that would have finished the job.

```python
class IterationBudget(BaseModel):
    # Each reservation is a full (calls, tokens, cost, deadline) allocation, not a call count.
    gathering_budget: Allocation      # the ONLY one `diagnose` may spend
    synthesis_reserve: Allocation     # synthesize_claims + bounded re-synthesis
    coherence_reserve: Allocation     # coherence_check and its back-edges
    safety_reserve: Allocation        # safety_validate, and re-validation after a human edit

    # Per-call bounds live here too: a reservation cannot be enforced if one call inside it
    # is unbounded. Every model call carries an explicit timeout and max_tokens.
```

`gathering_exhausted` therefore means *the gathering allocation* is spent, never that the run is
over. The three reserves are sized from observed p95 cost of each phase and are **not fungible** —
lending the coherence reserve to gathering reintroduces exactly the failure the split prevents.
Reserve exhaustion is itself an escalation reason, and a distinct one: "could not afford to validate"
is a different operational problem from "could not find enough evidence".

**Per-call limits are part of this, not separate from it.** Every model call carries an explicit
**timeout** and **`max_tokens`**; the client passes neither today, so a single hung or runaway
generation has no bound short of the HTTP stack's defaults. A budget that counts calls but cannot
bound one call is not a circuit breaker — the wall-clock deadline in particular is unenforceable
without a per-call timeout beneath it.

### Causal discrimination is a loop requirement, not an eval nicety

The answer key contains a deliberate red-herring scenario (inc-004: a coincidental deploy precedes
onset; the true cause is downstream gateway latency). The deterministic floor *fails* it by design —
it asserts the deploy, and the citation guardrail correctly passes it, because the citations are real
and the *conclusion* is wrong.

**Grounding and correctness are separate axes.** `unsupported_evidence_rate` is 0.0 (every citation is
real) while deterministic `rca_correctness` is 0.714 (inc-004 and inc-005 are grounded-but-wrong).
The LLM loop closes the red herring: reading inc-004's payment-api timeout evidence as *values*,
`single_agent` names payment-api / the gateway instead of the deploy. That does not show up in
`rca_correctness` — which ties at 0.714, because inc-004's true root is the **external**
payment-gateway no internal citation can name — but in a dedicated **`red_herring_avoidance`** axis,
where `single_agent` scores 1.0 vs the floor's 0.857.

Measuring both keeps the picture honest: reasoning improves even where the exact-root metric cannot
credit it. It is also the standing demonstration of why coverage alone cannot be the stop rule.

---

<a id="sec-7"></a>
## 7. Subagents & context quarantine

> **Status:** `proposed` — the loop calls tools directly · gaps: [G-25](./status.md#g-25)

The diagnosis node sees retrieval/telemetry tools as single-result functions; their internal calls
never enter the top-level loop. Investigation subagents are **LangGraph subgraphs wrapped as tools** —
the parent receives only the final structured result, keeping the *reasoning context* clean.

> **Promotion is conditional, not a settled default — and quarantine hides noise from the parent, not
> from observability.** Two clarifications the "subagents-as-tools" decision needs:
>
> - **A subgraph is a cost, so it must clear a bar.** Each promotion adds a planning boundary, a prompt,
>   model calls, schemas, failure handling, and an eval surface. [§13.1](decisions.md#sec-13) settles the *topology* (if a
>   gathering step is promoted, it is a subgraph-as-tool, not a handoff); it does **not** license
>   promoting every step. **Rule:** promote a knowledge/telemetry gathering step into a subgraph only
>   when a **declared threshold** is met — measured context reduction, quality improvement, or
>   latency-parallelism gain that exceeds a stated bar on the scorecard. The knowledge subagent's bar is
>   the `knowledge_grounding` axis (§10); a telemetry subagent would need its own. This is open decision
>   [§13.2](decisions.md#sec-13) (B) — the shape is settled, the *trigger* is not, and the default is **not promoted**.
> - **"Clean context" ≠ "hidden from traces."** Quarantine removes a subagent's intermediate tool calls
>   from the *parent model's context window* — it must **not** remove them from observability. Every
>   subagent call still emits a **hierarchical trace** under the parent's `trace_id` (§10) and an audit
>   record; the eval surface sees the parent's structured result *and* can drill into the child. A
>   subgraph that is opaque to tracing is unauditable, which the regulated-ops framing ([§1](architecture.md#sec-1)) forbids.

**The knowledge subagent is the intended home of the retrieval→reasoning fix, but is not a
prerequisite for it.** Two cautions against waiting for the promotion:

1. **The seam change is required either way.** A knowledge subagent that calls `search_runbooks` still
   receives `(doc_id, title, score)` and has nothing to summarize. Widening the retrieval seam ([§6](data-and-evidence.md#sec-6)) is
   a hard prerequisite for the subagent to be worth building, so it is sequenced first and
   independently.
2. **Nothing currently forces it.** No contract, test, or eval axis requires that retrieved knowledge
   influence the hypothesis, so the promotion could land, be measured as "no regression", and still
   deliver zero knowledge into context. The forcing function is the `knowledge_grounding` axis (§10),
   which must exist *before* the refactor — **promotion timing is open decision [§13.2](decisions.md#sec-13) (B)**.

**Context quarantine cuts both ways: the parent must see *less noise*, not *less evidence*.** A
subagent that returns only refs quarantines the reasoning from the knowledge — the current defect
wearing a better architecture.

---

<a id="sec-8"></a>
## 8. Human-in-the-loop protocol

> **Status:** `merged` (5c/#36 — verified reviewer identity, [G-01](./status.md#g-01) closed) ·
> `merged` (5f — durable pause [G-02](./status.md#g-02), and the resume/replay contract:
> decision-id replay, 409-stay on a stale hash, `publication_id` idempotent publish,
> [G-32](./status.md#g-32) + [G-58](./status.md#g-58) closed) · `proposed` — durable dispatch of the
> in-flight leg and `request_more_evidence` (Stage 5f, PR B). · gaps:
> [G-31](./status.md#g-31), [G-34](./status.md#g-34)

**This is a distributed-systems protocol, not a node behavior.** Pause → out-of-band decision →
optimistic-concurrency resume spans three separate requests and, with scale-to-zero, possibly three
process lifetimes. Designing either half alone produces two things that do not compose — a
run-to-terminal background worker and an indefinitely-pausing graph.

```
  POST /investigations ──► 202 {id}          repo: queued → running
        │                                    thread_id := id
        ▼
  graph.invoke(...)  ──► hitl_gate: interrupt(payload)
        │                    run ENDS; checkpoint persisted under thread_id
        ▼
  repo.transition(awaiting_approval, pending_interrupt=payload)      ◄── non-terminal
        │
        │   (process may exit / scale to zero here — both the checkpoint
        │    and the investigation record must survive this line)
        ▼
  GET /investigations/{id} ──► {status: awaiting_approval,
                                pending_decision: {report, report_hash,
                                                   contradictions_requiring_acceptance: [...]}}
        │
        ▼
  POST /investigations/{id}/decision {decision_id, decision, submitted_report_hash,
                                      accepted_contradictions: [id...], edits?}
        │   ONE conditional write commits the decision AND awaiting_approval → running,
        │       and decides every precondition below against the state it commits against
        │   409 decision_conflict  if decision_id was committed with a different body
        │   202 replay            if decision_id was committed with the SAME body (no resume)
        │   409 unless status == awaiting_approval        ◄── validated synchronously
        │   409 stale_report + current hash if submitted_report_hash != the pending one;
        │       run STAYS awaiting_approval               ◄── a conflict, not a failure
        │   422 if approve leaves a required contradiction unaccepted  ◄── not implicit consent
        ▼
  graph.invoke(Command(resume=decision), thread_id=id)
        │   hitl_gate re-executes from the top; code after interrupt() sees the decision
        ▼
  approve → finalize_report ─► terminal        edit → apply_edit → safety_validate → RE-PAUSE
```

```python
from langgraph.types import interrupt

def hitl_gate(state) -> dict:
    # Everything above interrupt() re-runs on resume — it must stay pure (no side effects).
    resume = interrupt({
        "kind": "approval_request",
        "investigation_id": state.investigation_id,   # == thread_id == the polled id
        "report": state.report,
        "report_hash": state.report_hash,             # approval binds to this exact object
        "safety": state.safety,
        # Surfaced EXPLICITLY, never buried in the report body: the tensions the reviewer is
        # being asked to take responsibility for (§5).
        "contradictions_requiring_acceptance": [c.contradiction_id for c in requires_human(state)],
    }) or {}
    # Only code BELOW here sees a human decision. Optimistic concurrency: a decision made
    # against a superseded report is rejected, not applied to a different object.
    # As of 5f/G-32 the stale check lives in the repository's atomic commit, so a stale hash is
    # a 409 that never resumes the graph and leaves the run awaiting_approval — this branch is
    # unreachable from the endpoint. Kept as the fail-closed floor: the alternative to failing
    # here is applying a human decision to a report they did not review.
    if resume.get("submitted_report_hash") != state.report_hash:
        return {"approval": {"decision": "stale_rejected", ...}}   # → escalate (unreachable floor)
    # Approval is not consent to what the reviewer did not name. The ids are inside the hashed
    # report, so acceptance is bound to the same bytes as the approval — no separate mechanism.
    if resume["decision"] == "approve" and not accepts_all_required(resume, state):
        return {"approval": {"decision": "incomplete", ...}}       # → re-pause, not approval
    # decision ∈ {approve, edit, request_more_evidence, reject}; edit re-enters validation.
    # TARGET: `approver` is a verified Entra identity from the request token, not a
    # caller-supplied string (G-01).
    return {"approval": {"decision": resume.get("decision"), ...}}
```

### `request_more_evidence` — the one decision that re-enters the agentic core

> **Status:** `proposed` — the positions below are taken, nothing implements them; today the decision
> falls through `after_approval`'s else-branch to `escalate` · gap: [G-31](./status.md#g-31)

`approve`, `edit`, and `reject` all terminate or loop within the publication half of the graph.
`request_more_evidence` is the only decision that sends control **back into the diagnosis loop**, and
it raises three questions none of the others do:

| Question | Position |
|---|---|
| **Where does resume land?** | `diagnose`, not `ingest` — the evidence trail, answered-question set, and severity revisions all survive; this is a continuation, not a re-run. |
| **What seeds the plan?** | The reviewer's free-text note becomes a **planner hint**, never a tool call. The model proposes the next batch as usual and the read-only registry still adjudicates it — a human asking for evidence must not become a way to drive arbitrary tool calls. |
| **Does the budget continue or reset?** | **Continues, with a bounded one-time extension.** Continuing alone invites instant re-escalation (the budget is why it stopped); resetting is budget laundering — an unlimited-spend path through a human who need not be authenticated ([G-01](./status.md#g-01)). A fixed per-investigation cap on extensions bounds both. |

Each extension is recorded on the approval record with the requesting identity, so "this investigation
cost 4× the others" resolves to *who asked and why*.

### Decision-resume failure semantics

> **Status:** `merged` (#36) — 409-on-wrong-status · `merged` (5f, [G-32](./status.md#g-32) +
> [G-58](./status.md#g-58) closed) — stale-hash is now **409-stay** (a concurrency conflict is not a
> failure), plus the record-with-resume commit, decision-id replay, and `publication_id` idempotent
> publish. All three are described below as built.

The decision leg is a distributed write, and its ordering is a design decision, not an implementation
detail. The rule:

```
1. durably record the decision (with reviewer identity + submitted hash)   ← the commit point
   AND transition awaiting_approval → running, in ONE conditional write
2. resume the graph — MUST be safe to re-invoke
```

**Why this order.** A crash between (1) and (2) leaves a recorded decision and a resumable checkpoint,
so a sweep or the next poll can re-drive it (§ below). The inverse order — resume first, record after —
loses the decision on a crash and strands the run at a pause whose reviewer already walked away.

**Why one write, not two.** The rule was originally stated as record, *then* transition. Building it
(G-32) collapsed the two into a single conditional write — one lock acquisition in-memory, one ETag
`replace_item` on Cosmos — because two writes leave a crash window between them, and because the
preconditions (is it still paused? is the hash still current? was this `decision_id` already
committed?) must be decided against the same state the write commits against. Checked in the endpoint
first, they are a check-then-act race that lets two concurrent decisions both reach the resume. The
stronger form implies the weaker one, so the ordering guarantee above still holds.

Three properties follow:

- **`Command(resume=...)` must be idempotent at the graph level.** Re-invoking on an already-resumed
  thread must not double-apply the decision. LangGraph re-executes the interrupted node from the top,
  so `hitl_gate` above the `interrupt()` call must stay pure — which it is, by construction — and the
  code below it must be a pure function of `(decision, state)`.
- **POST retries are idempotent by decision id.** A reviewer double-clicking, or a client retrying a
  timed-out request, must not resume twice. `decision_id` is client-minted and **required** — an
  optional idempotency key silently means nothing when omitted. A retried decision (same
  `decision_id` + same body) replays the previously committed response and resumes nothing; a
  *different* body against a consumed decision is a 409, not a silent overwrite. The body is
  fingerprinted together with the *verified reviewer*, so another identity reusing someone's key is
  a conflict to surface, not a retry to replay. A replay is answered whatever the current status is,
  since a retry naturally arrives after the run has moved on.
- **A stale hash is a 409 that keeps the run reviewable.** The response carries the current hash so
  the client can re-review and resubmit; the run stays `awaiting_approval`. This replaced #36's
  escalate-on-stale: losing a race to a concurrent edit is a concurrency conflict, not an
  investigation failure, and escalation is reserved for repeated policy failures.
- **Publication is idempotent by `publication_id`** ([G-58](./status.md#g-58)). `finalize_report`
  stamps a `publication_id` **derived** from `(investigation_id, report_hash)` — never minted — and
  the terminal result is committed through a sink that writes it at most once. Derivation is the
  whole mechanism: LangGraph re-executes an interrupted node from the top, so a checkpoint-recovered
  run runs `finalize_report` again, and a fresh key each time would publish the same report twice.
  A second, *different* `publication_id` on an already-published run fails closed rather than
  overwriting the bytes an approval was bound to. Binding the id to `report_hash` and not the run
  alone is deliberate: an `edit` produces different approved bytes, which is a genuinely different
  publication and must not be absorbed as a replay of the first.
- **Self-approval of one's own edit is permitted in v1 — stated, not defaulted.** An `edit` followed
  by an `approve` from the same identity is a normal single-reviewer workflow. Now that the endpoint
  authenticates the reviewer (#36, [G-01](./status.md#g-01) closed), a two-person rule *could* be
  enforced — v1 deliberately does not, and both identities are recorded, so the policy can be tightened
  later without a schema change. Revisit when v1's read-only scope ends and the gate guards remediation.

### The four properties the protocol must hold

1. **Resumability.** `thread_id` derives from the unique `investigation_id` (not reused across reopens
   or reruns), so resume is unambiguous across process restarts even when the same `incident_id` is
   investigated more than once — a durable await, not a blocking thread.
2. **Hash binding — to the report *and* its evidence.** Approval binds to an immutable `report_hash`,
   and separately to an **`evidence_manifest_hash`**: the map from every cited ref to the
   `result_hash` the tool ledger recorded for it ([§4](data-and-evidence.md#sec-4)). The report hash alone freezes the *bytes* of
   the conclusion; it says nothing about the evidence those bytes cite, which lives in Blob and the
   ledger. Without the manifest, a reviewer can approve exact report text while a cited metric sample
   is re-aggregated, a log is rotated out, or a retrieved passage changes underneath it — the
   signature covers the claim but not its grounding. `finalize_report` re-checks both hashes, so a
   publish whose evidence moved after approval fails closed rather than shipping a report that cites
   something that no longer says what it said. **Contradiction acceptances ride the report hash** —
   the ids live inside the hashed report, so an acceptance cannot be replayed against a different set
   of caveats.
3. **Optimistic concurrency at two levels**, separate mechanisms, both required: the *report* level
   (reviewer's `submitted_report_hash` vs current state) and the *store* level (Cosmos ETags on the
   investigation record, so two concurrent decisions cannot both commit).
4. **Verified reviewer identity** — *realized in #36* ([G-01](./status.md#g-01) closed). The decision
   binds to an authenticated human Entra principal ([§12](deployment.md#sec-12)) — token-validated at the endpoint, recorded
   in the `ApprovalRecord` alongside the hash, and distinct from the agent's own managed identity.
   Before #36 the approval record attested only that *someone typed a name*; that is now the one target
   property of the four that is already met.

**Durability is a precondition, not a nicety.** The checkpoint and the investigation record are
*separate* stores and both must survive the pause — the checkpointer alone does not cover the resource
record the poll endpoint reads. An `awaiting_approval` investigation is, by design, the one that sits
idle long enough to be scaled to zero ([G-02](./status.md#g-02)).

### Dispatch is durable, not post-response background work

> **Status:** `proposed` — the 202 runs the graph in-process today; no outbox, queue, lease, or
> fencing exists · gap: [G-34](./status.md#g-34)

Durability of the *pause* is the obvious half. The *initial leg* is the one that actually gets
interrupted more often, and nothing recovers it today:

- `POST /investigations` returns `202` and the graph runs as **post-response background work**.
- Container Apps' HTTP scaler counts **active HTTP requests**, not invisible post-response threads.
  With `minReplicas = 0` a replica can be reclaimed **mid-round**, while an investigation is still
  gathering — the scaler has no reason to keep it warm, because from its view the request already
  returned.
- The checkpoint bounds the damage — work already done survives — but **nothing re-drives the run**.
  The record sits at `running` forever, and a poller waits on a state that will never advance.

**Post-response execution behind an HTTP scaler is not an honest `202`.** An accepted job that only
runs while an HTTP request happens to keep a replica alive is not a durable accepted job. The two
recovery mechanisms an earlier draft offered as the *working default* were each unsound, and naming
why is what forces the real design:

- **Startup sweep** — re-drive expired-lease records on boot — **needs something to boot.** Under
  scale-to-zero there is no replica to run the sweep; the trigger and the failure share a cause.
- **Resume-on-poll** — a `GET` that re-drives an expired lease — turns a **read into a write plus
  LLM/tool spend**, lets multiple pollers (and health/monitoring clients) **race to restart the same
  run**, makes recovery depend on a human or UI *continuing to poll*, and leaves an **abandoned but
  important** investigation stalled forever.

> **Decision — durable dispatch is v1, not v2.** `POST /investigations` performs a **Cosmos
> transactional write** of the investigation record **and** a **dispatch-outbox record** in one
> logical partition (the outbox container of [§12](deployment.md#sec-12)), then returns `202`. The **change feed** relays the
> outbox event onto **Service Bus**; a **queue-triggered Container Apps worker** (KEDA queue scaler)
> picks it up and drives the checkpointed graph. This is the standard Azure background-processing
> shape — scale workers from *queued work*, not from HTTP activity — and it **composes with
> scale-to-zero rather than fighting it**: the queue scaler wakes a worker on a pending message, which
> the HTTP scaler structurally cannot do for a post-response thread. The outbox makes the accepted job
> and its dispatch atomic (one container, one partition — [§12](deployment.md#sec-12)); the queue makes recovery a redelivery,
> not a poll. *(This resolves former open decision [§13.2](decisions.md#sec-13) (D); Service Bus moves from v2 into v1
> scope.)*

```
POST /investigations
   └─ Cosmos transaction (one logical partition):
        investigation record  +  dispatch-outbox record
   └─ 202
change feed → Service Bus message
queue-triggered worker → checkpointed graph  (KEDA queue scaler; minReplicas 0 → wakes on message)
```

**A lease alone is not safe — it needs a fencing token.** Even with a durable queue, a worker can
appear dead (a lease lapses on a network partition) while it is still executing. If a second worker
then claims the run, **both** proceed — duplicate tool calls, duplicate spend, racing writes. The
guard is a **monotonically increasing fencing token (lease epoch)** stamped on the record: claiming a
run bumps the epoch, and **every state transition writes conditionally on still owning the current
epoch** (Cosmos ETag + epoch check). The partitioned worker A, resuming after its lease lapsed, finds
its epoch stale and its conditional write **fails closed** — it cannot advance a run another worker
now owns. A lease answers *is the worker gone*; the fencing token answers *am I still the owner*, and
only the second question is safe to write against.

`awaiting_approval` is explicitly **exempt** from lease expiry — it is a legitimately idle state with
no worker, which is why it needs the *pause* durability of [G-02](./status.md#g-02) instead. Conflating
the two is how a waiting reviewer's investigation gets "recovered" out from under them. The queue and
the pause are separate mechanisms: the pause is not a queued message, and re-driving it comes from the
decision endpoint ([§8](workflow-design.md#sec-8)), not the dispatcher.

### What this gate is, and isn't

In v1 (read-only), this is the **publication and quality** control — not the last line against
consequential external action, which only appears in v2 remediation. The consequential write in v1 is
the memory index, guarded separately by the verified-postmortem lifecycle ([§5](workflow-design.md#sec-5)) and a distinct
publishing identity ([§12](deployment.md#sec-12)), not by this gate.

---
