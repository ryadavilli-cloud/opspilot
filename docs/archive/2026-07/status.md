# OpsPilot — Build Status & Gap Register

**Companion to the [`architecture.md`](./architecture.md) set.** Those documents describe the *target*
design and stay stable. This one describes *what exists*, *what doesn't*, and *what is wrong* — and it
churns. **`§N` references follow the document map in [`architecture.md`](./architecture.md)** (e.g. [§5](workflow-design.md#sec-5)
is in `workflow-design.md`, [§4](data-and-evidence.md#sec-4)/[§6](data-and-evidence.md#sec-6) in `data-and-evidence.md`, §10–[§12](deployment.md#sec-12) in `deployment.md`/`evaluation.md`).

Every gap has a stable id (`G-nn`). Reference the id from any architecture-set file, `execution-plan.md`,
commits, and PRs — never re-describe a gap in prose, or the descriptions drift apart. Resolved items
move to [§4 (Resolved)](#4-resolved) (of this file) with the commit that closed them rather than being deleted, so the record of
*what was wrong and when it was fixed* survives.

**Last reviewed:** 2026-07-27 (Stage 5c **`verified`**; **Stages 5e + 5g closed**) · **Merged through:** `#50`
· **Deploy GREEN on `#50`** (2026-07-27) — Stage 5e is `verified` live, see below

> **✅ Stage 5c (#36) is `verified` — the deploy is green (2026-07-26, run on #47).** The smoke gate
> proves the full round trip live on Azure: `/health/ready` + `/version` (**`gpt-5-mini`**,
> `single_agent`) + sync `/investigate` (grounded RCA, 14 evidence/citations) + the async
> `/investigations` → pause → `/decision` → resume path
> (`history=[queued, running, awaiting_approval, running, completed]`, **`approval_kind=service_principal`**).
> Getting here cleared a stack of deploy blockers: model deprecation → `gpt-5-mini` (#39); ACR pull
> `registries:null` (#40); Cosmos-not-provisioned → **in-memory stores** (#41, durable Cosmos deferred
> to **5f**); `reasoning_effort` low→medium (#45); smoke read-timeout 10s→180s (#43); reviewer-identity
> `idtyp` optional-claim + **fail-closed** auth (#47). The pause is still **non-durable** (in-memory,
> [G-02](#g-02)) until 5f.
>
> **⚠️ Correction (2026-07-27).** This note previously said the `single_agent` eval baseline is
> recorded against the dev model `qwen3:8b`. **That was wrong.** Both committed cassettes carry
> `"model_id": "gpt-4o-mini"`, and `eval/record_single_agent.py`'s documented run line is
> `OPSPILOT_LLM_PROVIDER=openai OPSPILOT_LLM_MODEL=gpt-4o-mini`. `qwen3:8b` is the *local dev* model;
> it is not what the committed scorecard was recorded on. Two consequences the old wording hid: a
> re-record **spends the OpenAI key**, and the CI gate certifies a **non-reasoning** model
> (`gpt-4o-mini`) while the deploy runs a **reasoning** model (`gpt-5-mini`, effort `medium`). That
> model-class mismatch is a live instance of [G-54](#g-54), not a resolved concern.

> **✅ Stage 5e is `verified` — the deploy is GREEN (2026-07-27, run on `#50`).** The two-PR red
> streak is closed. `#49` broke the smoke gate by requiring a principal the script did not send
> (401); `#50` fixed the script and then surfaced the deeper problem, that the `Submitter` role
> named in config had never been created in Entra ([G-62](#g-62), 403). Both are now closed: the
> role exists, the deploy service principal holds it, and the gate passes end to end.
>
> **The conclusion contracts are proven in production, not just in tests.** The smoke run's
> published hypothesis is:
>
> ```
> Root cause: a failure in the dependency payment-api, affecting checkout-api,
> with effect onset at 2026-06-28T10:15:09+00:00 (causing event logs:payment-api:evt-004-02).
> ```
>
> That is `render_causal_statement`'s template verbatim, so the prose a reviewer reads was RENDERED
> from the admitted `CausalClaim` rather than authored by the model ([G-50](#4-resolved)). The same
> run gathered 16 evidence/citations (was 14) and drove the async pause → authenticated decide →
> resume path to `completed` with `approval_kind=service_principal`.

> **Refresh trigger.** This file drifted from the code within one day of being written — `2bad319`
> closed two gaps while the register still listed them open. **Any PR that closes a gap must move its
> entry to [§4 (Resolved)](#4-resolved) in the same PR**, and any PR that adds a `G-xx` reference must confirm the entry still
> reflects the tree. The one-line-per-gap discipline is what makes that cheap; skipping it is what
> made the old inline-prose version untrustworthy.

---

## 1. Build status by component

**Status uses the lifecycle vocabulary frozen in `architecture.md` → *How to read*** — `proposed` ·
`in review` · `on branch` · `merged` · `deployed` · `verified`, each implying the ones before it.
Two clarifications this table needs and that one does not:

- **`working tree`** is weaker than `on branch`: written, not committed anywhere. It is not a build
  state, it is a note that the next commit is expected to move something.
- **`merged` ≠ `deployed`** here matters for CI-only artifacts (the parity suite, the scorecard) and
  for seams that exist but are not activated in the live environment (the Cosmos checkpointer).

| Component | Status | Notes |
|---|---|---|
| **Data foundation** | ✅ `verified` | RetailEase corpus: topology + answer key, calibrated telemetry (RCAEval / ITSM profiles), alert/incident layer, authored KB with provenance, end-to-end closure gate. Held-out Online Boutique slice runs as the "wild" generalization eval. |
| **Tool set (8 tools)** | ✅ `deployed` | Six telemetry/record tools + both retrieval search tools behind `ToolService` with the uniform typed envelope. Validators normalize tz; `run_tool` catches any exception. Results are rendered lines, not typed facts. *Gaps: [G-42](#g-42), [G-04](#g-04), [G-16](#g-16), [G-17](#g-17), [G-18](#g-18)* |
| **Retrieval** | ✅ `deployed` (measured in isolation) | Hybrid (dense + BM25 via RRF) beats vector-only on MRR (0.708 vs 0.687); `bge-reranker-v2-m3` lifts to **MRR 0.792** (`eval/baselines/retrieval_scorecard.json`). No temporal bounds; AI Search parity unframed. *Gaps: [G-04](#g-04) — reaches no model · [G-52](#g-52), [G-56](#g-56)* |
| **Diagnosis loop** | ✅ `deployed` (floor + LLM) | Frozen plan→act→observe transitions (`diagnosis/contracts.py`); `DeterministicPlanner` (floor) or `LLMPlanner` (batched tool calls per round + a synthesis step). Tool results surfaced as `signal [ref]` values — and the loop **also concludes**, which it must not. Deadline honored only between rounds. *Gaps: [G-40](#g-40), [G-41](#g-41), [G-07](#g-07), [G-08](#g-08), [G-12](#g-12), [G-22](#g-22), [G-47](#g-47)* |
| **Conclusion contracts** | ✅ `verified` (5e, #50 — rendered statement observed in the deployed smoke run) | The conclusion is a typed `CausalClaim` + `ReportClaim`s that code ADMITS from the model's proposal (`diagnosis/admission.py`), the published prose is RENDERED from those fields (`diagnosis/render.py`), and a terminal run carries an `InvestigationResult` variant tag. Entity resolution is against refs this run produced — topology-version validation still needs typed evidence. *Closed: R-12, R-13, R-14, R-15 · Gaps: [G-42](#g-42), [G-43](#g-43), [G-40](#g-40)* |
| **Guardrails (executable)** | ✅ `deployed` | Read-only tool policy + no-unsupported-hypothesis citation gate wired into `safety_validate`; model output parsed through strict Pydantic schemas, malformed → fail closed. Content Safety / Prompt Shields pipeline not drawn or wired. *Gaps: [G-05](#g-05), [G-10](#g-10), [G-26](#g-26), [G-46](#g-46)* |
| **MCP** | ✅ `merged` (CI only) | Parity suite (in-memory client/server vs direct calls, identical envelopes). Transport only — no security/operational contract, and the incident source is hard-wired local. *Gaps: [G-24](#g-24), [G-53](#g-53)* |
| **CI regression gate** | ✅ `merged`, enforced (⚠️ one axis is noise-bound) | ruff + mypy + `core`/`full` lanes as required checks before deploy; scenarios scored against versioned baselines. LLM scorecard gated deterministically by cassette replay — no API call in CI. **Replay key is now the full behaviour manifest** (model, `reasoning_effort`, API version, sampling seed, resolved prompt versions); a stale cassette fails at LOAD naming the drifted field, instead of silently replaying (#50). Still open: no drift canary, and `evidence_recall` is gated on a single draw of a nondeterministic model. *Gaps: [G-54](#g-54), [G-35](#g-35)* |
| **LLM agent (`single_agent`)** | ⚠️ `deployed` (floor-beating claim is **within noise** on one axis) | Beats the deterministic floor on routing (0.857→1.0), tool-selection, and red-herring avoidance; `rca_correctness` ties at 0.714 (inc-004's true root is external). Wild slice: RCA **0.80 vs 0.00**. Deployed on **`gpt-5-mini`** (Azure OpenAI, keyless MI) as of #47. **The committed scorecard is recorded against `gpt-4o-mini` via the `openai` provider, NOT `qwen3:8b`** (corrected 2026-07-27; see the header note) — so CI certifies a *non-reasoning* model while the deploy runs a *reasoning* one ([G-54](#g-54)). **`evidence_recall` no longer supports a floor-beating claim:** four re-records ranged 0.4444 / 0.5111 / 0.5556 / 0.6222 against a floor of 0.4889, i.e. the range straddles the gate and one draw failed it ([G-35](#g-35)). |
| **Typed hash-bound report** | ✅ `deployed` (5a + 5e) | Frozen `IncidentReport` + `report_hash` (sha256 over canonical JSON); `apply_edit` re-validates into a new report with a new hash; `finalize_report` asserts the approved hash. **5e (#50) added `report_claims` inside the report**, so secondary claims sit in the bytes the approval binds and `safety_validate` checks their refs; `recommended_next_step` is rendered from a derived claim, not the old hard-coded rollback. *Closed: R-07, R-14, R-15* |
| **Durable checkpointer seam** | ✅ `merged` (5b) — not activated | `build_checkpointer()` → `none`/`memory`/`sqlite`/`cosmos`; SQLite durable across restart (CI-gated); `cosmos` via first-party `langchain-azure-cosmosdb`, keyless. One store modeled; the multi-container split is unbuilt. *Gaps: [G-02](#g-02) — not activated; default is `none` · [G-48](#g-48)* |
| **Async investigation API** | ✅ `deployed` (#34); auth `merged` (#49 + #50) — **smoke gate red pending an Entra role grant** (header note, [G-03](#g-03)) | `POST /investigations` → 202 + poll URL; `GET /investigations/{id}` status + history + typed result; idempotent on `(incident_id, summary)`; behind an `InvestigationRepository` seam; atomic `get_or_create` + `?force_rerun=true`. #49 added submit/read auth + a basic concurrency cap ([G-03](#g-03), [G-57](#g-57)). The 202 runs the graph **in-process** — no outbox, queue, or fencing. *Gaps: [G-02](#g-02), [G-34](#g-34) · closed: R-08* |
| **Operator console** | ✅ `merged` (#35 + #36 + #49) | Same-origin self-contained page at `GET /console`; submit, poll, review hypothesis/evidence/citations/safety/runtime, **and act on a pause** — #36 added authenticated decision controls (approve / edit / request-more-evidence / reject) behind an MSAL-style PKCE sign-in with an approver-role check; #49 (merged) extends the same bearer token to the submit and poll requests (both now server-enforced), disabling submit client-side until signed in. The disclosure banner now covers all three actions when no Entra console client is configured, not just decisions. *Closed: [G-23](#g-23). The `request_more_evidence` button's backend state machine is still [G-31](#g-31) (5f).* |
| **HITL interrupt** | ✅ `verified` (5c/#36, deploy green #47) | Real checkpoint-backed `interrupt()`; run ends at the pause; `awaiting_approval` non-terminal status; **authenticated** `POST /investigations/{id}/decision` (Entra token → verified `approver`, per [`adr-reviewer-identity.md`](./adr-reviewer-identity.md)) resumes via `Command(resume=...)`; stale-hash rejection; `edit` re-pauses. **The full round trip is smoke-proven live** (`approval_kind=service_principal`). The pause is still **non-durable** (in-memory saver) and dispatch post-response until 5f. *Closed: [G-01](#g-01), [G-15](#g-15), [G-02](#g-02), [G-32](#g-32), [G-58](#g-58), R-01/R-02/R-03. Open: [G-31](#g-31), [G-34](#g-34) → Stage 5f, PR B* |
| **Known-issue fast path** | ⚠️ `deployed` (candidate half only) | LLM triager surfaces the candidate (catches the inc-007 recurrence). The verification node is `proposed`. *Gaps: [G-09](#g-09), [G-19](#g-19)* |
| **Subagent promotion** | ❌ `proposed` | Loop calls tools directly. *Gap: [G-25](#g-25)* |
| **Cost / budget enforcement** | ❌ `proposed` | Call-count cap only. *Gap: [G-08](#g-08)* |
| **Observability layer** | ✅ `deployed` — emission seam (**Stage 5g closed**) | Node + tool + model spans under the parent `trace_id`, normalized usage capture, in-memory-exporter fixture, `none`/`memory`/`stdout` exporters (#46 + #48, deployed green). Default exporter `none` — the seam is deployed, not the telemetry. Remaining: LangSmith sink (Stage 8), MCP span (Stage 7), App Insights + `CostTracker` + hard gate (Stage 11) — see [G-61](#g-61). |
| **Azure service swaps** | ⚠️ `deployed` (compute + Azure-OpenAI only) | Container Apps + Azure OpenAI (gpt-class) live and keyless. Claude-on-Foundry needs its own Messages-API adapter ([G-45](#g-45)); AI Search, Cosmos container split ([G-48](#g-48)), Blob, Key Vault, publisher identity, Prompt Shields ([G-46](#g-46)) outstanding. Stage 8. |
| **A2A agent card** | ❌ `proposed` | Stretch, Stage 12. |

---

## 2. Gap register

**Severity.** `critical` = blocks the MVP boundary or is a live security exposure · `high` = a
documented claim is currently false, or a control does not do what it says · `medium` = a real defect
with bounded blast radius · `low` = accepted debt or ordinary unbuilt roadmap.

**Kind.** `defect` = merged, and wrong · `unbuilt` = designed but still `proposed` · `claim-risk` =
the document asserts a property nothing enforces or measures — i.e. `deployed` but never `verified`.

**Detail rule.** `unbuilt` is roadmap, not a wound: its row below carries the design pointer and the
stage, and it gets **no detail section** — the design doc's Status header and the execution plan own
that story. Detail sections in [§3](#3-gap-detail) exist only for `defect`, `claim-risk`, and the few
unbuilt items whose *current* code has a hazard worth recording ([G-08](#g-08), [G-31](#g-31)).

| ID | Gap | Sev | Kind | Target |
|---|---|---|---|---|
| ~~[G-02](#g-02)~~ | ~~A paused investigation is not durable~~ **CLOSED #51 + #52, VERIFIED live 2026-07-28** → [R-19](#4-resolved) | — | — | — |
| [G-03](#g-03) | Public ingress is uncapped *(auth fully closed: decision #36, submit/read #49, `/investigate` #50. **Only the request rate limit remains** — every route now requires a proven principal)* | high ⬇ was critical | defect | **Stage 8** |
| ~~[G-62](#g-62)~~ | ~~`Submitter`/`Reader` app roles were never created in Entra~~ **CLOSED 2026-07-27** → [R-17](#4-resolved) | — | — | — |
| [G-40](#g-40) | Two root-cause synthesis authorities | critical | defect | **Stage 6b** |
| <a id="g-42"></a>[G-42](#g-42) | Evidence is untyped — the deterministic checks cannot be written *(design: [§4](data-and-evidence.md#sec-4)/[§6](data-and-evidence.md#sec-6); blocks [G-07](#g-07), pairs with [G-04](#g-04))* | critical | unbuilt | **Stage 6a** |
| [G-45](#g-45) | `AzureOpenAI` can't front Claude-on-Foundry — providers don't compose | critical | defect | **Stage 8** |
| [G-52](#g-52) | No temporal isolation — eval can retrieve future postmortems | critical | claim-risk | **Stage 6a** |
| ~~[G-29](#g-29)~~ | ~~Conclusion is prose, and `blamed_entity` is too coarse for the checks~~ **CLOSED #50** → [R-12](#4-resolved). *(Downstream [G-07](#g-07)/[G-43](#g-43)/[G-40](#g-40) are now unblocked.)* | — | — | — |
| [G-41](#g-41) | Gathering gate grades a conclusion that does not exist; no finalization reserve | high | defect | Stage 6b |
| [G-43](#g-43) | Citation roles are model-asserted and never admitted by code | high | claim-risk | Stage 6b |
| [G-44](#g-44) | `acknowledged` is model-controlled — a one-sentence bypass of the gate | high | claim-risk | Stage 6b |
| [G-30](#g-30) | Coherence gate runs before the conclusion exists | high | defect | Stage 6b |
| [G-04](#g-04) | Retrieved knowledge never reaches the model | high | claim-risk | Stage 6a |
| [G-05](#g-05) | Grounding is forgeable — a field can't attest a producer | high | defect | Stage 6a |
| [G-06](#g-06) | No eval axis joins retrieval to the conclusion | high | claim-risk | Stage 6a |
| [G-07](#g-07) | Two sufficiency dimensions are constants | high | claim-risk | Stage 6b |
| [G-08](#g-08) | Iteration budget is a call count only *(+ no per-call timeout/`max_tokens`, no reserves — [G-41](#g-41))* | high | unbuilt | Stage 6b |
| <a id="g-09"></a>[G-09](#g-09) | Fast path trusts an unverified candidate — publishes the stored resolution unchecked at 0.95, live *(verification design: [§5](workflow-design.md#sec-5); compounded by [G-05](#g-05), [G-19](#g-19))* | high | unbuilt | Stage 9 |
| [G-10](#g-10) | `info_only` bypasses the citation gate entirely | high | defect | Stage 6c |
| [G-11](#g-11) | Known-issue `rca_correct` scores the answer key | high | defect | **Stage 9** ⬅ was 11 |
| [G-16](#g-16) | Truncation desyncs records from their refs | high | defect | **Stage 6a** ⬅ was 10 |
| ~~[G-18](#g-18)~~ | ~~Deploy window admits a post-onset deploy as causal~~ **CLOSED #44** → [R-18](#4-resolved) | — | — | — |
| [G-34](#g-34) | Dispatch is post-response, not durable; no fencing token | high | defect | **Stage 5f** |
| [G-35](#g-35) | No scenario can fail the new checks — axes pass vacuously; **and the metrics are not reproducible across re-records** (measured #50: `evidence_recall` 0.44–0.62 over four draws, straddling the 0.4889 floor) | high | claim-risk | Stage 6a |
| ~~[G-36](#g-36)~~ | ~~Escalation reasons are inferred, and misattributed~~ **CLOSED #50** → [R-16](#4-resolved) | — | — | — |
| [G-46](#g-46) | Content Safety isn't automatic on the Claude path; pipeline undrawn | high | claim-risk | Stage 8/10 |
| [G-47](#g-47) | Round-only cancellation can't hold a hard wall-clock deadline | high | defect | Stage 6b |
| <a id="g-48"></a>[G-48](#g-48) | "Cosmos" is several workloads modeled as one store *(design: [§12](deployment.md#sec-12), [`adr-checkpointer-cosmos.md`](./adr-checkpointer-cosmos.md))* | high | unbuilt | Stage 8 |
| ~~[G-49](#g-49)~~ | ~~Degraded rungs return non-RCA results under the RCA contract~~ **CLOSED #50** → [R-13](#4-resolved) | — | — | — |
| ~~[G-50](#g-50)~~ | ~~Prose `statement` can contradict the typed claim~~ **CLOSED #50** → [R-14](#4-resolved) | — | — | — |
| ~~[G-51](#g-51)~~ | ~~Only the root cause is structured; report-level claims are ungrounded prose~~ **CLOSED #50** → [R-15](#4-resolved) | — | — | — |
| <a id="g-53"></a>[G-53](#g-53) | MCP has no security/operational contract; incident source hard-wired local *(contract: [deployment.md §6](deployment.md), [`adr-mcp-boundary.md`](./adr-mcp-boundary.md); extends [G-24](#g-24))* | high | unbuilt | Stage 7 |
| [G-54](#g-54) | ~~Cassette key is 3 fields~~ **manifest CLOSED #50**; **no drift canary**, and CI certifies a non-reasoning model while the deploy runs a reasoning one | high | defect | **6a** (canary) |
| [G-57](#g-57) | No system-level admission control *(auth/roles/basic concurrency **merged** #49 — quotas, RPM/TPM admission, queue-depth, max-pending-approvals, retention, LangSmith sink rules still open)* | high | partial | Stage 8 |
| <a id="g-12"></a>[G-12](#g-12) | Severity frozen at ingest, capping rigor where mistakes are costliest *(revision design: [§5](workflow-design.md#sec-5); will cap [G-21](#g-21) tiering too)* | medium | unbuilt | Stage 6b |
| [G-17](#g-17) | Malformed rows drop silently; `ok\|error` too weak *(status set resolved)* | medium | defect | Stage 10 |
| [G-19](#g-19) | `search_past_incidents` can retrieve its own answer | medium | defect | Stage 9 |
| [G-31](#g-31) | `request_more_evidence` has no state machine | medium | unbuilt | **Stage 5f** |
| ~~[G-32](#g-32)~~ | ~~Decision-resume failure semantics undefined~~ **CLOSED (Stage 5f, PR A)** → [R-20](#4-resolved) | — | — | — |
| <a id="g-33"></a>[G-33](#g-33) | Memory admission component does not exist — the *verified* phase, distinct from [G-27](#g-27) *(design: [§5](workflow-design.md#sec-5), [`adr-memory-admission.md`](./adr-memory-admission.md); resolves §13.2 E)* | medium | unbuilt | Stage 8 |
| ~~[G-37](#g-37)~~ | ~~Checkpointer + singleton concurrency~~ **CLOSED (Stage 5f, PR A)** → [R-21](#4-resolved) | — | — | — |
| <a id="g-38"></a>[G-38](#g-38) | Mid-run provider outage is undefined — the deterministic floor is composition-time only *(open decision [§13.2](decisions.md#sec-13) A; must stamp its reason, [G-36](#g-36))* | medium | unbuilt | Stage 10 |
| [G-39](#g-39) | Four smaller defects (bundle) | low | defect | Stage 10 |
| <a id="g-20"></a>[G-20](#g-20) | State model partially typed *(`excerpt`/handle → 6a; `IterationBudget` → 6b; `NormalizedAlert`/`ApprovalRecord`/`DegradationState` → 6c)* | low | unbuilt | 6a/6b/6c |
| <a id="g-21"></a>[G-21](#g-21) | Severity→model tier map is unwired — `resolve_tier()` exists in config, read by nothing *(must read the revised severity, [G-12](#g-12))* | low | unbuilt | Stage 6b+ |
| <a id="g-22"></a>[G-22](#g-22) | Batching forfeits per-action checkpoint/cost/cancel *(accepted trade; guarantees re-derived per round: [§3](architecture.md#sec-3))* | low | accepted | Stage 6b |
| <a id="g-24"></a>[G-24](#g-24) | MCP exposure is a parity scaffold — the ownership-aligned split is Stage 7 *(target grouping: [§6](data-and-evidence.md#sec-6))* | low | unbuilt | Stage 7 |
| <a id="g-25"></a>[G-25](#g-25) | Subagents not promoted *(form + threshold trigger: [§7](workflow-design.md#sec-7), [`adr-subagent-promotion.md`](./adr-subagent-promotion.md); sequenced after [G-04](#g-04)/[G-06](#g-06))* | low | unbuilt | Stage 6c |
| [G-26](#g-26) | Untrusted-retrieval guardrail defends an empty set | low | claim-risk | Stage 6a |
| <a id="g-27"></a>[G-27](#g-27) | Postmortem write-back is a stub — `postmortem()` is a terminal no-op, no Store exists *(lifecycle: [§5](workflow-design.md#sec-5), [`adr-memory-admission.md`](./adr-memory-admission.md))* | medium | unbuilt | **5f** (preliminary) / **8** (verified) |
| [G-28](#g-28) | Demo script asserts four behaviors that do not run | medium | claim-risk | per-gap |
| [G-55](#g-55) | Known-issue path lacks precision/false-fast-path metrics | medium | claim-risk | Stage 9 |
| [G-56](#g-56) | AI Search "parity" framed as ranking equality; no embedding-profile versioning | medium | claim-risk | Stage 8 |
| ~~<a id="g-58"></a>[G-58](#g-58)~~ | ~~Publication is not idempotent~~ **CLOSED (Stage 5f, PR A)** → [R-22](#4-resolved) | — | — | — |
| [G-59](#g-59) | Readiness probe 503s on dependency health, contradicting run-level degradation | medium | defect | Stage 8 |
| <a id="g-60"></a>[G-60](#g-60) | `resynth_attempts` not scoped per evidence-epoch — a re-gather inherits the exhausted counter *(design: [§5](workflow-design.md#sec-5) back-edge; part of the [G-30](#g-30)/[G-41](#g-41) rework)* | low | unbuilt | Stage 6b |
| [G-61](#g-61) | Observability emission seam — node/tool/model spans + usage **built** (#46+#48); LangSmith sink → Stage 8, MCP span → §7 | medium | built (emission) | **Stage 8** *(sink; MCP span → Stage 7. Emission half built at 5g — the stage closes, the gap does not)* |

---

## 3. Gap detail

### Critical

<a id="g-02"></a>
#### G-02 — A paused investigation is not durable · `critical` · Stage 5f · **🔧 `working tree`**

> **Working tree:** `repository.py` (a `memory`/`cosmos` factory mirroring the checkpointer seam) and
> `cosmos_investigations.py` (id-uniqueness on the idempotency index + ETag conditional `replace_item`
> with bounded retry) are written but uncommitted. This closes the *repository* half. The
> **checkpointer half** — flipping `OPSPILOT_CHECKPOINTER` off its `none` default on Azure and
> provisioning Cosmos — is **Stage 5f** (activation, per the adopted plan; the earlier "Stage 8"
> pointer predated the 5e/5f split), and the gap stays open until both are live and the kill/restart
> proof below actually runs. Note this addresses the **pause** only; the in-flight leg is
> [G-34](#g-34).

Two separate stores must both survive the pause, and neither does by default:

- `OPSPILOT_CHECKPOINTER` defaults to `none`, which `build_graph` silently upgrades to an in-process
  `MemorySaver` so `interrupt()` works at all — a deliberate fallback that must not be production.
- `InvestigationRepository` is `InMemoryInvestigationRepository`. The Cosmos **checkpointer** (5b)
  does not cover this: it persists LangGraph *state*, not the resource record
  `GET /investigations/{id}` reads.

With `minReplicas: 0` and `maxReplicas: 3`, a paused run is lost on scale-down and a poll can land on
a replica that never saw it. The interrupt makes this load-bearing rather than theoretical: **an
`awaiting_approval` investigation is by design the one that sits idle long enough to be scaled to
zero.**

**Definition of done:** kill the process while `awaiting_approval`, restart, submit the decision,
observe the run resume and finalize.

<a id="g-03"></a>
#### G-03 — Public ingress is unauthenticated and uncapped · `critical` · Stage 5/8

`infra/main.bicep` sets `ingress.external: true` with no auth middleware, authorization policy, or
rate limiter anywhere in `api.py`, and the default deployment selects the LLM-backed `single_agent`.
Anyone who finds the URL could drive unlimited Azure OpenAI spend, submit forged approvals (closed
at 5c/#36, [G-01](#g-01)), or submit/read investigations.

**Closed for `POST /investigations` / `GET /investigations/{id}`** (#49, **merged** `0769ede`, pulled
forward from Stage 8 — did not need to wait on 8a's Cosmos container/ACL split; it reuses the existing
investigation repository as-is): both now require an Entra-validated principal
(`auth.require_role`/`require_any_role`, reusing [G-01](#g-01)'s validator instance under new
`Submitter`/`Reader` roles), plus a basic per-user/global concurrency cap
(`config.MAX_CONCURRENT_INVESTIGATIONS_*`, checked only when a new background job would actually
dispatch) before Azure OpenAI spend is incurred.

**Still open:** `POST /investigate` (the synchronous compatibility endpoint) carries no auth
dependency and no rate limit — same class of exposure, narrower now that it is the only
unauthenticated route left. A fix is written and committed **`on branch`** (`1b5cb51`,
`stage-5e-conclusion-wiring`) — it gates `/investigate` on the same role and repairs the smoke gate
that #49 broke (header note) — but it is **not in `main`** and has no open PR, so this row stays open.

**Fix:** apply the same Entra-role gate to `/investigate` (or retire the route), plus a request
rate limit, **before** the `minReplicas 0 → 1` always-on flip increases exposure. Land `1b5cb51`
first: until it does, `main`'s deploy pipeline stays red at the smoke gate.

<a id="g-62"></a>
#### G-62 — `Submitter`/`Reader` app roles do not exist in Entra · `critical` · immediate

`#49` introduced `config.ENTRA_SUBMIT_ROLE` (`Submitter`) and `ENTRA_READ_ROLE` (`Reader`) and made
`POST /investigations` require the first of them; `#50` applied the same gate to `POST /investigate`.
**Neither role was ever added to the API app registration.** Verified 2026-07-27:

```
az ad sp show --id c9de5ba9-…  --query "appRoles[].value"   ->  ["Approver"]
appRoleAssignments for opspilot-github-oidc               ->  [Approver] only
```

So `require_submitter`, which is a strict single-role check, rejects **every** caller: the deploy
service principal, and any human signing in through the console. The consequence is not a degraded
path, it is that **the deployed system cannot start an investigation at all**.

Reads and decisions still work, which is why this hid: `require_reader` uses `require_any_role` over
(read, submit, decide), and the existing `Approver` assignment satisfies it; the decision endpoint
has always used `Approver`. Only the submit gate is strict, and only submit is dead.

The smoke gate reports it precisely (`principal lacks the 'Submitter' role required for this
action`), which is how it surfaced — the same run that `#50` fixed the 401 on.

**Fix (Entra, no code change):**
1. Add `Submitter` and `Reader` to the API app registration's `appRoles`.
2. Assign `Submitter` to the deploy service principal `opspilot-github-oidc`
   (`2504d080-60d7-476b-809b-c3626e3d615d`), which today holds only `Approver`.
3. Assign `Submitter` (and `Reader` where appropriate) to the human reviewer identities that use the
   console, or the console's submit button stays 403 for them too.

**Lesson for the register:** `#49` was merged and called `deployed` on the strength of green
`core`/`full` lanes. Those lanes stub the authenticator, so they can never catch a role that exists
in config but not in the tenant. This is exactly the class of failure
[code-guidelines §2](./code-guidelines.md) has in mind with "a successful health endpoint is never a
release gate on its own" — only the deployed smoke test could see it, and it was already red for a
different reason, which masked it for two PRs.

<a id="g-40"></a>
#### G-40 — Two root-cause synthesis authorities · `critical` · Stage 6b

The run can conclude twice, and nothing compares the two conclusions.

- `LLMPlanner` **synthesizes on the stopping turn** — `revise_hypothesis(..., final=stopping)` in
  `nodes/investigation.py`. That conclusion is what `compute_sufficiency` grades and what the run
  stops on.
- [§5](workflow-design.md#sec-5)'s `synthesize_report` was scheduled as a **second LLM node** producing the
  structured claim the coherence gate checks and the human approves.

Two model calls over the same evidence will eventually disagree — the loop naming the payment
gateway, the report node naming a checkout deploy. Both are grounded, both cite real refs, and the
audit trail records only one of them. The stop decision and the published claim then rest on
different reasoning, undetectably.

This is also the **root cause of [G-30](#g-30)**: the coherence checks have nothing but a placeholder
to run against precisely because the loop owns a conclusion it should not own.

**Fix:** the one-authority rule ([§3](architecture.md#sec-3)/[§5](workflow-design.md#sec-5)). Land
with [G-29](#g-29) and [G-41](#g-41): the same edit that removes the loop's final synthesis must add
the node that replaces it.

### High

<a id="g-41"></a>
#### G-41 — The gathering gate grades a conclusion that does not exist · `high` · Stage 6b

Two defects in one expression, both in `diagnose_continue` / `compute_sufficiency`:

**1. Circular dimensions.** `citation_coverage` and the full contradiction set are conclusion-level —
they grade the citations and coherence of a root cause. They were evaluated *before* synthesis, against
the provisional hypothesis ([G-40](#g-40)), which the design itself calls a placeholder. A gate whose
inputs describe an object the run has not produced cannot be made correct by improving its producers.

**2. No finalization reserve.** `state.iteration.exhausted` routes into synthesis — i.e. the run is
out of budget at the exact moment it must make its most expensive and most important model call, and
then still validate and safety-check. Gathering is elastic and will consume whatever it is allowed to;
today it is allowed to consume everything.

**Fix:** the [§5](workflow-design.md#sec-5) gate split + the partitioned `IterationBudget` with
non-fungible reserves. Lands with [G-07](#g-07), [G-08](#g-08), [G-30](#g-30), [G-40](#g-40).

<a id="g-43"></a>
#### G-43 — Citation roles are model-asserted and never admitted by code · `high` · Stage 6b

Every conclusion-level check keys off `Citation.role`, and the model assigns it. A model that would
fail causal-order can relabel the inconvenient `effect` citation as `context`; a weak observation can
be promoted to `cause`. The check still runs, still reports deterministic, and passes.

**A deterministic check over a model-controlled input is deterministic in form only** — which is the
same failure as model-flagged contradictions, one level down, and the reason the typed-hypothesis work
([G-29](#g-29)) does not by itself close [G-07](#g-07).

**Fix:** roles are *proposed* by the model and *admitted* by code against the typed evidence — the
[§5](workflow-design.md#sec-5) admissibility table; an inadmissible role raises a
`role_inadmissible` `Contradiction`, so relabeling is itself detectable. Requires [G-42](#g-42)
(nothing to admit against without typed facts).

<a id="g-44"></a>
#### G-44 — An acknowledged contradiction is a model-controlled bypass · `high` · Stage 6b

[§5](workflow-design.md#sec-5) lets a contradiction stop blocking when it is *acknowledged*, and — as
originally specified — acknowledgment was carrying a caveat on the hypothesis. **The model writes the
hypothesis and its caveats.** So the deterministic stop rule reduces to:

```
"The metrics contradict this conclusion. I acknowledge this contradiction."
→ caveat recorded → contradictions_unresolved = 0 → publish
```

This is the same failure as [G-43](#g-43) one level up, and worse in consequence: an inadmissible
role gets a claim past one check, while a self-granted acknowledgment carries a **known-contradicted**
claim to a human who is being told the system already accounted for it. It also defeats the escalation
contract — a run that should have escalated with the contradiction set attached instead publishes.

Nothing is built wrong yet (the detector does not exist — [G-07](#g-07)), but the *design* sanctioned
the bypass, so building the detector as specified would have shipped it.

**Fix:** [§5](workflow-design.md#sec-5) *Acknowledgment is admitted, never asserted* — the model
proposes; only policy (`value_direction` alone, code-checked preconditions, code-capped confidence,
degraded `disposition`) or a named human (per-contradiction, in the decision payload) admits; and
`acknowledgment_rate` becomes a scored axis (§10). Depends on [G-29](#g-29) and [G-01](#g-01).
Lands with [G-07](#g-07).

<a id="g-45"></a>
#### G-45 — `AzureOpenAI` cannot be the Claude adapter; the providers do not compose · `critical` · Stage 8

§11 named the production LLM path `azure` = `AzureOpenAI`, while the model table
named Claude tiers on Foundry. **These do not compose.** Claude on Microsoft Foundry is served through
Anthropic's **Messages API** (`/v1/messages`, `AnthropicFoundry` client), not the Azure OpenAI
chat-completions surface - a different request/response shape, not a base-URL swap. The deployed demo
runs a gpt-class model through `AzureOpenAI` and works; the *target* Claude tiers cannot use that
adapter at all.

The `ChatModel` seam has therefore only ever been exercised against OpenAI shapes. To carry Claude
it must normalize across both surfaces — the per-concern comparison table is in
[`deployment.md` §11](deployment.md). **Hosting location is a second, separate decision** —
Azure-hosted vs Anthropic-through-Foundry, declared per tier in the §11 profile, not derivable from
the model id.

**Fix:** the `anthropic_foundry` adapter + `ChatModel` normalization
([`adr-model-provider.md`](./adr-model-provider.md)). Interacts with [G-21](#g-21) and
[G-38](#g-38) (mid-run outage now spans two provider surfaces).

<a id="g-46"></a>
#### G-46 — Content Safety is not automatic on the Claude path; the guardrail pipeline is undrawn · `high` · Stage 8/10

The deployment table read as though selecting **Content Safety** gives the model path built-in
guardrails. For Claude on Foundry it does not - Microsoft documents that content filtering must be
configured at the **application level**; it is not provided by default at the model deployment. So the
XPIA/injection defense OpsPilot's threat model depends on (untrusted alert text **and** all retrieved
content) is not ambient - it is application code that must exist and be wired in order.

**Prompt Shields** covers both direct user-prompt attacks and document/indirect (XPIA) attacks, which
is exactly the alert-text + retrieved-content surface - so it is a pipeline stage, not a checkbox.

**Fix:** the ordered application-level guardrail pipeline and "restricted deterministic mode", both
defined in [architecture.md §10](architecture.md#sec-10). Pairs with [G-26](#g-26)
(untrusted-retrieval handling).

<a id="g-47"></a>
#### G-47 — Round-only cancellation cannot hold a hard wall-clock deadline · `high` · Stage 6b

[§2](architecture.md#sec-2) lists "every run terminates inside a deadline" as a bounded-cost quality
attribute, but [§3](architecture.md#sec-3) honors cancellation only **between rounds** and merely says the deadline check must
"account for a full batch's latency." A batch of up to `_MAX_BATCH = 6` concurrent network calls can
exceed any such reserve - so the deadline is *accounted for around* the batch, not *enforced inside*
it, and a single slow tool/MCP call blows the guarantee.

**Fix:** the four-step in-batch deadline rule in [§3](architecture.md#sec-3) (per-call deadlines,
propagated cancellation, partial `timeout` envelopes). Checkpointing at round granularity stays;
cancellation moves inside the batch. Depends on [G-08](#g-08) (per-call timeout/`max_tokens`) and
the [G-17](#g-17) status set (`timeout` result).

<a id="g-49"></a>
#### G-49 — Degraded rungs return non-RCA results under the RCA contract · `high` · Stage 5e

The degradation ladder (§10) is `full agent -> retrieval-only summary -> cached runbook -> escalate`,
but a retrieval-only summary and a cached runbook are **not root-cause reports** - they cite no
diagnosed cause and were never gated by coherence. Returning all four rungs as one apparent
`IncidentReport` makes "degraded RCA" a euphemism for "we couldn't investigate, here's a runbook," and
a consumer can't tell a diagnosis from a briefing without reading prose.

**Fix:** the discriminated `InvestigationResult` union defined in
[`deployment.md` §10](deployment.md). Interacts with [G-36](#g-36) (the escalation reason lives on
`EscalationNotice`) and the [G-42](#g-42)/[G-29](#g-29) typed report shape.

<a id="g-52"></a>
#### G-52 — No temporal isolation; an investigation can see the future · `critical` (eval integrity) · Stage 6a

State carries no `as_of`, and the knowledge/telemetry tool contracts take no temporal bound. Two
failures follow, one per lane:

- **Evaluation leaks the future.** A historical scenario replayed today can retrieve the postmortem
  *written after that incident resolved* — the answer key, handed to the agent as "retrieved
  knowledge." The scorecard then measures memorization, not investigation, and every retrieval-touching
  number is unfalsifiably inflated. (A sharper form of [G-19](#g-19): there the fast path found its own
  answer; here *any* retrieval can pull a future doc.)
- **Production uses corrected knowledge.** A runbook edited after the incident, or a topology changed by
  a later migration, is not what the on-call engineer had — the report is unfaithful to the moment.

**Fix:** the four temporal fields as **mandatory retrieval arguments**, failing closed — the bounds
table is [§4](data-and-evidence.md#sec-4) (*Temporal isolation is a contract*). Blocks honest
scoring — lands with the retrieval seam widening ([G-04](#g-04)) so the seam carries the bounds from
day one. Interacts with [G-56](#g-56) (AI Search adapter honors the same as_of).

<a id="g-54"></a>
#### G-54 — The cassette key is three fields; and replay can't see provider drift · `high` · **5e** (manifest) / **6a** (canary)

The replay key is `(model_id, messages, temperature)`. The recorded response is a function of far
more — the full behavior-affecting set is enumerated in [evaluation.md §10](evaluation.md). Change
any of it and behavior shifts while the key does not — CI replays a response the current inputs
would never produce and **passes green on a lie**.

Separately, replay is deterministic by construction, so it is **blind to live-provider model drift**: a
hosted model that shifts behavior after the record date still produces the same cassette hit.

**Fix ([evaluation.md §10](evaluation.md)):** (1) the **cassette manifest** — **pulled forward to
5e** so that stage's one re-record is keyed correctly, not re-recorded again at 6a; (2) the
**scheduled live-canary eval** — **stays at 6a**. Replay gates *code* changes; the canary watches
the *provider*.

<a id="g-55"></a>
#### G-55 — The known-issue path has no precision / false-fast-path metrics · `medium` · Stage 9

The fast path is scored only by whether it lands the right resolution, which hides *how* it got
there — a too-eager gate that fast-paths a novel incident, or a too-timid one that sends every match
to full diagnosis, both look fine until they don't.

**Fix:** the four known-issue-path axes defined in [evaluation.md §10](evaluation.md), so
[G-09](#g-09) and [G-11](#g-11) become measurable rather than asserted. Requires the near-miss
scenario ([G-35](#g-35)) to exercise the false-positive/false-fast-path cases.

<a id="g-56"></a>
#### G-56 — AI Search "parity" is framed as ranking equality; no embedding-profile versioning · `medium` · Stage 8

The dev pipeline (local dense + BM25 + RRF + cross-encoder) and Azure AI Search hybrid (vector +
full-text + RRF, then semantic rerank over a candidate set) are **different retrieval systems** — the
"relevance parity within a declared tolerance" framing tests ranking equivalence that was never the
goal and can *fail on a better prod ranking*. The contract should be **outcome compatibility**: result
schema, filtering behavior, version/as-of constraints, a **shared** Precision@K/MRR floor (not "within
ε of each other"), and required-target recall.

Separately, `bge-small-en-v1.5` → BGE-M3 is drawn as a config swap, but it changes **embedding
dimensionality and index contents** — the index is incompatible and must be **rebuilt**; a query
embedded with the old model against a new index is nonsense.

**Fix:** outcome-compatibility parity + versioned embedding profiles
([`adr-retrieval-backend.md`](./adr-retrieval-backend.md)). Interacts with [G-52](#g-52) (the
adapter honors as_of).

<a id="g-57"></a>
#### G-57 — No system-level admission control · `high` · Stage 8

The `IterationBudget` bounds one investigation; it does nothing against **500 cheap investigations at
once** — each within budget, together exhausting the model's RPM/TPM, the dispatch queue, and the
approval backlog. Per-run cost control and system admission control are different layers.

**Merged** (#49): the auth + `submit`/`read`/`decide` roles + basic in-flight concurrency slice —
see [G-03](#g-03) for what merged and what remains on ingress. The cap is a best-effort
count-then-create check (`InvestigationRepository.count_active`), not a distributed lock or the
fuller system below.

**Still missing:** an `admin` role; per-user/per-service *quotas* (a rate over time, distinct from
the in-flight cap above); model RPM/TPM admission (reject/queue at the ceiling, not 429-storm
mid-run); queue-depth limits; a max-pending-approvals cap; incident-level access control; audit +
PII-aware Blob/trace retention. The **LangSmith exporter** ([G-61](#g-61)'s sink half) lands here
with the dev-local / synthetic-or-scrubbed trace rules it must obey — placement rationale in
[`adr-observability-tracing.md`](./adr-observability-tracing.md).

**Fix:** the still-missing rows above, per the admission-control table in
[deployment.md §10](deployment.md). [G-03](#g-03) (unauthenticated, uncapped ingress) is now mostly
closed; these remaining rows sit above it.

<a id="g-30"></a>
#### G-30 — Coherence gate runs before the conclusion exists · `high` · Stage 6b

`nodes/investigation.py` calls `compute_sufficiency(...)` at line 229 and
`revise_hypothesis(..., final=stopping)` at line 239. Under `single_agent` the model's real root cause
is synthesized **on the stopping turn, after the gate has already passed** — so a per-round
causal-order or blamed-entity check would evaluate `run_cycle`'s provisional deploy-blaming
placeholder, which the system already knows is a placeholder.

`graph.py` has no edge from `synthesize_report` back to `diagnose`, so there is nowhere for a
post-synthesis failure to go even if it were detected.

**Fix:** the [§5](workflow-design.md#sec-5) two-phase split + bounded back-edge. Depends on
[G-29](#g-29), and on [G-40](#g-40) underneath it: fixing the ordering without fixing the authority
just moves the second opinion later.

<a id="g-34"></a>
#### G-34 — Dispatch is post-response, not durable; and a lease has no fencing · `high` · Stage 5f

[G-02](#g-02) defends the *pause*. The *initial leg* is undefended, interrupted more often, and the
recovery an earlier draft proposed does not hold up.

`POST /investigations` returns `202` and the graph runs as **post-response background work**. Container
Apps' HTTP scaler counts **active HTTP requests, not invisible post-response threads** — so with
`minReplicas = 0` a replica can be reclaimed **mid-round**. Checkpoints bound the damage, but nothing
re-drives the run: the record sits at `running` forever and a poller waits on a state that never
advances. **Post-response execution behind an HTTP scaler is not an honest `202`.**

The two recovery mechanisms the draft offered (startup sweep, resume-on-poll) are each unsound
under scale-to-zero, and a bare lease races its replacement — the analysis is
[§8](workflow-design.md#sec-8) (*Dispatch is durable*).

**Fix ([§8](workflow-design.md#sec-8) — resolves former open decision [§13.2](decisions.md#sec-13)
D):** durable dispatch in v1 (Cosmos transactional outbox → change feed → Service Bus →
queue-triggered worker) + a monotonic fencing epoch checked on every write; `awaiting_approval`
stays exempt from lease expiry.

<a id="g-50"></a>
#### G-50 — Prose `statement` can contradict the typed claim · `high` · Stage 5e

[§4](data-and-evidence.md#sec-4) said `Claim.statement` is "human-readable, for the report — never parsed." That is
a loophole: the deterministic checks validate `causal` (the structured proposition), the human reads
`statement` (the prose), and nothing forces them to agree. A report can carry
`cause_entity = payment-gateway` while the prose says "the checkout deployment caused the outage" — the
gate passes the structure the human never sees, and the human approves prose the gate never checked.

**Fix ([§4](data-and-evidence.md#sec-4)/[§5](workflow-design.md#sec-5)):** `render_report` **renders `statement` from the structured fields**
(deterministic — the direction already set for that node), so the prose cannot introduce or contradict
a claim. Where a build lets the model author prose instead, a **semantic-consistency gate** must reject
prose that adds or contradicts a claim before it reaches a human. Depends on [G-29](#g-29) (typed
claim) and the [G-40](#g-40) one-authority rule (only `render_report` produces report bytes).

<a id="g-51"></a>
#### G-51 — Only the root cause is structured; the rest of the report is ungrounded prose · `high` · Stage 5e

G2 asserts **every** published claim cites tool-produced evidence, but the contract structures only the
top-level root-cause hypothesis. A real incident report also asserts **onset, blast radius, sequence,
contributing factors, ruled-out causes, and recommendations** — and if those are free prose, they are
ungrounded, so the "every claim" guarantee is stronger than the design enforces. `safety_validate`
today has nothing to check them against.

**Fix ([§4](data-and-evidence.md#sec-4)/[§5](workflow-design.md#sec-5)):** a report-level `report_claims: list[ReportClaim]`, each with
`claim_type` (root_cause / onset / blast_radius / sequence / contributing_factor / ruled_out /
recommendation), `support_refs`, and `counter_refs`. `ruled_out` must cite its disqualifying evidence;
`recommendation` is the one class that may cite runbooks/past incidents. `safety_validate` runs the
citation/unsupported-claim checks over **all** of them, not just `causal`. Depends on [G-29](#g-29)
(typed claim) and interacts with [G-05](#g-05) (each `support_ref` validated against `produced_refs`).

<a id="g-35"></a>
#### G-35 — No scenario can fail the new checks; axes pass vacuously · `high` · Stage 6a

The corpus is part of the instrument, and the project already has the proof: `eval/wild.py` runs with
retrieval **fully suppressed** (`_NoRetriever`) and still scores RCA 0.80. Every answer-key scenario's
`expected_evidence` is 100% telemetry refs.

So a [G-06](#g-06) `knowledge_grounding` ablation over the current corpus shows **no delta and the axis
passes** — certifying precisely the disconnection it was built to detect. The same trap applies to
[G-07](#g-07), [G-12](#g-12), and [G-09](#g-09): each needs a scenario where its failure is *possible*.
See §10 for the four required scenario classes.

Carries the standing **n = 7 statistical-power** problem: every rate quantizes to sevenths, so a
`> 0.95` threshold means "7/7" and one scenario flips a metric 14 points. Must be resolved before
Stage 11 arms thresholds as a hard gate.

<a id="g-36"></a>
#### G-36 — Escalation reasons are inferred, and misattributed · `high` · Stage 5e

`safety_validate` returns only `{"safety": {passed, violations}}` — it **never sets `state.error`**.
`escalate()` then *infers* the cause by probing state in order: `state.error` → approval decision →
`diagnose_iters >= MAX_DIAGNOSE_ITERS` → `sufficiency.plan_can_advance` → a generic fallback.

So a **guardrail/citation-gate failure** — a report blocked for unsupported citations — is reported as
`plan_exhausted_insufficient` or `iteration_budget_exhausted`: a confident, specific, wrong reason. It
was already wrong internally; since `#35` exposed `InvestigationResponse.reason` as **API surface**, it
is now a published falsehood, and the operator console renders it verbatim.

**Fix:** blocking nodes **stamp** their reason on state at the moment they block; `escalate()` reports
what it was told rather than guessing. Inference cannot be made correct — any cause the probe doesn't
test for produces a wrong answer.

<a id="g-04"></a>
#### G-04 — Retrieved knowledge never reaches the model · `high` · Stage 6a

The headline claim — "grounded in runbooks and past incidents" — is not a current property. This is a
**seam** gap, not a prompt gap:

- `retrieval/base.py: Hit` is `(doc_id, score, kind)`.
- `tools/contracts.py: DocHit` is `(doc_id, kind, title, services, score)`.

**Neither carries the matched chunk text.** The passage that BM25 and the cross-encoder scored is
discarded before it crosses the tool boundary. Consequences, all live:

1. `retrieve` stores `EvidenceItem.make("runbook", doc_id, hit.title)` — the "content" in state is a
   *title*.
2. `observe.py: _docs` renders a search result as `"{doc_id}: {title}"`, so even when the planner
   *does* call `search_runbooks` (it is in the tool list and passes `is_read_only`), the model
   receives a title and nothing else.
3. The planner and synthesis prompts render only `observation_trail`, which `retrieve` never writes —
   so `retrieve`'s output reaches no model context at all.

Phase 4 took MRR to 0.792 for a pipeline whose output no model reads. Making the search tools
first-class planner actions does **not** fix this alone, because the summarizer has only a title to
render.

**Fix:** `Hit` carries the matched chunk (text + `chunk_id` + offsets); `DocHit` carries a capped
`excerpt`; `observe.py: _docs` renders the excerpt; `EvidenceItem.excerpt` stores it; `retrieve`'s
excerpts reach planner + synthesis context. Ships with [G-06](#g-06) and [G-26](#g-26).

<a id="g-05"></a>
#### G-05 — Grounding is not structurally impossible to forge · `high` · Stage 6a

The citation guardrail's trust model is "a hypothesis may only cite what a tool actually produced" —
but `produced_refs` is an ordinary `Annotated[list[str], merge_refs]` channel any node can write.

- `diagnose` derives it from `result.evidence_refs` — genuinely tool-attested. ✅
- `retrieve` derives it from search hits. ✅
- **`known_issue_fast_path` mints `f"past_incident:{inc_id}"` from `state.matched_incident` and then
  cites that exact ref** — and `get_incident` returns `evidence_refs == []`, so no tool ever produced
  it. `safety_validate` passes it by construction.

That is self-certification: the guardrail's designed-against failure mode occurring inside the
guardrail's own trusted set. Every node added later is another chance to widen it silently.

**A `tool_call_id` field does not fix this** — Pydantic validates *shape*, never *who produced the
object*; [§4](data-and-evidence.md#sec-4) records why the second-review field fix was insufficient.

**Fix ([§4](data-and-evidence.md#sec-4) + [§8](workflow-design.md#sec-8)):** (1) the trusted
`ToolGateway` as the only ledger writer, with `merge_evidence` admitting only ledger-backed handles
— the fast path then fails the gate instead of passing by construction, closing this *and*
tightening [G-09](#g-09); (2) approval binds an `evidence_manifest_hash` alongside `report_hash`,
re-checked at finalize.

<a id="g-06"></a>
#### G-06 — No eval axis joins retrieval to the conclusion · `high` · Stage 6a

`data/answer_key/scenarios.yaml` carries `expected_evidence` (100% `logs:`/`metrics:`/`deploys:`/
`deps:`) and `expected_retrieval` (KB doc ids) as **separate** fields. `scenario_eval.py` scores
`evidence_recall` against the first only; retrieval MRR scores the second against the retriever in
isolation. **Nothing joins them.**

So [G-04](#g-04) is invisible to every published number: retrieval could be deleted from the
diagnosis path and the scorecard would not move. Any claim that the system is "grounded in runbooks
and past incidents" is therefore currently unfalsifiable.

**Fix:** the `knowledge_grounding` axis + retrieval-suppressed ablation defined in
[evaluation.md §10](evaluation.md). **Land this before the [G-04](#g-04) fix**, so the fix is scored
on the property it claims, and before Stage 11 arms thresholds.

<a id="g-07"></a>
#### G-07 — Two sufficiency dimensions are constants · `high` · Stage 6b

`diagnosis/sufficiency.py` returns `contradictions_unresolved=0` and
`unresolved_critical_questions=0` **unconditionally**, with a comment deferring them to "the LLM
loop", which never populates them. `SufficiencyState` is constructed in exactly one place, so this is
total.

The *effective* built stop rule is therefore `evidence_coverage >= required and citation_coverage ==
1.0` — a pure **coverage** test, which by construction cannot fail a hypothesis that is well-cited and
wrong. inc-004 is the standing proof: grounded, fully covered, and false, and the gate passes it.

The resolved-vs-acknowledged contradiction semantics in [§5](workflow-design.md#sec-5) are sound design with
**no component behind them**. Batching-per-round ([G-22](#g-22)) also removed the per-action seam
where such a check would naturally run.

**There is a test, and it gives false assurance.**
`tests/test_sufficiency.py::test_ready_only_when_every_dimension_passes` asserts
`_suff(contradictions_unresolved=1).ready is False` — so the truth table *is* covered and the gate
logic *does* honor the dimension. But the test constructs a `SufficiencyState` **directly** with a
value `compute_sufficiency` can never emit. The test passes, the dimension is exercised, and the
production path is unreachable. This is why the stage that claimed to deliver contradiction handling
(Stage 2) reads as complete: the assertion is real, the producer is not.

**Fix:** the deterministic detector specified in [§5](workflow-design.md#sec-5), run per round — plus a test
that drives `compute_sufficiency` end-to-end rather than hand-constructing the state.

<a id="g-08"></a>
#### G-08 — Iteration budget is a call count only · `high` · Stage 6b

`MAX_DIAGNOSE_ITERS` bounds diagnose rounds. `MAX_TOOL_CALLS` is defined in `config.py` and **read
nowhere**. There is no token, cost, or wall-clock cap anywhere in the codebase.
`ChatMessage.usage` (`llm/base.py`) is captured per call but read **only** by the cassette recorder —
the graph never accumulates it, so no code path *could* enforce a cap even if the field existed.

Live, not future: `single_agent` (up to 6 batched calls × up to 5 rounds + synthesis, uncosted)
already runs on Azure OpenAI. Submit/read gained Entra authentication and a basic concurrency cap in
#49 (merged), but neither bounds *cost per accepted call* — that gap is this one, not
[G-03](#g-03) — and the sync `/investigate` endpoint is still fully open (its own remaining share
of G-03).

**Dead config to remove in the same change:** `CONFIDENCE_THRESHOLD` (`config.py`) is read nowhere —
a leftover from the pre-Stage-2 confidence-gated stop rule (R-05), still sitting in the config surface
as though it governs something. `MAX_TOOL_CALLS` is the same shape. A config constant nothing reads is
indistinguishable from one that is enforced, which is the pattern this gap is about.

**Fix:** `IterationBudget` with token/cost/deadline fields, accounted **per round** (see
[G-22](#g-22)), fed by `ChatMessage.usage`; delete or wire the two dead constants.

<a id="g-10"></a>
#### G-10 — `info_only` bypasses the citation gate entirely · `high` · Stage 6c

`triage.v1.md` offers `info_only` to the model and `TriageResponse` accepts it, so the deployed
`single_agent` triager can set it today. `route_by_intent` sends it to `synthesize_report` — there is
no `service_answer` node — where `safety_validate` exempts it from the citation gate **wholly** rather
than scoping the exemption to a safe deterministic reply path. The auto-approve stub then publishes
the result.

`info_only` was specified as deterministic *service* questions only ("what is the status of
investigation X?"). As built it is a general ungrounded-output escape hatch.

<a id="g-11"></a>
#### G-11 — Known-issue `rca_correct` scores the answer key · `high` · **Stage 9** *(was Stage 11)*

> **Re-targeted to where its inputs already change.** Stage 9 replaces `known_issue_fast_path` with
> the candidate + verification flow, which alters exactly the citations `_implicated_entity` reads —
> so the scorer has to be revisited there regardless. Leaving the fix at Stage 11 means five stages of
> baselines ratcheting on a number that scores the answer key against itself.

`scenario_eval.py`'s `_implicated_entity` falls back to `root_by_incident.get(matched_incident)` when
a report carries no metrics/deps citations — true for **every** known-issue fast-path run, since
`known_issue_fast_path` only ever cites `past_incident:{id}`. So `rca_correct` for a known-issue
scenario is scored against the **answer key's own stored root for the matched incident**, not against
anything the graph produced. With the deterministic triager matching an incident only to itself
([G-19](#g-19)), this is close to a tautology.

**Fix before arming thresholds at Stage 11**, or the known-issue axis gates on an inflated number.

### Medium

<a id="g-31"></a>
#### G-31 — `request_more_evidence` has no state machine · `medium` · Stage 5f

`approve`, `edit`, and `reject` all terminate or loop inside the publication half of the graph.
`request_more_evidence` is the **only decision that re-enters the agentic core**, and nothing defines
where it lands, what seeds the plan, or what happens to the budget. Today `after_approval`'s
fail-closed else-branch sends it to `escalate` — a safe default that is also not the advertised
behavior, since [§5](workflow-design.md#sec-5) lists it as a reviewer option.

The budget question is the sharp one: continuing invites instant re-escalation (the budget is why it
stopped), resetting is **budget laundering** — an unbounded-spend path through a human who need not be
authenticated ([G-01](#g-01)). Positions in [§8](workflow-design.md#sec-8).

<a id="g-39"></a>
#### G-39 — Four smaller defects (bundle) · `low` · Stage 10

Tracked together; none justifies its own id, all are small and independent.

| | Defect |
|---|---|
| **a** | **`OPSPILOT_RETRIEVAL_BACKEND=rerank` silently runs hybrid.** `retrieval/factory.py` lists `rerank` in `_VALID` but dispatches `if backend in ("hybrid", "rerank")` to the same builder. The app then fails readiness with a misleading `RETRIEVAL_INITIALIZATION_FAILED` because `retrieval_backend != RETRIEVAL_BACKEND`. Either wire rerank or reject it at config time — the current state is the worst of both. |
| **b** | **Hand-rolled `strptime` in recency weighting.** `tools/search.py` parses `opened_at` with `datetime.strptime(..., "%Y-%m-%dT%H:%M:%SZ")` — the exact hand-rolled-timestamp anti-pattern the code guidelines memorialize, and it silently returns `None` (dropping recency weighting) for any other valid ISO-8601 form. |
| **c** | **`_env` strips `#` from values.** Deliberate and documented — it keeps a `.env` inline comment from poisoning config — but it also mangles any secret containing `#`. Narrow the parse to require preceding whitespace rather than removing the behavior. |
| **d** | **No per-call timeout or `max_tokens`** on model calls (`llm/client.py` passes only `temperature`). Folded into [G-08](#g-08)'s fix: a wall-clock budget is unenforceable without a per-call timeout beneath it. |

<a id="g-16"></a>
#### G-16 — Truncation desyncs records from their refs · `high` · **Stage 6a** *(was medium / Stage 10)*

`run_tool` (`tools/errors.py`) truncates `records` to `MAX_RESULTS` but returns `evidence_refs`
computed from the **untruncated** list. A citation can therefore reference a record the run never
surfaced — breaking the exact guarantee the citation gate depends on.

> **Re-targeted: this must precede or co-land with [G-05](#g-05).** G-05 makes the grounding set a
> derivation from tool envelopes at one choke point. If the envelopes still contain phantom refs to
> truncated-away records, **the choke point faithfully attests garbage** — and a derivation that
> launders bad inputs is more dangerous than the convention it replaced, because it *looks*
> authoritative. The derivation is only ever as trustworthy as the envelopes feeding it.

**Fix:** derive `evidence_refs` from the truncated records, or truncate both together.

<a id="g-17"></a>
#### G-17 — Malformed source rows drop silently, status stays `ok` · `medium` · Stage 10

Every tool's row loader (`tools/logs.py`, `tools/deployments.py`, …) catches row-construction errors
and `continue`s with no count, log line, or metadata flag — locked in by
`tests/test_tools.py::test_malformed_row_is_skipped_not_fatal`. A 90%-corrupt source returns a clean
`status="ok"` on the remaining 10%, and nothing downstream can tell the evidence window is mostly
missing.

**Fix:** covered by the resolved seven-state status set ([§6](data-and-evidence.md#sec-6),
[§13.1](decisions.md#sec-13)) — a malformed subset yields `status="partial"` + `rows_invalid`, never
a silent `ok`. This gap tracks wiring the producers, and stays `medium` because the corruption case
is bounded.

<a id="g-18"></a>
#### ~~G-18 — Deploy window admits a post-onset deploy as causal~~ · **CLOSED #44** → [R-18](#4-resolved)

> **Kept for the record; no longer current.** The clamp shipped in `#44` (`diagnosis/cycle.py`, `pre_onset = [d for d in result.results if d.ts <= onset_dt]`, gated by `tests/test_cycle_onset_clamp.py`). The description below is what was wrong, in the tense it was written.

> **Re-graded by this register's own severity definition.** The entry below states that a composition
> failure can *silently produce a fabricated causal claim* through the auto-approved deterministic
> floor. Fabricating causation and publishing it is not a `medium`. The fix is a one-line clamp
> (`d.ts <= onset`), so there is no cost argument for carrying it five more stages behind work that
> depends on nothing.

`diagnosis/cycle.py` queries deployments out to `onset + 15 minutes`, then picks
`max(result.results, key=lambda d: d.ts)` and writes it as having "preceded onset" **without checking
`d.ts < onset`**. A deploy that landed after symptoms began can be written into the hypothesis as
causal.

This is the deterministic floor's own reasoning bug, and it matters operationally because the floor is
the auto-approved fallback whenever `single_agent`'s model composition fails — a composition failure
can silently produce a fabricated causal claim. Generalizes to the causal-order contradiction check in
[G-07](#g-07).

<a id="g-19"></a>
#### G-19 — `search_past_incidents` can retrieve its own answer · `medium` · Stage 9

No `as_of` cutoff and no current-incident exclusion, so a scenario's own postmortem is retrievable
against itself — the deterministic triager's self-match depends on exactly this. The verification node
([G-09](#g-09)) must not be satisfiable by a self-lookup, so close this in the same stage.

<a id="g-59"></a>
#### G-59 — Readiness probe 503s on dependency health, contradicting run-level degradation · `medium` · Stage 8

`GET /health/ready` returns 503 until corpus + repository + logs + retrieval **all** pass (the
[deployment §12](deployment.md#sec-12) infra table). That contradicts the settled degradation semantics
([§10](architecture.md#sec-10) guardrails): a retrieval or telemetry outage is supposed to *degrade a
run* (continue with disclosure), not take the whole replica out of the load balancer. As written, a
downstream dependency blip 503s every replica and fails the deploy gate — converting a
degrade-with-disclosure condition into a hard outage.

**Fix (Stage 8, the readiness split):** `/health/ready` narrows to "can accept and track work"
(repository + checkpoint only); telemetry / retrieval / model / MCP health move to
`/health/dependencies`, which feeds run-level degradation instead of readiness. Surfaced by the
2026-07 third review.

### Low / accepted

<a id="g-26"></a>
#### G-26 — Untrusted-retrieval guardrail defends an empty set · `low` · Stage 6a

§10 states that all retrieved content is treated as untrusted data (delimited,
embedded instructions never followed). Today that control has nothing to defend: no retrieved passage
text reaches a model ([G-04](#g-04)).

It becomes load-bearing the moment the seam widens — so the delimiting / untrusted-data handling
**ships in the same change as [G-04](#g-04)**, not deferred to Stage 10. Widening the seam without it
creates exactly the exposure the guardrail was written for. Telemetry results (log messages in
particular) are attacker-influenceable too and get the same treatment.

<a id="g-28"></a>
#### G-28 — Demo script asserts four behaviors that do not run · `medium` · per-gap

`execution-plan.md`'s **Final demo path** is the most externally-visible artifact in the project, and
four of its beats currently describe behavior the system does not exhibit:

| Demo beat | Blocked by |
|---|---|
| Demo 1: "retrieves runbooks → finds payment-api timeout" — implies retrieval *contributed* to the finding | [G-04](#g-04); the finding comes from telemetry alone, retrieval only supplies a citation |
| Demo 1: "pauses for approval → finalizes" — pauses *authentically* (#36, [G-01](#g-01) closed) but **not durably** | [G-02](#g-02) |
| Demo 2: "matches prior postmortem → **verifies signals** → uses known resolution" | [G-09](#g-09); no verification node exists, and the match may be a self-lookup ([G-19](#g-19)) |
| Demo 3: injection inside a **retrieved runbook** is blocked | [G-26](#g-26); no retrieved passage text reaches a model, so there is nothing to inject into |

Tracked as its own gap because a demo is a *claim*, and rehearsing one of these live is how an
unsupported claim gets made in front of an audience. Closes automatically as its constituent gaps
close — until then, each demo beat in `execution-plan.md` carries a one-line precondition pointer
back to this entry.

<a id="g-61"></a>
#### G-61 — Observability emission seam (spans + usage) · `medium` · **Stage 8** *(sink)* — emission half **closed**

> **Stage 5g is closed** (2026-07-26): #46 `1385be2` + #48 `ecff925`, both merged and deployed green.
> The **gap stays open** on the two pieces that were never 5g scope — the LangSmith sink (Stage 8) and
> the MCP span (Stage 7). Stage closure and gap closure are different statements; the register tracks
> the gap, the roadmap tracks the stage.

The emission seam is built (§23): a span-emitting wrapper at the **node dispatch path** (#46, merged),
`run_tool` (#48), and the **`ChatModel` client** with normalized usage capture (#48). `trace_id` is
propagated onto state (`ingest`) and down the call tree via a contextvar, so tool/model spans nest
under the node span. `none`/`memory`/`stdout` exporters + an in-memory-exporter fixture ship; spans are
not behavior-affecting → **zero re-record**. This satisfies
[code-guidelines §22.5](code-guidelines.md#22-definition-of-done-per-step)'s "traces exist" for merged
work. `OPSPILOT_TRACE_EXPORTER` defaults to `none`, so the deployed revision carries the seam but emits
nothing until a sink is selected — which is what the Stage-8 exporter is for.

**Two pieces deliberately deferred — each now has a destination stage:**
- **The MCP wrapper is Stage 7, not 5g.** There is no MCP *client* in the runtime — the graph binds
  tools in-process (through the traced `run_tool`); MCP exists only as a CI parity scaffold. The MCP
  span rides the Stage-7 MCP promotion, reusing `span()`.
- **The LangSmith Developer sink lands at Stage 8.** `stdout` already emits the OTLP-shaped spans
  locally, so nothing is blocked; the exporter swap touches no emission site. Stage-placement
  rationale: [`adr-observability-tracing.md`](./adr-observability-tracing.md).

Concretely, what remains open on G-61 after #48 is: the LangSmith exporter (Stage 8) and the MCP span
(Stage 7). Nothing else.

The **aggregation half** (App Insights export, dashboards, `CostTracker`, live canary, arming the hard
gate) stays at Stage 11; usage *enforcement* is [G-08](#g-08) at 6b (this is capture only).

---

## 4. Resolved

| ID | Gap | Closed by |
|---|---|---|
| R-01 | **Async investigation identity was fragmented.** `POST /investigations` minted its own `investigation_id`; the background job separately minted `f"investigate-{uuid4()}"` as the checkpointer `thread_id`; `ingest()` minted a **third** unrelated pair in state. Resume-by-polled-id was impossible. | Stage 5c — one id spans poll id, `thread_id`, and `state.investigation_id`; `ingest()` honors a caller-supplied id. |
| R-02 | **`hitl_gate` was an auto-approve stub.** No real pause; the async worker drove every run to a terminal state, so a review step could not exist. | Stage 5c — real `interrupt()`, `awaiting_approval` status, decision endpoint, `Command(resume=...)`. |
| R-03 | **A stale approval could be applied to a superseded report.** | Stage 5c — inbound `submitted_report_hash` comparison → `stale_rejected` → `escalate`. Outbound half closed separately as R-07. |
| R-04 | **Re-entered diagnose loop appended the same evidence ref 5×.** Blind-append `list + operator.add` channels. | Stage 2 (#17–#20) — keyed `evidence_by_id` with a content-hash dedup reducer. |
| R-05 | **Stop rule was a model-confidence threshold.** The model decided when it was done. | Stage 2 — deterministic sufficiency gate; confidence recorded on the hypothesis, never the trigger. Two of its four dimensions remain unimplemented as [G-07](#g-07). |
| R-06 | **Deploy shipped on push to `main` untested.** | Stage 1 (#16) — ruff + mypy + `core`/`full` lanes as required checks. |
| R-07 | **Approval hash unasserted on the outbound side** (was G-13). `finalize_report` returned `state.report` unconditionally; the byte-exactness guarantee was a comment, not a check. | `2bad319` — `finalize_report` raises `RuntimeError` when `approved_report_hash != report_hash`. Deliberately kept even though `after_approval` should make it unreachable: a future routing change must fail loudly, not publish silently. |
| R-08 | **Idempotency ignored reruns and raced** (was G-14). Check-then-act `find_by_idempotency_key()` + `create()`; key had no version or rerun override. | `2bad319` — atomic `get_or_create`, `WORKFLOW_VERSION` folded into the key, and `?force_rerun=true` for a reopened incident (the superseded investigation stays reachable by its own id). |
| R-09 <a id="g-01"></a> | **Decision endpoint had no reviewer identity** (was G-01). `approver` was a client-supplied free string; the endpoint had no auth, so a forged approval was indistinguishable from real human review — the HITL gate controlled nothing. | Stage 5c (#36) — the endpoint validates an Entra token, derives `approver` from the verified principal, and stamps `auth_method`/`kind` from the proven identity (401/403 otherwise). The reviewer-identity design is [`adr-reviewer-identity.md`](./adr-reviewer-identity.md). |
| R-10 <a id="g-15"></a> | **Smoke gate did not cover the async pause path** (was G-15). `scripts/smoke_deployment.py` asserted the deterministic auto-approval on the sync `/investigate` path, so the real interrupt shipped ungated. | Stage 5c (#36) — the smoke gate drives 202 → pause → authenticated decision → resume when `OPSPILOT_SMOKE_AUDIENCE` is set. *(Runs green only once the blocked deploy is fixed — see the header note.)* |
| R-11 <a id="g-23"></a> | **Console had no decision controls** (was G-23). #35 shipped view-only, on the stated condition that controls land once the real `interrupt()` did. | Stage 5c (#36) — `console.html` renders `awaiting_approval` + `pending_decision` and submits approve / edit / request-more-evidence / reject to `POST /investigations/{id}/decision` behind an MSAL-style PKCE sign-in with an approver-role check; the disclosure banner now shows only when no Entra console client is configured. *(The `request_more_evidence` backend state machine remains [G-31](#g-31), 5f.)* |
| R-12 <a id="g-29"></a> | **Conclusion was prose; nothing typed for the checks to interrogate** (was G-29). `Hypothesis.statement` was free text and `SynthesisResponse.root_cause` a bare string, so every conclusion-level check in [§5](workflow-design.md#sec-5) had no contract to run against. | Stage 5e (#50) — the model PROPOSES `causal`/`report_claims`; `diagnosis/admission.py` ADMITS them into the strict `CausalClaim`/`ReportClaim` or refuses. Refused when the entity resolves against nothing this run touched, or when no proposed support ref was produced; an unrecognised `cause_type` degrades to the contract's own `unknown`. An unadmitted claim degrades the run rather than publishing a structure nothing verified. |
| R-13 <a id="g-49"></a> | **Degraded rungs returned non-RCA results under the RCA contract** (was G-49). A consumer could not tell a diagnosis from a briefing without reading prose. | Stage 5e (#50) — `_build_outcome` classifies a terminal run into the typed `InvestigationResult` union and the API surfaces `outcome.result_type`. Only a run carrying an admitted `CausalClaim` is `grounded_rca`; a completed run without one is `partial` (where the deterministic floor lands by design); `info_only` is a `knowledge_briefing`, never an RCA. |
| R-14 <a id="g-50"></a> | **Prose `statement` could contradict the typed claim** (was G-50). The gate validated the structure, the human read the prose, and nothing forced them to agree. | Stage 5e (#50) — `diagnosis/render.py` builds the sentence by template substitution over the admitted fields, so the entity is only ever interpolated from `claim.cause_entity`. The model's own prose stands only when nothing was admitted, and then it carries no claim to contradict. |
| R-15 <a id="g-51"></a> | **Only the root cause was structured; the rest of the report was ungrounded prose** (was G-51), so the "every published claim cites tool-produced evidence" guarantee was stronger than the design enforced. | Stage 5e (#50) — `report_claims` live INSIDE `IncidentReport`, so they are part of the bytes the approval hash binds, and `safety_validate` checks their support refs alongside the headline citations. `recommended_next_step` is now rendered from a derived `recommendation` claim instead of the hard-coded rollback string (a §21 prohibited pattern). |
| R-16 <a id="g-36"></a> | **Escalation reasons were inferred, and misattributed** (was G-36). `escalate()` probed state in a fixed order, so a guardrail block (which set nothing) surfaced as `plan_exhausted_insufficient` or `iteration_budget_exhausted` — published via `InvestigationResponse.reason` since #35. | Stage 5e (#50) — every path into `escalate` stamps its own cause at the moment it blocks (`diagnose`, `safety_validate`, `hitl_gate`); `escalate` reports the stamp verbatim. An empty stamp is a caller defect and reports `unattributed_escalation` rather than a plausible guess. Gate test constructs state that would ALSO satisfy both old budget probes, so a wrong attribution is observable. |
| R-17 <a id="g-62"></a> | **`Submitter`/`Reader` app roles existed in config but not in Entra** (was G-62). `#49` gated submit on a role that was never created on the API app registration, so `require_submitter` (a strict single-role check) rejected every principal and no investigation could be started in production. Reads and decisions kept working, because `require_any_role` was satisfied by the existing `Approver`, which is why it hid. | 2026-07-27 — `Submitter` (`9b3129f9-…`) and `Reader` (`b03c93fc-…`) added to the `opspilot-api` app registration, preserving `Approver`'s id so existing assignments survived; `Submitter` assigned to `opspilot-github-oidc`. Deploy green on the re-run. **`Reader` is deliberately unassigned** — `require_reader` accepts read/submit/decide, so it is a placeholder for a future audit or dashboard principal. |
| R-18 <a id="g-18"></a> | **Deploy window admitted a post-onset deploy as causal** (was G-18). `diagnosis/cycle.py` queried deployments out to `onset + 15min` and took a plain `max(..., key=d.ts)`, writing it up as having "preceded onset" without checking it actually did — so a change that landed *after* symptoms began could be published as the cause. A fabricated causal claim, reachable through the auto-approving deterministic path. | Stage 5e (#44) — clamped to `d.ts <= onset_dt`; when nothing precedes onset the hypothesis cites no deploy at all rather than blaming a later one. Gated by `tests/test_cycle_onset_clamp.py`. *(Register bookkeeping lagged: the gap stayed listed as open until 2026-07-27.)* |
| R-19 <a id="g-02"></a> | **A paused investigation was not durable** (was G-02). `OPSPILOT_CHECKPOINTER` defaulted to an in-process `MemorySaver` and the repository was in-memory, so an `awaiting_approval` run — by design the one that sits idle long enough to be scaled to zero — was lost on any restart, and a poll could land on a replica that never saw it. | Stage 5f slice 1 (#51, + the `id` fix in #52) — both stores on Cosmos, keyless; the database and three containers declared in Bicep with the partition keys their clients write, because the app holds a DATA-plane role and cannot create containers. **Verified live 2026-07-28:** the smoke gate restarts the active revision mid-pause, confirms the run is still `awaiting_approval` with an unchanged report hash, then approves and resumes to `completed`. |
| R-20 <a id="g-32"></a> | **Decision-resume failure semantics were undefined** (was G-32). `submit_decision` checked the status, transitioned to `running`, then scheduled the resume: three steps over the same state, so two concurrent decisions could each observe `awaiting_approval` and both resume the graph, and a client retrying a timed-out POST had nothing to retry against. A stale `submitted_report_hash` escalated the run, spending a human's paused investigation on what is only a lost race. | Stage 5f, PR A — `repo.commit_decision` records a `CommittedDecision` **and** moves `awaiting_approval → running` in ONE conditional write (one lock acquisition in-memory, one ETag `replace_item` on Cosmos), deciding the replay lookup and both preconditions against the state it commits against. `decision_id` is client-minted and required; a same-body retry replays the committed 202 and resumes nothing, a different body is 409 `decision_conflict`, and the fingerprint covers the verified reviewer so another identity reusing a key is a conflict, not a replay. A stale hash is now 409 `stale_report` + the current hash with the run **left `awaiting_approval`**. [§8](workflow-design.md#sec-8) updated with it. |
| R-21 <a id="g-37"></a> | **Checkpointer + singleton concurrency** (was G-37). Five lazy globals in `api.py` used unguarded `if x is None: x = build()`, so two concurrent first requests could each open a second `CosmosClient` and checkpointer against the same containers; and the SQLite checkpointer hands one `check_same_thread=False` connection to every run in the process. | Stage 5f, PR A — double-checked locking around all five singletons, the unlocked read staying the fast path. The SQLite half was **investigated rather than rewritten**: `SqliteSaver` already serializes every access to that connection under its own lock, and this runtime reports `sqlite3.threadsafety = 3`. Measured, not assumed — stub the lock out and 8 threads driving the saver all fault with `InterfaceError`, so the third-party lock is load-bearing. Per-run connections were rejected (contention, not correctness, and a proxy impersonating `sqlite3.Connection` for a dev/CI-only path). Pinned by `test_concurrent_threads_share_one_sqlite_saver`, verified to fail when the lock is stubbed. |
| R-22 <a id="g-58"></a> | **Publication was not idempotent** (was G-58). LangGraph re-executes an interrupted node from the top, so a checkpoint-recovered run re-runs `finalize_report` and republishes — latent only until at-least-once dispatch ([G-34](#g-34)) makes the replay real, which is why this had to land before it, never after. | Stage 5f, PR A — `finalize_report` stamps a `publication_id` **derived** from `(investigation_id, report_hash)`, never minted, so a re-execution presents the key the first pass already committed; `repo.publish` commits the terminal result under it at most once (no duplicate result, no duplicate history entry) and fails closed on a *different* id rather than replacing the bytes an approval was bound to. Binding to `report_hash` keeps an `edit`'s different approved bytes a genuinely new publication instead of a suppressed replay. |
