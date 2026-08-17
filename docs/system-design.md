# OpsPilot System Design

**What does each part of the system own, how do the parts reach each other, and which technology
carries which responsibility?**

This document owns component responsibilities, permitted interaction directions, the conceptual
seams, and the technology responsibility map. Behavior over time belongs to `workflow-design.md`;
information meaning to `data-and-evidence.md`; hosting to `runtime-and-deployment.md`.

A conceptual interface named here does not imply a dedicated request class and result class. Most
interactions are ordinary function calls with typed parameters over the domain objects
`data-and-evidence.md` defines.

---

## 1. Components

### The three agents

**Supervisor.** Owns the investigation: interprets the selected incident into an objective, sets the
bounds, authorizes each gathering step against the registry and the bounds, decides when gathering
ends, authorizes the one analysis-to-gathering return, runs the deterministic grounding gate,
triggers persistence, and delivers. Two of its steps are model judgements: objective interpretation
and answering a question over a completed record. Everything else it does is deterministic code.
The Supervisor is one boundary that holds both; it is not two components and not a fourth agent.

**Evidence Investigator.** Decides what evidence to gather next from the incident, the objective,
and what has already been observed, and gathers it through evidence access. It proposes one
capability and its arguments per step, and states the question it expects the result to answer.
It holds a working hypothesis as guidance for its own next choice; that hypothesis is never
evidence and never reaches the engineer.

**RCA Analyst.** Synthesizes the assessment from the admitted evidence, retrieved knowledge, and
recorded limitations. It reaches no tool. It may name one unresolved question that gathering could
still answer, and it returns everything through the Supervisor.

Agents are model-backed functions over investigation state. There is no agent base class, no
registry of agents, and no message bus between them.

### The non-agent areas

**Interface.** One screen: incident selection, a compact activity feed, the brief as the dominant
element, one expandable details area, and a question box for a completed investigation. One
streaming request owns a run. It receives the question and presents the answer; the Supervisor
produces the answer. It reaches no model of its own.

**Evidence access.** The registered read-only capabilities and the admission of their results:

- operational tools over the RetailEase records: correlated alerts, logs, metrics, deployments,
  dependencies;
- retrieval over the knowledge collections: runbooks, architecture notes, postmortems and prior
  incidents;
- the governed structured query over an approved operational-records surface;
- one capability additionally exposed through MCP with identical behavior.

A capability is reachable only by being registered. Registration is a static mapping; there is no
dynamic discovery. Every call carries the investigation's remaining deadline and counts against the
same capability-call cap. Every operational result is admitted through one deterministic path;
retrieval passages join the knowledge set, and a failed retrieval is a limitation.

**Investigation Record.** Passive persistence of the one completed-investigation artifact. Save
once, read by identifier. It routes nothing and validates nothing.

**Evaluation** is outside the live system. It reads completed investigations and telemetry after
the fact.

---

## 2. Permitted interactions

```text
  Interface ──► Supervisor            selected incident; question over a completed record
  Supervisor ──► Evidence Investigator   objective, admitted evidence so far, remaining bounds
  Evidence Investigator ──► Evidence access   one capability call with arguments and deadline
  Evidence access ──► Evidence Investigator   one admitted result or one limitation
  Evidence Investigator ──► Supervisor   the result and its proposal for what to check next
  Supervisor ──► RCA Analyst           incident, admitted evidence, knowledge, limitations
  RCA Analyst ──► Supervisor           the assessment proposal, optionally with one question
  Supervisor ──► Investigation Record  save the completed investigation
  Investigation Record ──► Supervisor  the completed investigation, read by identifier for the
                                       question and for reading it back
  Supervisor ──► Interface             activity while running; the brief; the answer
```

The table is conceptual: it names who may reach whom, not request and result classes. No other
direction exists. The Evidence Investigator does not reach the engineer. The RCA Analyst does not
reach evidence access. Nothing writes to the record before completion, and nothing but the
Supervisor writes to it at all.

---

## 3. Seams

**Model access.** One adapter to the chat deployment, used by the three agents and the judge. It
takes a task label and messages, returns structured proposed output, and records the deployment,
latency, and token usage. It is replaceable in tests by a fake and by cassette replay. Prompts live
behind it.

**Persistence.** One repository with `save` and `get`. An in-memory implementation for tests, a
Cosmos implementation for local and hosted runs.

**Telemetry.** One tracing seam every component emits through, correlated by `investigation_id`.
The engineer-facing activity feed is a projection built at the same instrumentation points, so the
two cannot drift. Exporter selected by configuration; Application Insights when hosted.

**Evaluation injection.** The investigation runner accepts one optional internal policy that only
the evaluation harness supplies. It can substitute a fixed next-action source or withhold retrieved
passages at prompt assembly. The harness may also invoke the runner directly with the benign
fixture's incident context; the fixture is not selectable in the product interface. Normal runtime
never supplies the policy, and no API parameter reaches it.

---

## 4. Evidence access capabilities

| Capability | Reads | Kind |
| --- | --- | --- |
| Correlated alerts, incident record | operational records | tool |
| Logs, metrics, deployments, dependencies | operational records | tool |
| Retrieval | knowledge passages | retrieval |
| Structured query | approved operational-records surface | governed query |
| `get_deployments` over MCP | the same registered implementation | protocol exposure |

Retrieval: embed the question, vector search plus a lexical pass over the selected collection,
reciprocal-rank fusion, deterministic promotion of passages whose extracted identifiers match
identifier-like terms in the question, a small passage budget. Passages carry their text and their
reference. No model reranker.

Structured query: the Evidence Investigator asks an operational question; the model proposes a
bounded structure of predicates, projection, optional count, and limit over one approved
collection; deterministic code validates it against the approved surface and translates it into one
parameterized read-only query; the result is admitted like any other. Each row carries the
reference of the record it projects; a count carries the reference of the query operation. No caller
string reaches the query text.

The incident record reaches an agent only in the fields the approved structured-query surface
exposes; its cause and resolution text is excluded on every path.

MCP: `get_deployments` is additionally served through an in-process MCP server built on the
official Python SDK, over stdio, dispatching to the same registered implementation. Transport is
recorded on the activity event and nothing else differs.

---

## 5. Investigation model

One `investigation_id`, minted at selection. It is the persistence key, the telemetry correlation
id, and the handle for a question. There is no turn identity, no session identity, and no
collection of runs under one investigation.

While running, state is in memory for the streaming request: the normalized incident context, the
objective, the bounds, the evidence set, the retrieved passages, the assessment proposal, and the
flags for the one correction and the one return. It is not checkpointed and not recoverable.

When complete, one artifact persists. Its contents belong to `data-and-evidence.md`.

---

## 6. The question over a completed record

One operation: `investigation_id` and question text in; one answer out. The model's only
investigative context is the completed record, and its instruction is to answer from that record or
say the record cannot answer. Its response carries the answer text and the references it cites;
where it refers to a candidate structurally, it may carry that candidate's position in the retained
ordered candidate list. Deterministic code checks what code can check: every cited reference exists
in the record, and any candidate position is valid for the retained assessment. The "no new
conclusion" property is achieved by the constrained context, the instruction, those structured
references, and refusal; code does not and cannot prove that arbitrary prose introduces nothing
new. It gathers no evidence, creates no investigation, and is not a run.

---

## 7. Technology responsibility map

| Responsibility | Realization | Settled in |
| --- | --- | --- |
| Model reasoning and the judge | Azure OpenAI, one chat deployment, one adapter | `runtime-and-deployment.md` |
| Embeddings | Azure OpenAI, one embedding deployment | `runtime-and-deployment.md` |
| Orchestration | One small compiled in-process graph over typed state, no checkpointer | `decisions.md` |
| Knowledge retrieval | Cosmos vector search plus in-process lexical, RRF, identifier promotion | `decisions.md` |
| Structured query | Validated structure to one parameterized Cosmos query | `runtime-and-deployment.md` |
| Operational tools | Read-only adapters over the operational-records container | `runtime-and-deployment.md` |
| MCP | Official Python SDK, in-process, stdio, one capability | `decisions.md` |
| Persistence | Cosmos, one container, one artifact per investigation | `runtime-and-deployment.md` |
| Hosting | One Container App, one image, zero to one replica | `runtime-and-deployment.md` |
| Identity | Container Apps built-in authentication; managed identity with scoped data-plane and model-access roles | `runtime-and-deployment.md` |
| Telemetry | One tracing seam; Application Insights hosted | `runtime-and-deployment.md` |
| Evaluation | Offline runner over completed investigations; one judge | `evaluation.md` |
