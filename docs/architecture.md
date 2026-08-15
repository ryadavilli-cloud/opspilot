# OpsPilot - Architecture

**What top-level system shape satisfies the requirements, and why?**

## 1. Purpose and Document Boundaries

This document owns the architectural drivers, the system context, the top-level logical shape, the
trust and authority boundaries, the broad information flow, the architectural principles, and the
major structural trade-offs and their accepted costs.

`requirements.md` governs product intent, scope, and required behavior. This document does not
restate it; it translates the requirements that shape structure into architecture.

Detail belongs downstream. Component responsibilities, conceptual interfaces, the session and turn
model, and the technology map belong to `system-design.md`. Turn stages, routing, handoffs,
continuation, cancellation, and degradation belong to `workflow-design.md`. Evidence admission,
citations, candidate causes, assessment, and brief semantics belong to `data-and-evidence.md`.
Hosting, transport, persistence realization, identity, telemetry, and deployment verification belong
to `runtime-and-deployment.md`. Corpus, baselines, metrics, and reporting belong to `evaluation.md`.
Settled technical choices belong to `decisions.md`, implementation and merge enforcement to
`code-guidelines.md`, and build state to `status.md`.

---

## 2. Architectural Drivers

These are the forces the structure has to answer. Each names the requirements it exists to answer;
this section is where requirements meet structure, and the rest of this document speaks in concepts.

- **The product is a brief, not a report.** Each bounded investigation turn produces one concise,
  evidence-supported brief that an engineer can act on immediately (FR-9, FR-11).
- **Interaction continues after delivery.** The shape must let an engineer question a completed
  turn's result from retained state without reopening the turn that produced it (FR-6, FR-8).
- **Specialization must be purposeful and visible.** Orchestration, evidence gathering, and
  synthesis are genuinely different responsibilities and are separated so each can be traced and
  evaluated on its own (FR-77 to FR-79, FR-80).
- **Investigation must be adaptive and inspectable.** Different incidents take different evidence
  paths, and every step is attributable to a role and a reason (FR-85, FR-86, NFR-14).
- **Several evidence modes must sit behind one governed surface.** Knowledge retrieval, read-only
  operational tools, governed structured-data querying, and one real protocol boundary answer
  different questions and must share one permission and provenance regime (FR-89, FR-95, FR-103,
  FR-104).
- **Grounding and provenance are load-bearing.** Material claims must resolve to evidence gathered
  during the investigation, and contradictions must stay visible rather than being smoothed away
  (NFR-2, NFR-3, NFR-6).
- **Operational access is read-only on every path.** There is no configuration under which OpsPilot
  can change what it observes (FR-75, FR-102, NFR-1).
- **Execution must be bounded deterministically.** No model may widen its own time, step, tool,
  retry, context, or model-use budget (FR-53, FR-56, NFR-10).
- **Completed work must survive; in-flight work need not.** Delivered briefs and their supporting
  evidence persist so citations stay resolvable, without building durable workflow infrastructure
  (NFR-55, NFR-57, NFR-58).
- **The system must be inspectable enough to demonstrate, debug, and troubleshoot** across local
  runs, automated smoke checks, and the hosted demonstration (NFR-19, NFR-20).
- **The architecture must be testable against simpler baselines**, so that its complexity can be
  shown to earn its place rather than asserted (NFR-34, NFR-45).
- **It runs as one coherent application**, locally and in Azure, which is the fixed hosting
  environment (NFR-50, NFR-51). The agent roles are responsibilities inside that application, not
  independently deployed services.
- **It must remain buildable by one developer in vertical slices on an individual-scale budget.**

---

## 3. System Context

An on-call engineer is both the source and the consumer of an investigation. They open it, watch it
run, receive the brief, and decide what to do with it. There is no other actor with authority over a
turn.

OpsPilot is the bounded system. Outside it sits **RetailEase**, a synthetic microservices
environment supplying operational evidence and operational knowledge: logs, metric observations,
deployment records, service dependencies, structured operational tables, runbooks, postmortems, and
prior incidents. OpsPilot reaches all of it read-only, through one governed surface, and writes only
its own investigation artifacts.

Evaluation is an external consumer. It reads preserved artifacts and traces out of band, evaluates
the complete investigation rather than isolated steps, compares the design against simpler baselines
to test whether the agentic structure is justified, and verifies deterministic controls separately
from output quality. Observability is cross-cutting instrumentation over the same activity. Neither
participates in a live turn.

---

## 4. Top-Level Logical Architecture

```text
                                    Engineer
                                       │
             questions                 │     brief, handoff summary
                                       ▼
                       ┌──────────────────────────────┐
                       │ Engineer Interaction Interface │
                       └──────────────┬───────────────┘
                         turn objective │  ▲ delivered brief
                                        ▼  │
     ┌───────────────────────────────────────────────────────────────┐
     │                          Supervisor                            │
     │  turn objective · orchestration · execution bounds ·           │
     │  deterministic grounding gate · terminal turn shape            │
     └───┬─────────────────────┬───────────────▲───────────────┬──▲──┘
         │ evidence assignment │ synthesis     │ assessment    │  │ retained context / read
         │                     │               │ completed turn│  │
         ▼                     ▼               │               ▼  │
 ┌───────────────────┐  ┌─────────────────────────────┐  ┌───────────────────┐
 │ Evidence          │  │         RCA Analyst          │  │ Investigation     │
 │ Investigator      │  │ (sole synthesis authority)   │  │ Record            │
 └────────┬──────────┘  └─────────────────────────────┘  └────────┬──────────┘
          │ evidence requests                                      │ read
          ▼                                                        ▼
 ┌──────────────────────────────────────────────┐            Evaluation
 │            Evidence Access Layer              │         (offline reader,
 │  knowledge retrieval · governed structured    │          no live authority)
 │  query · read-only operational tools ·        │
 │  one external protocol boundary               │
 └──────────────────────┬───────────────────────┘
                        │ read-only
 ═══════════════════════│═══════════ OpsPilot boundary ══════════════════════
                        ▼
 ┌──────────────────────────────────────────────┐
 │  RetailEase operational evidence and          │
 │  knowledge sources                            │
 └──────────────────────────────────────────────┘

 Observability correlates every interaction above. It has authority over none of them.
```

Six logical boundaries make up the runtime. Three are agent roles; three are not.

**Engineer Interaction Interface** is the engineer-facing boundary. It normalizes intake into a
structured incident, classifies each follow-up, presents live activity, and renders the brief and
handoff summary. It holds no investigative authority.

**Supervisor** is the orchestration agent. It interprets the current turn objective, assigns work,
enforces execution bounds, authorizes bounded continuation, applies the deterministic grounding
checks a brief must pass before delivery, and owns the turn's terminal shape.

**Evidence Investigator** is the gathering agent. It chooses which evidence sources to consult next
based on what has already been observed, and it is the only agent role that reaches the Evidence
Access Layer.

**Evidence Access Layer** is the single governed surface onto RetailEase. Knowledge retrieval,
governed structured-data querying, read-only operational tools, and one real external protocol
boundary are capabilities within it, not separate architectural components. It performs no
investigative judgment.

**RCA Analyst** is the synthesis agent and the sole authority over the causal assessment: the
leading candidate, supported alternatives, supporting and weakening evidence, unknowns and
limitations, and the recommendations that make up the brief's analytical content.

**Investigation Record** is passive persistence for the investigation's durable artifacts: the
investigation identity, its completed turns, the admitted evidence needed to keep citations
resolvable, delivered briefs, follow-up history, and references to persisted traces. It holds
completed work only. Evaluation artifacts reference the Record's completed turns from outside it,
never the reverse. The Record holds no decision authority and is not a workflow checkpoint store.
When a turn's work becomes durable, and how it is stored, belong to `system-design.md` and
`runtime-and-deployment.md`.

An **investigation** is the durable identity for one incident under study. A **turn** is one bounded
adaptive gathering-and-synthesis cycle that produces one brief. A **live session** is the ephemeral
conversational surface over an investigation and is not separately persisted. The persisted
relationship is one investigation to its completed turns. A restart may lose the in-flight state of
the current turn; everything already completed remains available.

---

## 5. Trust and Authority Boundaries

### One authority per concern

| Concern | Authority |
| --- | --- |
| Engineer interaction, intake normalization, follow-up classification, presentation | Engineer Interaction Interface |
| Turn objective, orchestration, execution bounds, grounding gate, terminal turn shape | Supervisor |
| Evidence-source selection, investigative questions, working hypotheses | Evidence Investigator |
| Evidence-access mechanics and the read-only boundary | Evidence Access Layer |
| Causal assessment, candidates, recommendations, brief content | RCA Analyst |
| Persistence of completed investigation artifacts | Investigation Record |

Coordination is Supervisor-mediated. Assignments, results, continuation decisions, and synthesis
requests pass through the Supervisor, and there is no unrestricted peer-to-peer conversation between
agents. The RCA Analyst returns its assessment through the Supervisor; it cannot reach tools, extend
the investigation on its own, or deliver directly to the engineer. Where further evidence is needed,
the need returns through the Supervisor and is answered only inside bounds that already exist.

The Supervisor contains the deterministic **grounding gate**, which executes exactly four grounding
checks before a brief may be delivered. The gate is code within the Supervisor boundary, not a
validator agent, a validator service, or a further component.

### What is trusted, and how far

**Engineer and incident input** frames the investigation and is untrusted content. It may contain
speculation, an asserted cause, or instructions, and none of that acquires control authority.

**Retrieved knowledge** supplies context and investigative leads. It cannot independently establish
the cause of the current incident; a live conclusion still requires evidence gathered now.

**Operational tool results** become citable evidence only through deterministic admission. An
operation that failed, timed out, was unavailable, or was refused produces a stated limitation, not
a fabricated observation.

**Model output** is proposed reasoning or proposed structured data until deterministic code admits
it. Models do not enforce their own permissions, bounds, evidence admission, citation integrity, or
terminal outcome.

**The observed environment** is reachable only through the Evidence Access Layer, read-only. No
mutation, remediation, or configuration path exists on any transport, including the external
protocol boundary.

### Non-authoritative concerns

**Observability** must correlate activity end to end well enough to reconstruct which investigation
and turn ran, which role acted, which handoffs and model, retrieval, tool, structured-query, and
protocol-borne operations occurred, what evidence was admitted, why execution continued or stopped,
which bounds or degradation conditions were hit, whether the brief passed the grounding gate, and
what the run consumed in latency, model and tool calls, token usage, and approximate cost. That
exists to make the agentic system inspectable, to support local debugging, and to locate a failure
quickly in a smoke check or a hosted run. It does not imply an observability subsystem in the
component model, production service objectives, alert routing, long-term telemetry architecture, or
drift monitoring.

**Evaluation** reads completed artifacts and traces out of band. Neither observability nor
evaluation may route, gate, delay, revise, or decide anything in a live turn.

---

## 6. Major Information Flow

An engineer selects a predefined incident or describes a symptom. The Engineer Interaction Interface
normalizes it into a structured incident and hands it to the Supervisor, which establishes the
bounded objective for the turn.

The Supervisor assigns evidence work to the Evidence Investigator, which consults the Evidence
Access Layer adaptively, letting each observation inform what is worth checking next. Gathered
information returns through the Evidence Investigator to the Supervisor. When the Supervisor judges
the accumulated evidence ready, it assigns synthesis to the RCA Analyst, which returns the
structured assessment and the brief's analytical content. The Supervisor's grounding gate runs its
four checks; the completed turn and its evidence are then written to the Investigation Record; and
only once that write succeeds does the Engineer Interaction Interface present the outcome, with a
brief where the turn produced one.

Every completed turn has exactly one outcome: **complete**, **partial**, or **inconclusive**. An
attempt that cannot produce, validate, persist, and deliver a trustworthy brief is a failed
execution, which creates no completed turn and is not another turn outcome. There is no approval,
editing, publication, or finalization stage between synthesis and delivery.

Afterwards the engineer may question the result. A question or a handoff-summary request is answered
from what the Investigation Record already holds, and nothing reaches back into a turn that is
already running.
Detailed routing, bounds, and degradation behavior belong to `workflow-design.md`.

---

## 7. Architectural Principles

**Use the smallest purposeful agent team.** Three agent roles exist because orchestration, evidence
gathering, and causal synthesis are distinct responsibilities. A fourth requires a distinct
authority and demonstrated value, not a plausible use.

**One responsibility, one authority.** Every major concern has exactly one owner, and no two roles
produce competing authoritative conclusions.

**Supervisor-mediated coordination.** Every assignment, result, and continuation decision passes
through the Supervisor. This is less flexible than open collaboration and makes delegation,
provenance, and failure attributable in exchange.

**Adaptive but bounded.** The system chooses its evidence path from what it observes; deterministic
code owns every budget, and no model may widen its own.

**Deterministic control around probabilistic reasoning.** Models propose actions, interpretations,
and conclusions. Code enforces permissions, bounds, contract admission, evidence admission,
grounding, citation integrity, and what may be delivered.

**Grounded, not asserted.** A material incident-specific claim must resolve to evidence gathered
during the investigation. Retrieval shapes what is examined and how it is read, and proves nothing
on its own.

**Read-only by design.** The same read-only boundary applies to direct tools, structured queries,
and the external protocol path alike. There is no alternate write path to guard because none exists.

**The brief is the product.** The architecture exists to deliver a concise, evidence-supported brief
that can be questioned and revised through later bounded turns.

**Inconclusive is useful.** An honest inconclusive result that names what is missing is worth more
than a confident unsupported cause, and the structure must make that outcome ordinary.

**Completed artifacts, not durable workflow machinery.** Delivered briefs and the evidence behind
them persist so citations stay resolvable. In-flight recovery, durable suspension, and checkpoint
replay are not baseline architectural concerns.

**Observability is cross-cutting.** Agent, model, tool, evidence, and turn activity must be
correlated and inspectable, and observability holds no authority over any of it.

**Complexity must be earned.** An element stays only when removing it would break a requirement, a
required demonstration, an evaluation guarantee, a safety boundary, or practical troubleshooting.

---

## 8. Structural Trade-offs and Accepted Costs

| Chosen structure | What it gains | Accepted cost |
| --- | --- | --- |
| Fixed three-agent topology | Visible specialization, attributable handoffs, and separate evaluation of orchestration, gathering, and synthesis | More coordination and context-transfer overhead than a single-agent design |
| Supervisor-mediated communication | Inspectable routing, enforceable authority, attributable failures | Less flexible than unrestricted peer collaboration |
| One synthesis authority | One authoritative assessment, simpler grounding and provenance | Result quality depends heavily on a single role |
| Shared Evidence Access boundary | One governed read-only surface with consistent provenance and tool semantics, and no duplicated permission logic | Several evidence capabilities share one boundary and need careful internal separation downstream |
| Bounded adaptive investigation | Observation-driven paths, visible agentic behavior, controlled cost and termination | A useful investigation may stop before every question is answered |
| Completed-artifact persistence only | Simpler runtime and storage while preserving briefs, evidence, and traces | In-flight turn progress may be lost on restart |
| No mandatory approval gate | Immediate delivery, natural conversational follow-up, no review or publication machinery | The output stays advisory, and the engineer owns how it is used |
| One coherent application | Simpler deployment and coherent tracing, with no distributed agent communication | Roles and capabilities do not deploy or scale independently |
| Fixed Azure hosting environment | A reproducible hosted demonstration on a narrow operational surface | Provider and cloud portability are not goals |
| Practical observability rather than production monitoring | Inspectable agentic behavior and faster debugging, smoke-test diagnosis, and deployment troubleshooting | No service objectives, alerting organization, or long-term telemetry architecture |
