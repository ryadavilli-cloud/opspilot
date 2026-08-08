# OpsPilot — Evaluation

**Part of the OpsPilot architecture set.** The scorecards, the cassette-replay identity, the answer-key corpus and scenarios, and all current numbers. Design docs cite the *axis*; the *values* live here.

> **Document map & `§N` resolver:** the map in [`architecture.md`](./architecture.md).

---

## 10 (eval). Evaluation

*The evaluation slice of §10. The guardrail and operational slices are in
[`architecture.md`](./architecture.md) § 10 and [`deployment.md`](./deployment.md) § 10.*

### Evaluation

Three instruments, one answer key.

**1. The slice scorecard** *(built)* — all seven scenarios end-to-end against a versioned baseline:
routing accuracy, category accuracy, evidence recall (over *novel* scenarios only — a correctly
fast-pathed known issue gathers no diagnostic evidence by design), `rca_correctness`,
`red_herring_avoidance`, unsupported-evidence rate, tool-call validity, tool-selection accuracy,
loop-termination accuracy, iteration compliance, MCP parity. `evaluate(implementation=...)` selects the
diagnosis + triage pair; deterministic scores are the retained floor. The LLM run is gated
**deterministically by cassette replay** — record once, commit, replay in CI with no API call.

**2. The wild generalization slice** *(built)* — the held-out **Online Boutique** RCAEval slice: real
third-party telemetry the agent was never tuned on. Each RE1 fault case is adapted into an incident the
*same* tools query (retrieval suppressed, so no RetailEase knowledge leaks in), scoring whether the
agent names the injected root service from metric anomalies alone.

**3. The metric framework** *(per-phase)* — retrieval (Precision@K, MRR), generation (groundedness >
0.85, faithfulness, completeness), agent-loop (routing, tool-selection, loop-termination),
safety-violation rate, cost/p95-latency. Golden + synthetic sets gate every deploy: **DeepEval in CI,
the Foundry Eval SDK in the Azure pipeline**; LangSmith stays a dev-local tracing adapter and never
gates the Azure deploy — its exporter lands at **Stage 8** as the deferred sink half of
[G-61](./status.md#g-61) (span emission itself has been live since Stage 5g).

> **Required addition — `acknowledgment_rate`.** A single acknowledged contradiction can be honest
> analysis; a rising rate is a model finding the cheap path past the gate ([§5](workflow-design.md#sec-5)). Scored per
> implementation and per severity, treated as a regression axis rather than a report field — the
> abuse signal is the trend, and a trend is only visible if someone is counting. Pairs with
> `disposition` mix: a growing share of `qualified` conclusions is the same signal, seen from the
> other side. See [G-44](./status.md#g-44).

> **Required addition — `knowledge_grounding`.** The instruments above score retrieval *in isolation*
> (MRR) and conclusions *in isolation* (`evidence_recall`, `rca_correctness`), and **nothing joins
> them**. A joining axis — does retrieved knowledge reach and change the conclusion, verified by a
> retrieval-suppressed ablation — is required before the "grounded in runbooks and past incidents"
> claim is falsifiable at all, and before thresholds go hard. See [G-06](./status.md#g-06).

> **Required addition — known-issue-path metrics.** The fast path is scored today only by whether it
> lands the right resolution, which hides *how* it got there. It needs four explicit axes so a
> too-eager or too-timid gate is visible: **candidate precision** (of surfaced candidates, how many are
> genuine matches), **verification false-positive rate** (a candidate the signal-check *confirmed* that
> was actually wrong), **false-fast-path rate** (a novel incident wrongly resolved as a known issue —
> the expensive error), and **correct fall-through rate** (a non-match correctly sent to full
> diagnosis). These make [G-09](./status.md#g-09)/[G-11](./status.md#g-11) measurable rather than
> asserted. See [G-55](./status.md#g-55).

### The cassette identity must be the full behavior-affecting input, not three fields

> **Status:** `proposed` — the replay key is `(model_id, messages, temperature)` · gap: [G-54](./status.md#g-54)

Cassette replay is what lets a non-deterministic LLM scorecard gate CI for free (record once, replay
with no API call). But **the recorded response is a function of far more than three fields**, so keying
on `(model_id, messages, temperature)` makes the cassette silently stale: change the system-prompt
version, a tool schema, the response schema, `effort`, `max_tokens`, or the provider API version, and
the *behavior changes while the key does not* — CI replays a response the current inputs would never
produce, and passes green on a lie. The key must be a **cassette manifest** hashing **every
behavior-affecting input**:

```
system_prompt_version · tool_schemas+descriptions · response_schema · provider_api_version
· effort/reasoning setting · max_tokens · stop_sequences · model_deployment/version
· provider_hosting_mode (azure_openai | anthropic_foundry) · safety_settings · messages · temperature
```

Any of these changing produces a new key → a cache miss → a required re-record, rather than a false
hit. (This is also why the [§5 (C)](workflow-design.md#sec-5) note pins `model_id` per run — a mid-run tier switch would split one
run across two manifests.)

> **Replay cannot see live-provider drift — a canary must.** Cassette replay is deterministic *by
> construction*, which is its value and its blind spot: a hosted model that shifts behavior between the
> record date and today produces the *same* cassette hit, so CI never notices. A **scheduled live-canary
> evaluation** — the real provider, a small held-out slice, off the CI path — is what detects drift; its
> results **inform deployment policy** (re-baseline / re-record / hold) without making routine CI
> nondeterministic. Deterministic replay gates *code* changes; the canary watches the *provider*. See
> [G-54](./status.md#g-54).

### An axis is only as good as the scenario that can fail it

> **Status:** `proposed` — current scenarios are telemetry-solvable · gap: [G-35](./status.md#g-35)

**The corpus is part of the instrument.** A metric over scenarios that cannot exhibit the failure it
measures reports a passing number forever, and the project already has the proof: the wild slice runs
with **retrieval fully suppressed** (`_NoRetriever`) and still scores RCA 0.80. Every answer-key
scenario's `expected_evidence` is 100% telemetry refs. So a `knowledge_grounding` ablation over the
current corpus would show **no delta — and the axis would pass vacuously**, certifying exactly the
disconnection it was built to detect.

Each new deterministic check needs a scenario constructed so that it *can* fail:

| Capability | Required scenario class |
|---|---|
| `knowledge_grounding` ([G-06](./status.md#g-06)) | Telemetry **underdetermines** the root cause; a KB doc carries the disambiguating fact. Without this the ablation is a no-op. |
| Contradiction detector ([G-07](./status.md#g-07)) | A genuine contradiction — evidence supporting two readings, with a later signal that discriminates (exercises `resolved`) and one that does not (exercises `acknowledged`). |
| Severity revision ([G-12](./status.md#g-12)) | A **mis-triaged** incident: reported SEV3, dependency evidence reveals anomaly on a critical-path service. Must pair with a near-miss that reaches a critical service *without* anomaly, so the impact predicate is tested in both directions. |
| Verification node ([G-09](./status.md#g-09)) | A **disqualifying-signal near-miss** — a candidate that matches on description and fails on signals. |

> **Standing constraint — n = 7 has no statistical power.** With seven scenarios, every rate quantizes
> to sevenths: a `> 0.95` threshold means "7/7", and one scenario flipping moves a metric 14 points.
> Baselines are therefore *change detectors*, not measurements, and the difference matters most at
> Stage 11 when thresholds become a hard gate. Growing the corpus is the fix; until then, a threshold
> that cannot be met at any value other than 1.0 should be written as `== 1.0` and understood as such,
> not dressed as a fraction.

**Baselines move deliberately.** The scorecard is committed; CI fails on material regression; baselines
only move via an explicit reviewed re-baseline commit, never silently, and are expected to move *up* as
capabilities land.

---

## 11 (data). Answer-key corpus & scenarios

*The data slice of §11. The models/provider slice is in [`deployment.md`](./deployment.md) § 11; the
retrieval-parity slice is in [`data-and-evidence.md`](./data-and-evidence.md) § 11.*

### Data

The primary corpus is **RetailEase** — a self-contained synthetic system (checkout/payment/inventory/
catalog APIs + notification worker; Service Bus, Cosmos DB, Redis) with generated logs, metrics,
deployments, dependencies, alerts, and incidents, plus authored runbooks, architecture docs, and
postmortems. A self-authored world keeps the demo coherent, the ground truth exact, and the provenance
clean.

**The labels are the source of truth.** An answer key of incident scenarios — each carrying its
expected root cause, evidence refs, and retrieval targets — projects into the eval golden sets;
everything else is generated from or validated against it. An end-to-end **closure gate** proves every
evidence ref resolves to a telemetry row, every retrieval target to a KB doc, and every postmortem to
a historical incident. One scenario (inc-004) is a deliberate **red herring**, so
correlation-vs-causation discrimination is a scored, falsifiable behavior rather than a claim; another
(inc-007) is a genuine **recurrence** with a new incident id, without which the known-issue fast path
could only ever match an incident to its own postmortem.

**Calibrate, don't copy.** Real public datasets shape *distributions*, never content: telemetry signal
proportions from the **RCAEval** microservice-RCA benchmark, incident-layer distributions from a real
**ITSM event log** — both CC-BY, raw data gitignored, only derived profiles committed. Severity is
*emergent* (blast-radius × path-criticality); the noise floor is sub-threshold instances of the same
failure modes; same-domain **synthetic distractors** make the retrieval eval realistic.

| Index / store | Sources | Notes |
|---|---|---|
| Runbooks + architecture (semantic) | **RetailEase synthesized KB** (primary); Google SRE Workbook / Atlassian handbook + HF incident-playbook datasets as cited augmentation | Provenance in `data/provenance.md` |
| Past incidents (recency-weighted Store) | **RetailEase synthetic postmortems** (primary); `6StringNinja/synthetic-servicenow-incidents` + `danluu/post-mortems` as realism reference | Written back **only** by `verified_postmortem` after closure + RCA reconciliation — never predicted RCA ([§5](workflow-design.md#sec-5)) |
| Telemetry / metrics | **RetailEase synthetic** `logs.jsonl` / `metrics.json` (primary); `logpai/loghub` as optional reference | loghub's **research/academic license** applies if sampled — cite, not commercial |
| Eval golden set | Hand-built from the RetailEase scenarios (~15–50 pairs) | Hardest-to-fake signal; grows one case per bug |

---
