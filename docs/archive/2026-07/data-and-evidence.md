# OpsPilot — Data & Evidence

**Part of the OpsPilot architecture set.** The state model, the typed evidence union, the citation grammar, temporal isolation, the grounding gateway, and the tool/retrieval contracts.

> **Document map & `§N` resolver:** the map in [`architecture.md`](./architecture.md).

---

<a id="sec-4"></a>
## 4. State model

> **Status:** `deployed` — Pydantic state, separated ids, keyed evidence · `proposed` — typed hypothesis,
> `excerpt`, `tool_call_id`, severity revisions · gaps: [G-20](./status.md#g-20)

LangGraph state is the contract between nodes. It is **versioned and typed** (Pydantic models, not
free `dict`s) so schema validation is real rather than decorative, and reducers define how concurrent
writes merge.

```python
from typing import Annotated, Literal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

Severity = Literal["SEV1", "SEV2", "SEV3", "SEV4"]
Intent   = Literal["known_issue", "novel_investigation", "info_only"]

class EvidenceEnvelope(BaseModel):
    """Provenance and identity. Shared by every evidence type; carries no domain facts."""
    evidence_id: UUID
    ref: str                    # frozen ref grammar (Appendix D)
    source_system: str
    retrieved_at: datetime
    handle: ToolResultHandle    # provenance: the gateway's receipt for the run that produced this.
                                # A node cannot forge one — it only ever holds handles execute()
                                # returned. merge_evidence drops any item whose handle does not
                                # resolve to a tool_ledger record. Grounding derives from THIS.
    raw_reference: str          # pointer to the full payload in Blob (not inlined)
    excerpt: str                # capped snippet kept in state — the text the model actually
                                # reads. Requires Hit/DocHit to carry passage text (§6).
    content_hash: str           # dedup + integrity key

class InvestigationState(BaseModel):
    schema_version: Literal["1.0"] = "1.0"

    # identifiers — separated (see §13)
    incident_id: str
    investigation_id: UUID
    workflow_version: str
    idempotency_key: str

    # TEMPORAL ISOLATION — mandatory, not optional (§6, §11). Every retrieval and topology read is
    # bounded by these so an investigation can only ever see what existed when it began. Without them,
    # eval retrieves future postmortems and prod uses knowledge corrected after the fact (see below).
    investigation_as_of: datetime      # the run's logical "now"; nothing dated after this is visible
    knowledge_cutoff: datetime         # docs/postmortems must predate this (usually == as_of)
    topology_version: str              # the dependency/config snapshot valid at as_of
    corpus_snapshot_id: str            # the immutable retrieval-index generation the run reads

    alert: NormalizedAlert
    # severity is REVISABLE (§5): triage sets it from the incident record, and the loop may raise
    # it once dependency evidence reveals the real blast radius. Monotonic upward, and every
    # revision is recorded — it changes the sufficiency bar the run is judged against.
    severity: Severity | None = None
    severity_revisions: list[SeverityRevision] = []   # (from, to, trigger_refs, at)
    category: str | None = None
    intent: Intent | None = None
    candidate_incident: str | None = None       # a *candidate* past match, not yet verified

    # THE TOOL LEDGER — append-only, written ONLY by the ToolGateway (see below), never by a node.
    # Each record is the gateway's attestation that a tool actually ran with given args and produced
    # a given result. A node cannot forge one because a node cannot write this channel at all.
    tool_ledger: Annotated[dict[str, ToolExecutionRecord], append_only_ledger] = {}

    # keyed collections — dedup by content hash, not blind append.
    # NOTE the key is `content_hash`, NOT `evidence_id`: two tools observing the same row must
    # collapse to one entry, which a per-observation UUID would not do. `evidence_id` identifies
    # the observation; the hash identifies the fact. (The name is historical — code and doc agree.)
    # merge_evidence ADMITS an item only if its `handle` resolves to a tool_ledger record whose
    # result_hash covers it — evidence with a dangling or forged handle is DROPPED, not stored.
    evidence_by_id: Annotated[dict[str, Evidence], merge_evidence] = {}   # Evidence = the union below
    # NOT a writable channel: the grounding set is a projection over LEDGER-BACKED evidence only.
    # produced_refs = {e.ref for e in evidence_by_id.values() if e.handle in tool_ledger}

    # A candidate steers the NEXT batch and nothing else: never cited, never rendered, never graded.
    # `claim` is the run's one conclusion, written only by synthesize_claims (§5).
    candidate_hypotheses: list[CandidateHypothesis] = []
    claim: Claim | None = None
    # the deterministic gathering gate (§5) computes these inputs each turn — the stop rule is
    # code, not model confidence (which is recorded on the claim, never the trigger).
    sufficiency: GatheringSufficiency | None = None
    coherence: CoherenceState | None = None       # conclusion-level, populated after synthesis
    iteration: IterationBudget                    # four reservations — §5
    resynth_attempts: int = 0                     # bounds the coherence back-edge (§5)

    report: IncidentReport | None = None
    report_hash: str | None = None                # binds approval to the exact report bytes
    evidence_manifest_hash: str | None = None     # binds approval to the exact evidence too (§8):
                                                  # every cited ref → its ledger result_hash. Without
                                                  # this, approved bytes can cite evidence that later
                                                  # changed or vanished.
    approval: ApprovalRecord | None = None

    degradation: DegradationState | None = None
    errors: list[ExecutionError] = []
```

### Temporal isolation is a contract, not a filter

> **Status:** `proposed` — no `as_of`/cutoff/snapshot on state or in the tool contracts · gap: [G-52](./status.md#g-52)

An investigation must only ever see what existed **when it began**. Miss this and two failures follow,
one per lane:

- **Evaluation leaks the future.** A historical scenario replayed today can retrieve the *postmortem
  written after that incident was resolved* — the answer key, handed to the agent as "retrieved
  knowledge." The scorecard then measures memorization, not investigation, and reads high for the wrong
  reason. (This is a sharper form of [G-19](./status.md#g-19): there the fast path retrieved its own
  answer; here *any* retrieval can pull a future document.)
- **Production uses corrected knowledge.** A runbook edited after an incident, or a topology changed by
  a later migration, is not what the on-call engineer had — using it makes the report unfaithful to the
  moment it describes.

**The four temporal fields (above) are mandatory retrieval arguments, not optional filters.** A
knowledge or telemetry tool call that does not carry `as_of` / `knowledge_cutoff` / `topology_version` /
`corpus_snapshot_id` is a contract violation, not a call that silently returns everything. The bounds
each tool enforces:

```
retrieved_document.created_at   <= investigation_as_of
past_incident.closed_at          < investigation_as_of      # strictly before — a still-open incident is not history
current incident                 EXCLUDED                    # never retrieve the incident under investigation
superseded memory                EXCLUDED                    # only the version current as_of, not a later correction
topology / config                valid at topology_version   # the dependency graph as it was, not as it is
```

`corpus_snapshot_id` pins the *index generation* so a re-run reads a byte-identical corpus even after
the live index has moved on — which is also what makes cassette replay ([evaluation.md](./evaluation.md)) and the
answer-key closure gate reproducible. The retrieval seam ([§6](data-and-evidence.md#sec-6)) and the AI Search adapter (§11) both take
these as required parameters, and the golden-retrieval contract test asserts a call *without* them
fails closed.

### Evidence is a discriminated union of typed facts, not a generic envelope

> **Status:** `proposed` — `EvidenceItem` is one flat shape with `source_type: str`, `observed_at`,
> and `excerpt` · gap: [G-42](./status.md#g-42)

Every deterministic check in [§5](workflow-design.md#sec-5) is a comparison between *facts*: does this metric window overlap that
one, did this deployment start before that anomaly, was this dependency edge valid at onset. **A
single `observed_at` plus an `excerpt` cannot answer any of them.** An aggregated p99 over a
five-minute window has no single timestamp; a deploy is an interval that can straddle onset; a
dependency edge is only true relative to a topology version. A checker built on the generic envelope
would have to parse prose or re-parse ref strings — which is string-matching wearing a type
annotation, and it fails silently the first time a format changes.

```python
class MetricEvidence(EvidenceEnvelope):
    kind: Literal["metrics"] = "metrics"
    service: str
    metric_name: str
    dimensions: dict[str, str] = {}      # route, region, instance — part of comparability
    aggregation: Literal["p50", "p95", "p99", "avg", "sum", "rate", "count"]
    window_start: datetime               # an aggregate has a WINDOW, never a point
    window_end: datetime
    value: float
    baseline_value: float | None         # what "normal" was, per the same aggregation
    direction: Literal["above", "below", "at"]   # vs baseline — derived, not asserted
    unit: str
    clock_source: str                    # whose clock — cross-system ordering needs this

class DeploymentEvidence(EvidenceEnvelope):
    kind: Literal["deploys"] = "deploys"
    service: str
    deploy_id: str
    started_at: datetime                 # an INTERVAL: a deploy may start before onset
    completed_at: datetime | None        #   and complete after it — causal-order compares ranges
    rollout_scope: str                   # canary | percentage | full — blast radius of the change
    version_before: str | None
    version_after: str
    status: Literal["succeeded", "failed", "rolled_back", "in_progress"]

class DependencyEvidence(EvidenceEnvelope):
    kind: Literal["deps"] = "deps"
    from_service: str
    to_service: str
    edge_type: Literal["sync", "async", "datastore", "external"]
    valid_from: datetime                 # topology is versioned: a report reconstructed later
    valid_to: datetime | None            #   must not be re-checked against today's graph
    topology_version: str

class LogEvidence(EvidenceEnvelope):
    kind: Literal["logs"] = "logs"
    service: str
    event_id: str
    observed_at: datetime                # a log line IS a point event — the one type where it fits
    level: Literal["debug", "info", "warn", "error", "fatal"]
    message: str
    noise_floor: int | None              # matching count in the comparable quiet window (§6)

class KnowledgeEvidence(EvidenceEnvelope):
    kind: Literal["runbook", "past_incident"]
    doc_id: str
    chunk_id: str
    passage: str                         # the matched text — the reason retrieval exists (§6)
    rank: int
    score: float

Evidence = Annotated[
    MetricEvidence | DeploymentEvidence | DependencyEvidence | LogEvidence | KnowledgeEvidence,
    Field(discriminator="kind"),
]
```

**The envelope survives; it just stops carrying the facts.** `excerpt` stays — it is what the model
reads ([§6](data-and-evidence.md#sec-6)) — but no deterministic check may consult it. The rule is one line: **prose is for the
model, typed fields are for the gate**, and any check that needs to read an excerpt to decide is a
check that has not been designed yet.

**This is a tool-boundary requirement before it is a state requirement.** State cannot hold a window,
a rollout scope, or a topology version that no tool returns — so [§6](data-and-evidence.md#sec-6)'s telemetry tools must return
typed facts in the same change, exactly as the knowledge tools must return passages.

### The conclusion is a causal proposition, not a blamed name

> **Status:** `proposed` — `Hypothesis` is `statement: str` + untyped citations today · gaps: [G-29](./status.md#g-29), [G-43](./status.md#g-43)

A free-text conclusion cannot be checked by code. But naming an entity is not enough either.
`blamed_entity = "checkout-api"` does not say whether the claim is *checkout's deploy broke it*,
*checkout's config broke it*, *checkout was overloaded by a dependency*, or *checkout is merely where
the symptom is visible* — and those demand different checks. The causal-order detector wants to
compare a **deployment interval** to effect onsets; against an entity name it has nothing to compare,
so it would have to guess that the entity's most recent deploy is the claimed cause. **A checker that
guesses what the claim was is not deterministic.**

```python
CitationRole = Literal[
    "cause",      # evidence FOR the causal event — admissibility table in §5
    "effect",     # the symptom being explained — expected to POSTDATE the cause
    "baseline",   # deliberately-normal evidence, cited to rule something OUT
    "context",    # supporting/topological, carries no temporal claim
]

class Citation(BaseModel):
    ref: str                        # frozen ref grammar (Appendix D)
    role: CitationRole              # PROPOSED by the model, ADMITTED by code (§5). Without the
                                    # role the causal-order check false-positives on every
                                    # legitimate baseline citation; without the admission check
                                    # the model can relabel its way past the gate.
    note: str = ""

class EntityRef(BaseModel):
    kind: Literal["service", "datastore", "external", "unknown"]
    name: str                       # MUST resolve in the topology unless kind is external/unknown
                                    # ("external:payment-gateway" is inc-004's true root)

class CausalClaim(BaseModel):
    cause_type: Literal["deployment", "configuration", "dependency_failure",
                        "capacity", "external_dependency", "unknown"]
    cause_entity: EntityRef         # WHO
    cause_event_ref: str | None     # WHAT happened — the specific deploy/config/failure ref.
                                    # Required when cause_type is "deployment": the causal-order
                                    # check compares THIS interval, never an inferred one.
    affected_entities: list[EntityRef]
    onset_window: TimeRange         # when the effect began — the ordering anchor
    support_refs: list[str]         # refs whose role is "cause"
    counter_refs: list[str]         # evidence AGAINST this claim, carried openly

class Acknowledgment(BaseModel):
    """Why a contradiction stopped blocking. NEVER written by the model (§5)."""
    admitted_by: Literal["policy", "human"]
    accepted_by: str | None = None   # verified Entra principal, when admitted_by == "human"
    accepted_at: datetime | None = None
    policy_id: str                   # which rule admitted it — auditable, not "the model said so"

class Contradiction(BaseModel):
    contradiction_id: str            # stable within the report; a human accepts THIS, not "the report"
    kind: Literal["causal_order", "entity_support", "value_direction", "role_inadmissible"]
    refs: list[str]
    detail: str                      # for the human. Never an input to any check.
    state: Literal["unresolved", "resolved", "acknowledged"] = "unresolved"
    acknowledgment: Acknowledgment | None = None   # REQUIRED when state == "acknowledged"

ReportClaimType = Literal[
    "root_cause",        # the CausalClaim below — exactly one per report
    "onset",             # when/where the incident began
    "blast_radius",      # which services/users were affected
    "sequence",          # the order events unfolded
    "contributing_factor",  # a condition that worsened it, short of the cause
    "ruled_out",         # a candidate cause deliberately excluded (cites the disqualifying evidence)
    "recommendation",    # a suggested follow-up (the one class that may cite runbooks/past incidents)
]

class ReportClaim(BaseModel):
    """EVERY assertion in the report is one of these — not just the root cause (G2)."""
    claim_type: ReportClaimType
    statement: str                  # human-readable rendering of THIS claim's structured fields
    support_refs: list[str]         # grounding — validated against produced_refs like any citation
    counter_refs: list[str] = []    # evidence against, carried openly
    entities: list[EntityRef] = []  # what the claim is about, topology-resolved
    window: TimeRange | None = None # for onset/sequence claims

class Claim(BaseModel):
    # `statement` is RENDERED from the structured fields by render_report (§5), not free-authored
    # alongside them. A model-authored prose statement that contradicts `causal` (blames the deploy
    # while `causal.cause_entity` is the gateway) is the loophole "never parsed" left open — closed
    # by deterministic rendering, or, if the model authors it, a semantic-consistency gate (§5, G-50).
    statement: str
    causal: CausalClaim             # the machine-checkable root-cause proposition
    confidence: float = Field(ge=0.0, le=1.0)    # code-capped when a caveat is acknowledged (§5)
    disposition: Literal["conclusive", "qualified", "inconclusive"] = "conclusive"
                                    # DERIVED, never asserted: a claim carrying an acknowledged
                                    # contradiction is at best "qualified" — it does not get to
                                    # present as a settled root cause
    citations: list[Citation] = Field(default_factory=list)
    caveats: list[Contradiction] = Field(default_factory=list)   # the model may PROPOSE a caveat
                                    # here; only policy or a human moves one to "acknowledged"
    # The report is a SET of grounded claims, not one hypothesis with prose around it. G2 ("every
    # claim is grounded") is enforceable only if every claim is a ReportClaim the citation gate can
    # check — onset, blast radius, sequence, contributing factors, ruled-out causes, recommendations
    # (§5, G-51). The root_cause entry's structured proposition is `causal` above.
    report_claims: list[ReportClaim] = Field(default_factory=list)
```

**Each `cause_type` selects which checks apply**, which is the point of typing it: `deployment`
requires `cause_event_ref` and runs causal-order over intervals; `dependency_failure` requires a
`DependencyEvidence` edge valid at onset plus an anomaly on the far side; `external_dependency`
accepts an unresolvable `cause_entity` (nothing internal can be cited for it — inc-004's standing
case) but then requires `counter_refs` to show what internal causes were ruled out; `unknown` fails
the gate as an unsupported conclusion rather than passing quietly.

**`SynthesisResponse` mirrors this shape**, so the model emits the structure directly rather than a
downstream parser re-deriving it from text. `cause_entity` is validated against the topology at parse
time and fails closed to `kind="unknown"`.

> **"Never parsed" was a loophole, and G2 was bigger than one hypothesis.** Two things this shape
> fixes:
>
> 1. **Prose cannot contradict the structure.** An earlier draft let `statement` be free human-readable
>    text the checks never read — so a report could carry `cause_entity = payment-gateway` while the
>    prose says *"the checkout deployment caused the outage,"* and the human reads the prose. `statement`
>    is therefore **rendered from the structured fields by `render_report`** (deterministic, [§5](workflow-design.md#sec-5)), not
>    authored beside them. If a build lets the model author prose, a **semantic-consistency gate** must
>    reject prose that introduces or contradicts a claim before it reaches a human ([G-50](./status.md#g-50)).
> 2. **Every claim is grounded, not just the root cause.** G2 says a *published conclusion cites only
>    tool-produced evidence* — but a real incident report also asserts onset, blast radius, sequence,
>    contributing factors, ruled-out causes, and recommendations. If only the top-level hypothesis is
>    structured, those secondary claims are ungrounded prose and the "every claim" guarantee is stronger
>    than the design enforces. `report_claims: list[ReportClaim]` makes each one a typed, citation-gated
>    assertion — `ruled_out` must cite its disqualifying evidence, `recommendation` is the one class that
>    may cite runbooks/past incidents, and `safety_validate` checks *all* of them, not just `causal`
>    ([G-51](./status.md#g-51)).

**Sequencing consequence.** This is a change to frozen contracts (`diagnosis/contracts.py`,
`llm/schema.py`) and it is a **prerequisite for three things already scheduled**: the coherence
detector ([G-07](./status.md#g-07)) has nothing to run against without it, role admissibility
([G-43](./status.md#g-43)) has no role to admit, and Stage 5's LLM report node would otherwise ship on
the unstructured shape and need retrofitting. It gets more expensive after that node lands, not less.

### Design rules

**Reducers merge by key, never by blind concatenation.** `merge_evidence` deduplicates by
`content_hash`, preserves the earliest `retrieved_at`, and keeps *all* contradictory observations —
never silently collapsing them, because contradictions are an input to the stop rule ([§5](workflow-design.md#sec-5)). This avoids
the duplicate-evidence, unbounded-checkpoint, and nondeterministic-ordering failure modes that
`list + add` produces under parallel branches *and under loop re-entry*.

**State holds excerpts and references only.** Raw payloads and full reports go to Blob Storage; the
checkpoint carries pointers. Memory layers map cleanly: per-turn scratchpad = working memory,
`InvestigationState` per thread = short-term, the cross-incident **Store** = long-term.

**Two fields are load-bearing, not typing polish** (grounding provenance gets its own subsection
below — it is a channel-ownership problem, not a field):

- **`excerpt`** is what the model actually reads. It is meaningful only once the retrieval seam
  carries passage text — the state field and the seam widening are one change, not two
  ([G-04](./status.md#g-04)).
- **`severity_revisions`** records a bar change rather than silently overwriting the bar the run is
  judged against ([G-12](./status.md#g-12)).

### Grounding is enforced by a gateway, not by a field

> **Status:** `proposed` — `produced_refs` is a node-written channel today · gap: [G-05](./status.md#g-05)

An earlier version of this document claimed a `tool_call_id` field makes it *physically impossible*
for a node to mint evidence. **That claim was wrong, and the error is instructive.** A `UUID` field
proves nothing about who set it. A node that can write both the evidence channel and the tool-call
channel can fabricate a `ToolExecutionRecord`, point forged evidence at its id, and pass every
type-level check — Pydantic validates *shape*, never *provenance*. Adding an id turned an unowned
channel into an unowned channel with an extra field.

The control is **structural: separate the writer, not the type.**

```python
class ToolGateway:
    """The ONLY code path that may append to the tool ledger. Nodes hold a reference to
    execute() and nothing that writes the ledger channel directly."""
    def execute(self, call: ToolCall, state) -> ToolResultHandle:
        result = self._adapter.run(call)                 # the actual tool / MCP round-trip
        record = ToolExecutionRecord(
            tool_call_id=uuid4(),
            tool_name=call.name,
            canonical_arguments_hash=sha256_canonical(call.arguments),
            result_hash=sha256_canonical(result.payload),  # binds the id to THESE bytes
            executed_at=result.executed_at,
            adapter_version=self._adapter.version,
        )
        # append-only: the reducer for `tool_ledger` rejects any write not carrying the
        # gateway's signing token, so this is the sole producer by construction.
        emit_ledger(state, record)
        return ToolResultHandle(tool_call_id=record.tool_call_id, result_hash=record.result_hash)
```

A node receives an **opaque handle**, not writeable provenance. It builds `Evidence` and attaches the
handle; `merge_evidence` then **admits the item only if the handle resolves to a ledger record whose
`result_hash` covers the evidence**, and drops it otherwise. The grounding set is a projection over
ledger-backed evidence, so the chain is: *tool actually ran* (gateway wrote the record) → *this
evidence came from that run* (handle + `result_hash` match) → *this ref is citable* (in
`produced_refs`). No link is a field a node can set on its own.

This is what finally closes `known_issue_fast_path`'s self-certification ([G-05](./status.md#g-05)):
the fast path mints `past_incident:<id>` from a store read whose tool returned `evidence_refs == []`,
so there is no ledger record to resolve against and `safety_validate` fails it — instead of passing it
by construction, as today. The `remediation_action` v2 write path ([§6](data-and-evidence.md#sec-6)) rides the same gateway, which
is where the read-only allowlist is actually enforceable rather than conventional.

---

<a id="sec-6"></a>
## 6. Tool boundary

> **Status:** `deployed` — all 8 tools behind `ToolService` · `merged` — the MCP parity suite (a
> 3-tool scaffold, not the production split) · `proposed` — temporal args, the MCP security/operational
> contract, the incident-source boundary · gaps: [G-04](./status.md#g-04), [G-16](./status.md#g-16), [G-17](./status.md#g-17), [G-24](./status.md#g-24), [G-52](./status.md#g-52), [G-53](./status.md#g-53)

External-system tools *become* **MCP servers**; retrieval stays in-process; the v2 write tool is a
separate allowlisted MCP server.

| Tool | Hosting (target) | Notes |
|---|---|---|
| `get_incident` | **incident-source adapter** (dev in-process; prod behind an ITSM-owned boundary) | Incident record lookup; known errors link their postmortem. Originates from monitoring/ITSM, not local data — see below |
| `get_correlated_alerts` | **incident-source adapter** (dev in-process; prod behind an ITSM-owned boundary) | The alert storm (root_cause / symptom / trigger); navigational, no evidence refs |
| `query_logs` | MCP (telemetry server) | Log search over a service/window; signal returned alongside the noise floor |
| `get_metrics` | MCP (telemetry server) | Error rate, latency percentiles |
| `get_deployments` | MCP (platform server) | Recent deploys — "what changed" |
| `get_service_dependencies` | MCP (platform server) | Blast radius |
| `search_runbooks` | in-process | Hybrid (dense + BM25) over runbooks/architecture |
| `search_past_incidents` | in-process | Recency-weighted hybrid over past incidents |
| `remediation_action` *(v2)* | MCP (action server, allowlisted) | Mutating; reachable only after approval |

### Knowledge tools must return passages, not pointers

The two tools that deliver *knowledge* must deliver the matched passage, not merely a citation target.
`Hit` carries the matched chunk (text + `chunk_id` + offsets); `DocHit` carries a capped `excerpt`
derived from it; the observation summarizer renders that excerpt; `EvidenceItem.excerpt` ([§4](data-and-evidence.md#sec-4)) stores
it.

This is what makes MRR 0.792 *actionable* rather than decorative — a reranker's job is to put the
right passage first, which only matters if the passage is delivered. **As built, both tools return
`doc_id`/`title`/`score` and no text at all** — [G-04](./status.md#g-04), the root of the
retrieval-disconnection defect, and a change no prompt or planner work can route around.

It is also the point at which retrieved content becomes an **injection surface**: §10's untrusted-data
handling must ship in the same change ([G-26](./status.md#g-26)), because widening the seam without it
creates exactly the exposure that guardrail was written for.

**Both knowledge tools take the [§4](data-and-evidence.md#sec-4) temporal bounds as *required* arguments** — `as_of`,
`knowledge_cutoff`, `corpus_snapshot_id` — and return only documents that existed at the cutoff,
against a pinned index generation, with the current incident excluded and superseded versions filtered
to the one current *as of* the run ([G-52](./status.md#g-52)). A call missing them fails closed; it does
not default to "everything now."

### Telemetry tools must return typed facts, not rendered lines

The same argument, on the other half of the tool set. [§4](data-and-evidence.md#sec-4)'s evidence union and [§5](workflow-design.md#sec-5)'s deterministic
checks need windows, intervals, baselines, and topology versions — and **state cannot hold what no
tool returns**. A `get_metrics` that answers with `"p99 latency elevated on checkout-api"` forces
every downstream check to parse prose; one that answers with
`(service, metric_name, dimensions, aggregation, window_start, window_end, value, baseline_value, unit, clock_source)`
makes the check a comparison.

| Tool | Must additionally return |
|---|---|
| `get_metrics` | the aggregation and its **window**, the comparable `baseline_value`, unit, dimensions, clock source |
| `get_deployments` | `started_at` **and** `completed_at`, rollout scope, version before/after, status |
| `get_service_dependencies` | edge type and the **validity interval** + `topology_version` of the snapshot |
| `query_logs` | level and the noise-floor count for the comparable quiet window |

The `signal [ref]` summaries the model reads are then **rendered from these facts**, not the source of
them — one representation for the model, one for the gate, derived from a single typed object
([G-42](./status.md#g-42)).

### Uniform envelope

Every tool returns a `ToolResult` with a sanitized `error` and no exception, stack trace, or path ever
crossing the boundary. Plain error *strings* are deliberately avoided as data: an error envelope can
never be mistaken for a successful result. Over MCP the server serializes this same envelope, so
in-process and out-of-process contracts stay identical, validated continuously by the parity suite.

**`ok | error` is too coarse for a system that claims explicit degradation.** The whole reliability
story (§10) rests on distinguishing *disclosed-degraded* from *complete*, and the sufficiency gate
([§5](workflow-design.md#sec-5)) needs to tell "this class genuinely has no signal" from "we could not read this class" — those
route to opposite decisions and a two-value status collapses them. The envelope therefore carries a
richer status and completeness metadata:

```python
class ToolStatus(str, Enum):
    ok          = "ok"           # complete result, whatever its cardinality
    empty       = "empty"        # ran fine, genuinely nothing matched — NOT an error, NOT missing data
    partial     = "partial"      # returned some rows and knowingly dropped/omitted others
    timeout     = "timeout"      # deadline hit; any rows returned are a prefix, not the set
    blocked     = "blocked"      # a guardrail/policy refused the call (e.g. non-read-only)
    unavailable = "unavailable"  # the source could not be reached — the degradation ladder's trigger
    error       = "error"        # the call itself failed

class ToolResult(BaseModel):
    status: ToolStatus
    results: list[...] = []
    evidence_refs: list[str] = []
    error: str | None = None            # sanitized; present iff status in {error, blocked}
    metadata: ResultMetadata

class ResultMetadata(BaseModel):
    rows_examined: int | None = None
    rows_returned: int
    rows_invalid: int = 0               # malformed source rows dropped (G-17 stops being silent)
    truncated: bool = False
    has_more: bool = False
    continuation_token: str | None = None
    query_window: TimeRange | None = None   # what span was actually covered
    source_snapshot: str | None = None      # topology_version / index generation queried
    retryable: bool = False
    warning_codes: list[str] = []
```

The distinctions this buys are exactly the ones the architecture already promises but could not
express: *no matching logs* (`empty`) vs *telemetry source down* (`unavailable`, which fires the
degradation ladder) vs *first 100 of many* (`ok`/`partial` + `has_more` + `continuation_token`) vs
*40% of rows malformed* (`partial` + `rows_invalid`, closing [G-17](./status.md#g-17)'s silent drop)
vs *timed out after a partial read* (`timeout`, whose rows are a prefix the gate must not treat as
the full set). Each maps to a defined downstream behavior; none is representable in `ok | error`.

This resolves the status-set half of the former open decision [§13.2](decisions.md#sec-13) (F) in favor of the richer set —
the consuming behaviors above are the consumers that decision was waiting on.

Tool design otherwise follows the established pattern: single-purpose tools, precise descriptions (the
agent's only selection signal), bounded iterations, result/window caps. The read-only surface is
enforced at the gateway ([§4](data-and-evidence.md#sec-4)), not by convention — a non-read-only call returns `blocked`, it does not
run. The v2 `remediation_action` server adds a `before_tool` allowlist callback (information-asymmetry
pattern): read tools open, write tools gated.

### MCP exposure aligns with system ownership

In production: a **telemetry server** (`query_logs`, `get_metrics`) and a **platform server**
(`get_deployments`, `get_service_dependencies`). `search_runbooks` / `search_past_incidents` leave the
exposed set — RAG is OpsPilot-owned and in-process, and putting it behind a network protocol adds
latency and failure surface for zero ownership benefit. The parity suite extends to every exposed tool.

### Not tools — controlled workflow nodes

Conclusion and report production (`synthesize_claims` → `coherence_check` → `render_report`) and
approval (`hitl_gate`) are **graph stages** under the names [§5](workflow-design.md#sec-5) gives them, not agent-callable tools:
letting the model *select* its own approval step would weaken the very HITL control it enforces, and
letting it *call* synthesis would reintroduce the second authority [§5](workflow-design.md#sec-5) rules out. Three categories, kept distinct: (1) agent-callable evidence tools, (2) deterministic
workflow nodes, (3) admin/control-plane operations.

---

## 11 (retrieval). Retrieval design

*The retrieval slice of §11. Models/provider are in [`deployment.md`](./deployment.md) § 11; the
answer-key corpus is in [`evaluation.md`](./evaluation.md) § 11.*

### Retrieval parity is outcome compatibility, not ranking equality

> **Status:** `proposed` — AI Search adapter unbuilt; parity framed as ranking equivalence; no embedding-profile versioning · gap: [G-56](./status.md#g-56)

The dev pipeline (a local dense embedder + BM25 fused with RRF + a cross-encoder reranker) and Azure AI
Search hybrid (vector + full-text combined with RRF, then a semantic reranker over a candidate set) are
**different retrieval systems** — they do not, and need not, produce identical rankings. Requiring
"near-identical ranking within a declared tolerance" is the wrong contract: it can *fail on a better
prod ranking* and it tests an algorithm equivalence that was never the goal. What the investigation
actually depends on is **outcome compatibility**, so the adapter contract tests assert:

| Contract | What it pins |
|---|---|
| **Result schema** | The `Hit`/`DocHit` shape (passage text, `chunk_id`, offsets, score) is identical across backends |
| **Filtering behavior** | Metadata/`as_of`/snapshot filters ([§4](data-and-evidence.md#sec-4) temporal isolation) apply identically — a filtered doc is absent from both |
| **Version / as-of constraints** | Both honor `corpus_snapshot_id` + `knowledge_cutoff`; neither returns a future doc |
| **Minimum Precision@K / MRR** | Each backend clears the *same floor* on the golden-retrieval suite — not "within ε of each other" |
| **Required-target recall** | The KB doc every answer-key scenario needs is retrieved by both, at K |

Ranking may differ; the *conclusion the agent can reach* must not. That is the parity that matters,
and it is falsifiable without pinning two different engines to the same order.

**Swapping the embedder is a migration, not a config flip.** Moving `bge-small-en-v1.5` → BGE-M3
changes the **embedding dimensionality and the vectors in the index** — the existing index is
incompatible and must be **rebuilt**, and any query embedded with the old model against a new index is
nonsense. The architecture therefore versions the embedder as an **embedding profile**
(`embedding_model + dimensions + index_schema_version`, part of `corpus_snapshot_id`) and treats a
profile change as an **index-rebuild/migration** with its own gate: re-embed the corpus, re-run the
golden-retrieval floor on the new index, re-baseline. "Config-swappable" describes the *seam*, not the
*operation* — the seam is a swap, the swap triggers a rebuild.
