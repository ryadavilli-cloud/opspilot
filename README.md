# OpsPilot

OpsPilot is an agentic incident-investigation assistant over RetailEase, a synthetic e-commerce
microservices environment, hosted on Azure.

When an alert fires, an on-call engineer typically spends the first fifteen to twenty minutes
gathering context before real diagnosis can begin: logs, metrics, recent changes, dependencies,
runbooks, and similar past incidents. The same visible symptom often has several plausible causes,
and the engineer must work out which one the evidence supports, what remains uncertain, and what
can safely be done now. OpsPilot prepares that initial investigation and delivers it as one
concise, evidence-supported brief the engineer can question afterwards.

OpsPilot recommends; it does not remediate or mutate the systems it investigates. Every access on
every path is read-only, and the synthetic environment is deliberate: it makes every scenario
reproducible and every answer checkable.

## The agentic investigation

One investigation is carried out by three model-directed roles with distinct responsibilities: a
Supervisor that interprets the incident into an objective and holds the bounds, an Evidence
Investigator that decides what evidence to gather next through registered read-only capabilities,
and an RCA Analyst that is the sole owner of causal synthesis. The evidence path is not scripted:
each observation informs the next choice, so different incidents take demonstrably different
paths. When synthesis names one material unresolved question that gathering could still answer,
deterministic code may authorize one bounded return to gathering. Throughout, deterministic code
owns every limit, admits every piece of evidence, checks the assessment against what was actually
observed, and persists the completed investigation before anything is delivered.

```text
  Incident
     ↓
  Supervisor: objective + bounds
     ↓
  Evidence Investigator
     ↓
  choose capability → observe result
          ↑                │
          └──── adapt ─────┘
     ↓
  RCA Analyst
     ↓
  need one more discriminating check?
     ├─ yes → bounded return to evidence gathering
     └─ no
          ↓
  deterministic grounding
     ↓
  persisted investigation
     ↓
  brief + follow-up questions
```

The activity an engineer watches is a compact projection of actions and outcomes, never
chain-of-thought.

## Model decisions and deterministic authority

The investigation is genuinely model-directed, and authority stops in exactly stated places.

| Models decide | Deterministic code controls |
| --- | --- |
| What the investigation must establish, from the incident context | The deadline, the capability-call cap, the model-call cap, the one correction, the one return |
| Which evidence to gather next: which capability, with what arguments, to answer what question | The registered capability inventory; authorization of every proposal against it, the questions already put, the calls already made, and the remaining budget |
| The structure of a governed query over approved operational data | Validation against the approved surface and translation into one parameterized read-only query |
| The causal assessment: candidates, what supports and weakens each, unknowns | Admission: only a successful source result becomes evidence, an empty result becomes a citable absence, a failure becomes a stated limitation |
| Recommended actions, and whether retrieved guidance or own judgement produced each | Grounding: every material claim must rest on evidence this run admitted, and retrieved knowledge may never stand as current proof |
| One unresolved question that could justify returning to gathering | Whether the return is authorized, the outcome (complete, partial, inconclusive), persistence, and delivery order |

The compact rule this implements: models propose; code authorizes.

## Try one investigation

Start inc-004: checkout-api returning 500s shortly after this morning's deployment.

A deployment really did occur near the failure. Watch what evidence the investigator chooses,
whether later observations strengthen or weaken that initial correlation, how candidate causes are
expressed with supporting and weakening evidence, and what deterministic checks run before the
brief is delivered. Things worth looking for: capability choices changing in response to what came
back, a possible return to gathering, grounding passing before delivery, each recommended action
naming whether retrieved guidance or the analyst's own judgement produced it, and a refused
proposal if one occurs. After the run, ask the record: was the morning deployment actually
responsible, and what evidence supports that conclusion?

Setup and the screen's address are in the quickstart below.

The full guide to reading a live run, scenario by scenario, is [docs/DEMO.md](docs/DEMO.md).

## Technology

- Python 3.12, FastAPI, `uv`
- LangGraph: one small compiled in-process graph over typed state, no checkpointer
- Azure OpenAI: one chat deployment for every runtime model task and one embedding deployment,
  called keyless as the managed identity
- Claude Opus 5 in Microsoft Foundry: the offline evaluation judge, deliberately a different
  model family from the runtime it scores, keyless
- Azure Cosmos DB: the prepared corpus (knowledge and operational records) and the completed
  investigations, including vector search for retrieval
- Hybrid retrieval: vector search plus an in-process BM25-style lexical pass, combined by
  reciprocal-rank fusion, with deterministic promotion of exact identifier matches
- MCP: one capability additionally exposed through an in-process stdio server on the official
  Python SDK
- Azure Container Apps at zero to one replica, behind built-in authentication, with the one
  secret in Key Vault
- Bicep infrastructure and an OIDC GitHub Actions deploy with a post-deploy smoke run
- One tracing seam correlated by investigation id, exported to the Log Analytics workspace with
  a workspace-based Application Insights component over it

## Architecture at a glance

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

The high-level design behind this shape, in reading order: what the system must accomplish in
[docs/requirements.md](docs/requirements.md), the shape, authority, and trust boundaries in
[docs/architecture.md](docs/architecture.md), and component responsibilities, seams, and the
technology map in [docs/system-design.md](docs/system-design.md).

## What the system demonstrates

- Adaptive evidence paths rather than a fixed diagnostic script: the next capability is chosen
  from what has already been observed.
- Three distinct responsibilities: Supervisor, Evidence Investigator, and RCA Analyst, with
  Supervisor-mediated coordination.
- Synthesis-driven feedback: analysis can request one bounded return to gathering, and code
  decides whether it is granted.
- Execution bounds no agent can widen: a deadline propagated into every model and capability
  call, a capability-call cap, a model-call cap, one correction, one return.
- Typed, read-only capabilities behind one registry; a mutating capability is structurally
  absent, not merely forbidden.
- Deterministic evidence admission and a deterministic grounding gate between the assessment and
  delivery.
- Operational evidence held apart from retrieved knowledge, with different trust: knowledge
  informs interpretation and can never establish the current incident's cause.
- Hybrid retrieval combining semantic and lexical signals, with exact identifiers (service
  names, error codes, deploy ids) deterministically promoted.
- A governed, read-only structured query: the model proposes a bounded structure; code validates
  it against an approved surface and executes one parameterized query.
- One capability additionally exposed through MCP with the same behavior, transport recorded.
- One persisted completed investigation per run, written before delivery, then questionable:
  answers cite only references the record carries, checked by code.
- Activity and telemetry built from the same facts at the same call sites, correlated end to end
  by one investigation id.

## Reliability by construction

The defenses are structural: each failure mode meets a mechanism, not a guideline.

| Failure | Structural response |
| --- | --- |
| A proposal names a capability that does not exist | Refused against the registered inventory; the refusal is recorded and visible |
| A request does not fit the capability | Typed parameters validated at dispatch; the governed query validated against its approved surface before anything executes |
| The same question or call is proposed again | Refused by the questions already put and the call signatures already executed |
| A run tries to run forever | The deadline travels into every model and capability call; capability and model calls are capped |
| The assessment claims more than was observed | The deterministic grounding gate returns issues; one correction, then explicit failure |
| A retrieved document is offered as current evidence | Evidence and knowledge are separate trust classes; the gate refuses a knowledge reference as operational support |
| A source cannot answer | A stated limitation, never a fabricated observation; an authoritative empty answer stays citable as an absence |
| Synthesis returns something unusable | Structural admission refuses it; one correction, then a sanitized failed execution that persists nothing |
| Anything attempts remediation | The capability surface is read-only on every path, including MCP, by construction |

## Evidence that the system works

**Deterministic tests.** The repository-wide gates at this tree: `ruff check` and
`ruff format --check` clean, `mypy` strict clean over 63 source files with no override list, and
the deterministic lane `pytest -m "not llm"` at 657 passed with 1 deselected (the one test that
calls a live deployment). Three committed cassettes replay whole recorded investigations, taken
through the same Azure adapter the application ships, so the deterministic lane replays real runs
rather than scripted calls.

**Authored scenario evaluation.** Seven authored incidents across five overlapping failure
families, each carrying an authored expectation of what a correct investigation establishes, plus
one distinct benign fixture where the correct answer is that no immediate action is warranted.

**Controlled comparisons.** Two falsification tests, run live with one variable changed each. In
the recorded runs, the adaptive path reached required evidence on the ambiguous deployment
scenario that the same tools in a fixed order never did, and on the recurrence scenario the
investigation with retrieved passages visible to reasoning differed from the same investigation
with them withheld on every dimension the comparison watches. Both are observations from those
runs, recorded in [docs/engineering-notes.md](docs/engineering-notes.md), not guarantees about
future runs.

**Semantic evaluation.** An offline LLM judge scores each delivered brief on a model deliberately
different from the one that produced it, so the judge's blind spots are not the system's own:
Claude Opus 5 in Microsoft Foundry, pinned to a concrete version, while every runtime task stays
on the Azure OpenAI chat deployment. With one authored rubric it returns a category for four
qualities of the brief plus the semantic diagnosis match, per scenario. It is advisory, runs after
the deterministic checks, is reported beside them and never combined into one number, and a
verdict outside its vocabulary is refused rather than repaired. The method is
[docs/evaluation.md](docs/evaluation.md).

## Quickstart

```bash
uv sync --group dev --group data      # runtime + dev dependencies
uv run pytest -m "not llm" -q         # the deterministic CI lane
uv run uvicorn opspilot.api:app --reload
```

The investigation screen is at `http://localhost:8000/investigation`. A live local investigation
reaches the same Azure resources the hosted application uses, keyless: copy `.env.example` to
`.env`, fill in the Azure OpenAI and Cosmos endpoints, and sign in with `az login` as an identity
holding the data-plane roles. The deterministic test lane needs none of that.

## Repository map

```text
README.md

docs/
  requirements.md          what OpsPilot must accomplish
  architecture.md          shape, authority, trust boundaries
  system-design.md         components, seams, technology map

  workflow-design.md       one investigation over time
  data-and-evidence.md     references, admission, evidence versus knowledge
  runtime-and-deployment.md  hosting, configuration, hosted verification
  evaluation.md            checks, comparisons, the judge
  decisions.md             settled choices, each with why and cost

  engineering-notes.md     what building and hosting it revealed
  DEMO.md                  how to read a live demonstration
  code-guidelines.md       binding rules for changing the code

src/       implementation
tests/     deterministic tests
eval/      offline evaluation: runner, comparisons, judge, cassettes
data/      synthetic RetailEase corpus and answer key
infra/     Azure infrastructure and deployment
```
