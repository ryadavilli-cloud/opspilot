# OpsPilot Architecture

**What is the shape of the system, who holds authority for what, and where does trust stop?**

OpsPilot is an educational Agentic AI capstone: an incident-investigation assistant over a synthetic
e-commerce environment, built to make agentic ideas visible and explainable. This document owns the
top-level shape. Component responsibilities belong to `system-design.md`, behavior over time to
`workflow-design.md`, information meaning to `data-and-evidence.md`, and hosting to
`runtime-and-deployment.md`. `requirements.md` governs all of them.

---

## 1. Architectural drivers

- **The brief is the product.** One concise, evidence-supported brief an engineer can act on, and
  can question afterwards.
- **The agentic behavior is what is being shown.** An investigation whose evidence path adapts to
  what it finds, carried out by three roles with distinct responsibilities, using tools and
  retrieved knowledge, and visible while it happens.
- **Grounded and read-only are non-negotiable.** An assistant that fabricates evidence or mutates
  what it observes is worse than none.
- **Bounded by construction.** Deterministic limits the model cannot widen; one process; one
  request owns one run.
- **Understandable in minutes.** A reviewer should grasp the architecture from this document and
  one diagram; the code should reinforce it rather than require a long explanation of why dozens of
  types are necessary.

---

## 2. System context

```text
   Engineer ──── selects one authored incident, watches, reads the brief, asks a question
       │
       ▼
   OpsPilot ──── one process: interface, three agents, evidence access, record, evaluation
       │
       ▼ read-only, every path
   RetailEase ── synthetic environment: logs, metrics, deployments, dependencies, runbooks,
                 postmortems, prior incidents, structured operational records
```

Model access is to one chat model and one embedding model. Persistence is one document store.
Telemetry goes to one sink. Nothing else is external.

---

## 3. Logical areas

These are explanatory groupings, not a component count and not a class per box.

```text
                                Engineer
                                   │
                    incident       │      activity · brief · answer
                    question       ▼
                  ┌────────────────────────────────┐
                  │           Interface            │  one screen · one streaming request
                  └───────────────┬────────────────┘
                                  ▼
     ┌────────────────────────────────────────────────────────────┐
     │                       Supervisor  [agent]                   │
     │  objective · bounds · continuation · one return ·           │
     │  deterministic grounding gate · persist · deliver · answer  │
     └──────┬────────────────────┬──────────────────────┬─────────┘
            ▼                    ▼                      ▼
   ┌────────────────┐  ┌───────────────────┐  ┌───────────────────────┐
   │   Evidence     │  │    RCA Analyst    │  │  Investigation Record │
   │  Investigator  │  │      [agent]      │  │  one completed record │
   │    [agent]     │  │ sole synthesis    │  │  written once         │
   └───────┬────────┘  └───────────────────┘  └───────────┬───────────┘
           ▼                                              ▼
   ┌────────────────────────────────────────┐        Evaluation
   │           Evidence access              │     (offline reader,
   │ registered read-only capabilities:     │      one LLM judge)
   │ tools · retrieval · structured query · │
   │ one MCP-exposed capability · admission │
   └────────────────────┬───────────────────┘
                        │ read-only
   ═════════════════════│═══════════════════ OpsPilot boundary
                        ▼
                    RetailEase
```

**Three agents are deliberate.** Supervisor, Evidence Investigator, and RCA Analyst exist because
orchestration, evidence gathering, and causal synthesis are genuinely different responsibilities,
and separating them is what makes delegation, adaptation, and synthesis-driven re-gathering
visible. There is no fourth agent and no extensible agent framework.

**Interface, evidence access, and the record are not agents.** They hold no investigative
judgement. Evaluation reads completed investigations after the fact and holds no authority in a
live run.

---

## 4. Authority

One owner per concern.

| Concern | Owner |
| --- | --- |
| Objective, bounds, continuation, the one return, the grounding gate, persistence, delivery, the answer to a question over the completed record | Supervisor |
| Which evidence to gather next, through which capability | Evidence Investigator |
| The assessment: candidates, support, unknowns, actions, the one unresolved question | RCA Analyst |
| Read-only access mechanics and admission of results into evidence | Evidence access |
| The completed-investigation record | Investigation Record |
| Presentation; receiving the question and presenting its answer | Interface |

Coordination is Supervisor-mediated. The Evidence Investigator and the RCA Analyst do not talk to
each other, do not deliver to the engineer, and do not extend their own bounds. The RCA Analyst
cannot reach a tool; when its synthesis needs more evidence, it says so through the Supervisor,
once.

The grounding gate is deterministic code inside the Supervisor. It is not a reviewing role.

---

## 5. Trust boundaries

**Models propose; code admits.** Every model output is a proposal until deterministic code has
parsed it and, where it matters, checked it. Models set no bounds, admit no evidence, choose no
outcome, and cannot influence the grounding gate.

**Evidence enters only through admission.** A successful source result becomes an admitted
observation with a stable reference. An empty result is an admitted, citable absence. A partial
result stays marked partial. A source that failed, timed out, was unavailable, or was refused
becomes a limitation, never an observation.

**Read-only on every path.** Direct tools, retrieval, structured query, and the MCP-exposed
capability all read. No write path exists to guard.

**Retrieved knowledge is context, never proof.** A runbook or postmortem shapes what is checked and
how evidence is read. It cannot establish the cause of the current incident on its own.

**Untrusted content is data.** Incident text, engineer questions, retrieved passages, and tool
output carry no instruction authority.

**Nothing is written until the investigation completes, and nothing is delivered until it is
written.** In-progress state is ephemeral. The completed record is persisted once, before the
terminal event.

**Hidden reasoning stays hidden.** Activity shown to the engineer is a compact projection of what
happened, never chain-of-thought.

---

## 6. Major flow

An engineer selects one authored incident. The Supervisor sets the objective and the bounds. The
Evidence Investigator proposes the next evidence action from what it has already seen; the
Supervisor authorizes it against the registry and the bounds; evidence access executes it read-only
and admits the result. Retrieved knowledge, where relevant, informs both what to check and how to
read it. When gathering ends, the RCA Analyst synthesizes an assessment. If it names one material
question that gathering can still answer, and no return has yet happened, the Supervisor sends the
investigation back to gathering once, then synthesis finishes. The grounding gate checks the
assessment against the admitted evidence and the retrieved knowledge and may request one
correction. The completed investigation is persisted, and its brief is delivered.

Afterwards the engineer may ask a question; the Interface receives it and presents the answer, and
the Supervisor answers it from the completed record alone.

Every completed investigation is complete, partial, or inconclusive. An attempt that cannot
produce, ground, persist, and deliver a trustworthy brief fails without a record; failure is not an
outcome.

---

## 7. Structural principles

- **Smallest purposeful agent team.** Three roles, each with a distinct authority.
- **Adaptive but bounded.** The evidence path is chosen from what is observed; code owns every
  limit.
- **Deterministic control around probabilistic reasoning.** Models interpret, choose, and
  synthesize; code enforces admission, bounds, grounding, read-only, and delivery order.
- **One investigation, one run, one record.** No turn history, no session, no reopening.
- **Inconclusive is a good result** when it is honest and names what is missing.
- **Completed artifacts, not workflow machinery.** No checkpoints, no jobs, no recovery.
- **Complexity earns its place.** An element stays only if removing it breaks a requirement, a
  course demonstration, a trust boundary, credible evaluation, or basic troubleshooting.

---

## 8. Trade-offs accepted

| Chosen | Gained | Cost |
| --- | --- | --- |
| Three fixed agent roles | Visible specialization, attributable handoffs, a real synthesis-to-gathering loop | More coordination than a single agent with tools |
| Supervisor-mediated coordination | Inspectable routing, enforceable authority | Less flexible than open peer collaboration |
| One synthesis authority | One assessment, simple grounding and provenance | Result quality rests on one role |
| One evidence-access surface | One read-only boundary, one admission path, one provenance discipline | Several capabilities share one area and need internal separation |
| One process, one replica, ephemeral in-progress state | Simple runtime, honest capstone scale | A lost request means running the investigation again |
