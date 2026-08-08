# OpsPilot — Glossary

**Part of the OpsPilot architecture set.** The frozen citation-ref grammar and the shared vocabulary used across the architecture set.

> **Document map & `§N` resolver:** the map in [`architecture.md`](./architecture.md).

---

## Appendix D — Glossary

**Evidence reference grammar** — the frozen citation vocabulary. Every citable ref is one of:

| Form | Meaning |
|---|---|
| `logs:<service>:<event_id>` | A specific log event |
| `metrics:<service>:<metric>@<ts>` | A specific metric sample |
| `deploys:<service>:<deploy_id>` | A specific deployment |
| `deps:<from>-><to>` | A dependency edge |
| `runbook:<doc_id>` | A KB runbook or architecture doc |
| `past_incident:<incident_id>` | A historical postmortem |

The prefix is the **evidence class**, which is what severity-scaled coverage counts ([§5](workflow-design.md#sec-5)).

> **A ref identifies an observation; it does not describe it.** Deterministic checks read the typed
> evidence the ref resolves to ([§4](data-and-evidence.md#sec-4)), never the ref string. One consequence is already visible in the
> grammar: `metrics:<service>:<metric>@<ts>` addresses a *point*, but an aggregated sample is a
> *window*, so `<ts>` must be the window's start and the sample's `window_end`/`aggregation` must come
> from `MetricEvidence` — two refs that differ only in aggregation over the same start are different
> facts. Extending the grammar to carry the window is deliberately **not** the fix: refs are frozen,
> cited in reports, and stored in the answer key; the facts belong on the evidence
> ([G-42](./status.md#g-42)).

**KB doc ids are a second, distinct namespace.** The retrieval corpus addresses documents as
`runbook:<doc_id>` and `postmortem:<incident_id>` — that is what `search_past_incidents` returns and
what triage surfaces as a *candidate* match ([§5](workflow-design.md#sec-5)). `runbook:` is spelled the same in both namespaces;
`postmortem:` is **not** — the citable form of a historical incident is `past_incident:<incident_id>`.

> The rename between namespaces is a live defect surface, not a cosmetic difference: the fast path
> mints `past_incident:<id>` by string-rewriting a `postmortem:<id>` doc id no tool ever produced,
> which is one half of [G-05](./status.md#g-05). Any code that crosses the two must go through an
> explicit mapping, never a prefix swap.

| Term | Meaning |
|---|---|
| **Grounding set** (`produced_refs`) | The refs a tool actually produced during this run. A citation outside it is unsupported by definition. |
| **Gathering sufficiency** | The deterministic gate deciding whether the loop is *allowed to stop gathering* — evidence classes, independent observations, critical questions, plan advancement, funded reserve. Looks at no conclusion. |
| **Conclusion validation** | The deterministic checks that run *after* synthesis — ref resolution, role admissibility, causal order, entity support. Together with the gate above these were once one expression; splitting them is what makes both implementable ([§5](workflow-design.md#sec-5)). |
| **Claim** vs **candidate** | A *candidate* hypothesis steers the loop's next batch and is never cited, rendered, or graded. The **claim** is the run's single conclusion, written once by `synthesize_claims`. |
| **Plan advancement** | Whether any not-yet-answered question remains. A re-entered loop that cannot advance must stop, not spin. |
| **Intent** | `known_issue` · `novel_investigation` · `info_only` — the triage classification that selects a route. |
| **Severity** | `SEV1`–`SEV4`. Scales the sufficiency bar and (target) the model tier. Revisable upward mid-run. |
| **Candidate** vs **verified match** | Triage surfaces a *candidate* past incident; only a signal check makes it a match. A score alone is never confirmation. |
| **Deterministic floor** | The retained non-LLM implementation the agent must beat, and the fallback when model composition fails. |
| **Cassette** | A recorded request→response map that lets a non-deterministic LLM eval gate CI with no API call. |
| **Resolved** vs **acknowledged** | *Resolved* = later evidence discriminated between the readings. *Acknowledged* = the tension stands and the claim is published anyway — admissible only by policy (narrow kinds, below SEV1, both sides cited, confidence capped, `disposition` degraded) or by a named reviewer accepting that specific contradiction. Never by the model. |
| **Disposition** | `conclusive` · `qualified` · `inconclusive`. Derived from the caveat set, never asserted — a claim carrying an acknowledged contradiction cannot present as a settled root cause. |
| **`InvestigationResult`** (degraded vs escalated) | The discriminated union every run returns: `GroundedRcaReport` (a real diagnosis) · `PartialInvestigationReport` / `KnowledgeBriefing` (*degraded* — completed with disclosed missing evidence) · `EscalationNotice` (*escalated* — handed to a human with a machine-readable reason). Neither degraded nor escalated is ever silent, and neither presents as an RCA — the distinction is typed, not a flag (§10, [G-49](./status.md#g-49)). |
