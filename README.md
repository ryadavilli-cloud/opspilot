# OpsPilot

OpsPilot is an agentic incident-investigation assistant over RetailEase, a synthetic e-commerce
microservices environment, hosted on Azure.

When an alert fires, an on-call engineer typically spends the first fifteen to twenty minutes
gathering context before real diagnosis can begin: logs, metrics, recent changes, dependencies,
runbooks, and similar past incidents. The same visible symptom often has several plausible causes,
and the engineer has to work out which one the evidence supports, what remains uncertain, and what
can safely be done now. OpsPilot does that first pass and delivers one concise brief the engineer
can question afterwards.

The question I wanted to answer was not whether an agent could produce an incident brief. It was
when an investigation that adapts to what it finds earns its complexity over a predetermined path,
and the evaluation is built so that the answer can come back no.

OpsPilot recommends, and the engineer stays the investigator. Every path is read-only, so there is
no write path to guard: none was built. I authored RetailEase rather than pointing this at a real
environment, so every scenario is reproducible and every answer checkable. The scope is deliberate:
this is not a production incident-management platform and is not measured as one.

## Why it is interesting

The hard part of an agent like this is not getting a model to call tools. It is deciding what the
model is allowed to decide, and making the rest impossible rather than discouraged.

- The evidence path is not scripted: each observation informs the next choice. One scenario is
  built so the decisive evidence is only nameable after something earlier in the run reveals it.
- Retrieved knowledge and current operational evidence are separate trust classes. A runbook or a
  past postmortem can shape interpretation; neither can stand as proof of what is happening now,
  and code enforces that at delivery rather than asking the model to remember it.
- The model proposes a structured query; code validates it against an approved surface and runs one
  parameterized read-only statement. Natural language never reaches the data store.
- Retrieval is hybrid: vector search and a lexical pass fused by rank, with exact operational
  identifiers promoted deterministically, because an embedding does not reliably distinguish
  `checkout-api` from `checkout-web`.
- Analysis can hand work back to gathering exactly once, when synthesis names a material unresolved
  question, and code decides whether that return is granted.
- The engineer watches what each agent and capability did and what it obtained, built from the same
  facts as the traces and never chain-of-thought.

## How an investigation works

Three roles with distinct responsibilities: a Supervisor that turns the incident into an objective
and holds the bounds, an Evidence Investigator that decides what to gather next through registered
read-only capabilities, and an RCA Analyst that is the sole owner of causal synthesis.

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

The split of authority is explicit:

| Models decide | Deterministic code controls |
| --- | --- |
| What the investigation must establish, from the incident context | The deadline, the capability-call cap, the model-call cap, the one correction, the one return |
| Which evidence to gather next: which capability, with what arguments, to answer what question | The registered inventory, and authorization of every proposal against it, the questions already put, the calls already made, and the remaining budget |
| The structure of a query over approved operational data | Validation against the approved surface, then one parameterized read-only execution |
| The causal assessment: candidates, what supports and weakens each, unknowns | Admission: only a successful result becomes evidence, an empty result becomes a citable absence, a failure becomes a stated limitation |
| Recommended actions, and whether retrieved guidance or own judgement produced each | Grounding: every material claim rests on evidence this run admitted, and retrieved knowledge never counts as current proof |
| One unresolved question that could justify returning to gathering | Whether the return is authorized, the outcome, persistence, and delivery order |

Models propose; code authorizes. A proposal naming a capability that does not exist is refused, a
repeated call is refused by signature, a run cannot outlive its deadline, and an assessment
claiming more than was observed gets one correction and then an explicit failure that persists
nothing. A mutating capability is not forbidden by policy; it is absent from the surface.

Untrusted content gets the same treatment: incident text, tool output, retrieved passages, and the
engineer's question are data beneath authored instructions, and what the model proposes afterwards
is still bounded, admitted, and grounded. That limits what a persuaded model can do without
claiming prompt-injection immunity. [docs/architecture.md](docs/architecture.md) states where the
limit stops.

## What was actually validated

**Gates.** Lint, format, `mypy` in strict mode with no override list, and a deterministic test lane
that replays seven committed cassettes, one per authored scenario, recorded through the same Azure
adapter the application ships. They pass without suppression or the change is not done.

**Scenario evaluation.** Eight scenarios: seven authored incidents across overlapping failure
families, each with an authored expectation of what a correct investigation establishes, plus one
benign fixture where the correct answer is that no immediate action is warranted. In the final
recorded run all eight completed and **five passed every deterministic check**:

- Two investigations reached a defensible conclusion without ever checking change history, where
  the answer key expects that check. Their briefs read well; they simply never looked.
- The benign fixture settled a cause on a run where the scenario expects restraint.

These were left as findings. Tuning the prompt until they passed would have removed the evidence.

**Controlled comparisons.** Two, run live with one variable changed at a time.

- *Adaptive value*, on the scenario built for it: a second contributor that nothing in the opening
  symptom points at. Across four observations the model reached both contributors once, ran out of
  time once, and stopped at an honest partial answer once. The comparison against the fixed-order
  baseline reported a difference on an ordinary log entry, not on the second contributor. The
  mechanism is in place and the claim is testable, and **it has not been cleanly demonstrated.**
- *Retrieval influence*: the same investigation with retrieved passages visible to reasoning and
  with them withheld. **Observed in one of three paired attempts.** The other two were not
  evaluable, because in each of them one arm retrieved nothing to compare.

**A baseline with no model in it.** A nearest-history shortcut answers straight from the closest
past incident. On the deployment scenario it recommended the rollback the real investigation had
examined and declined: confident, cheap, and wrong. On the recurrence scenario it was right and had
verified nothing. That is what a retrieval-only system would have said.

**Semantic judgement.** An offline judge scores each brief on a deliberately different model family
from the one that produced it. It is advisory, runs after the deterministic checks, is reported
beside them and never folded into one number.

**Hosted.** Every deploy finishes by running a smoke check against the revision it just shipped: an
unauthenticated caller is refused, a real investigation runs end to end, the persisted record is
read back from a separate request, and every reference the brief cites resolves from that record.
The current revision passed it.

The recorded observations are in [docs/engineering-notes.md](docs/engineering-notes.md). They
describe what those runs did, not what future runs will do.

## Technology

- Python 3.12, FastAPI, `uv`
- LangGraph: a small in-process graph for the investigation flow. Application code owns the state
  and the execution bounds; there is no checkpointer and no durable workflow.
- Azure OpenAI: one chat deployment for every runtime model task, one embedding deployment, called
  keyless as the managed identity
- Claude Opus 5 in Microsoft Foundry: the offline judge, a different model family from the runtime
  it scores
- Azure Cosmos DB: the corpus, the completed investigations, and the vector search behind retrieval
- Hybrid retrieval: Cosmos vector search plus in-process BM25, fused by reciprocal rank
- MCP: one capability additionally exposed through an in-process stdio server, transport recorded
- Azure Container Apps behind built-in authentication, Bicep infrastructure, an OIDC GitHub Actions
  deploy with a post-deploy smoke run
- Application Insights: one tracing seam, every span correlated by investigation id

## What building it taught

- Components that pass in isolation can be silent in composition: retrieval was present, wired, and
  never meaningfully reached, and only an end-to-end evaluation showed it.
- Predicting a model's choices is the fragile half of a proof. Tests asserting which tool would be
  called broke on correct behavior; the durable checks assert what the run established instead.
- Nondeterminism hid in the ranking, not the model. Tied retrieval scores were ordered by
  hash-seeded set iteration, which made recorded runs unreplayable until every tie had a stable key.
- An evaluator can encode the opposite of its own contract and still look green, which is what the
  benign-scenario check did until a failing run exposed it.
- Deployment failures are diagnosed faster from the platform's own telemetry than from probing the
  endpoint, which is the argument OpsPilot itself makes.

## Going deeper

**Start here**

- [docs/DEMO.md](docs/DEMO.md): how to run a live investigation and what to watch for, scenario by
  scenario.

**Technical deep dives**

- [docs/architecture.md](docs/architecture.md): shape, authority per concern, trust boundaries.
- [docs/evaluation.md](docs/evaluation.md): what is checked deterministically, how the two
  comparisons are built, what the judge does and does not decide.
- [docs/engineering-notes.md](docs/engineering-notes.md): the engineering retrospective. What
  worked, what did not work reliably, and what the failures revealed.

**Detailed engineering reference**

- [requirements.md](docs/requirements.md): what it must accomplish, and what is out of scope
- [system-design.md](docs/system-design.md): components, seams, capabilities, technology map
- [workflow-design.md](docs/workflow-design.md): one investigation over time
- [data-and-evidence.md](docs/data-and-evidence.md): references, admission, grounding, the brief
- [runtime-and-deployment.md](docs/runtime-and-deployment.md): hosting, configuration, verification
- [decisions.md](docs/decisions.md): settled choices, each with its reason and its cost
- [code-guidelines.md](docs/code-guidelines.md): binding rules for changing the code

```text
src/    implementation          tests/  deterministic tests
eval/   runner, comparisons, judge, cassettes
data/   synthetic RetailEase corpus and answer key
infra/  Azure infrastructure and deployment
```

## Quickstart

```bash
uv sync --group dev --group data      # runtime + dev dependencies
uv run pytest -m "not llm" -q         # the deterministic CI lane
uv run uvicorn opspilot.api:app --reload
```

The investigation screen is at `http://localhost:8000/investigation`. The deterministic lane needs
nothing else: it replays recorded runs and reaches no service.

A live run reaches the same Azure resources the hosted application uses, keyless. Copy
`.env.example` to `.env`, fill in the Azure OpenAI, Cosmos, and judge endpoints, and sign in with
`az login` as an identity holding the data-plane roles. Offline evaluation runs from the same
environment; a kept run and the investigations behind it are listed at
`http://localhost:8000/agentops`.

```bash
uv sync --group dev --group data --group llm
uv run --group llm uvicorn opspilot.api:app --reload
uv run --group dev --group llm python eval/run_evaluation.py --full --keep "milestone"
```
