# OpsPilot - Runtime and Deployment

**How does OpsPilot run, how is it deployed to Azure, and how is the deployment verified?**

## Purpose and Document Boundaries

This document owns the runtime shape, its Azure realization, and the checks that prove a deployment
works. It is organized in three parts: runtime design, deployment realization, and operational
verification. A runtime obligation is not a deployment step, and neither is a verification check.

It does not own behavior or meaning. Stages, routing, bounds, and outcomes belong to
`workflow-design.md`. Evidence, citation, assessment, and brief semantics belong to
`data-and-evidence.md`. Components and authority belong to `system-design.md`. Corpus, metrics, and
scoring belong to `evaluation.md`. Merge and implementation rules belong to `code-guidelines.md`.

`system-design.md` settles Azure as the hosting environment and Azure OpenAI as the model provider.
Every other product named below is selected here.

OpsPilot is a bounded hosted demonstration. Where a simpler runtime satisfies the requirements, it
is chosen over a more reliable or more scalable one.

---

## Part I - Runtime Design

### 1. Process Topology and Replica Posture

One application, one image, one process.

The API surface, the orchestration runtime, all three agent roles, the Evidence Access Layer, and
the MCP server realization run inside that single process or its container. Agent roles are
responsibilities in code, not processes and not services.

The baseline hosted runtime scales between zero and one replica:

```text
minimum replicas: 0
maximum replicas: 1
```

One replica is deliberate. Active turn state lives in process memory, so a second replica would
require either affinity or shared active state, and neither is worth building for a demonstration.
There is no multi-replica active-turn support, no affinity, no distributed active state, and no claim
of horizontal scalability. Horizontal scaling remains a considered future concern with no baseline
machinery.

Several investigations may run concurrently as asynchronous operations inside the one process,
subject to a small configured concurrency limit.

### 2. Turn Execution and Activity Streaming

One live streaming HTTP request owns one turn from start to finish. The same request:

1. creates the turn;
2. emits the investigation and turn identities as its first event;
3. emits activity, tool, retrieval, evidence, and agent events as they happen (NFR-53);
4. executes gathering and synthesis;
5. runs the grounding gate;
6. persists the completed-turn artifact;
7. emits the terminal outcome with its brief once that commit succeeds, or a controlled execution
   failure;
8. ends.

Steps 6 and 7 are ordered deliberately. A successful terminal outcome is never emitted before
persistence succeeds. Where the commit fails, the stream emits a failed execution instead, and no
completed turn exists.

There is no create-then-attach pair, no job dispatch, and no work that continues after the request
returns. The response is a streaming HTTP body the engineer-facing client reads directly; it does not
require the browser `EventSource` API.

The engineer-facing client is static content served by the same Container App over these same
ordinary and streaming requests. There is no second frontend deployment, ingress, CDN, or hosting
service, and no WebSockets. The streamed activity events are the ephemeral display projection
`system-design.md` ("Activity projection") defines: they are not persisted or replayed, the client
never queries Application Insights, and durable post-turn visibility comes from the retained
completed turn.

### Interaction transports

Only two shapes exist: a streaming request that owns a turn, and an ordinary request that does not.

| Interaction | Transport |
| --- | --- |
| Start a turn from a predefined incident | Streaming request |
| Follow-up question | Ordinary request, answered from retained state |
| Handoff or status summary | Ordinary request, answered from retained state |
| Retrieve an investigation | Ordinary request returning retained state and completed turns |

Reading an investigation returns retained state and completed turns only. It cannot attach to a turn
in flight.

**No reconnection.** A client cannot reattach to a running turn. There is no event buffering, event
replay, sequence cursor, or task lookup, because none is needed once a turn is owned by one request.
If the connection is lost before completion, the active turn may be lost, no incomplete turn record
remains, and the engineer starts the turn again.

**A turn ends with its request.** A turn runs to completion, exhausts a bound, or ends because the
request carrying it disconnected. No active-turn registry, cancellation endpoint, or cancellation
signal map exists, because nothing outside the request needs to reach the turn it owns.

### 3. Live and Persisted State

| State | Where it lives | Lifetime |
| --- | --- | --- |
| Active turn working state, admitted evidence before commit, draft assessment | Process memory | The streaming request |
| Completed turns, briefs, evidence, assessments, follow-up history, trace references | Cosmos DB | Retained |

Nothing in the first row is checkpointed, replicated, or recovered. There is no active-turn
store, no pending-turn record, no checkpoint store, no replay log, and no background reconciler
(NFR-57).

The Supervisor commits the completed-turn artifact at turn completion and is its only writer. What
the retained row holds is what survives (NFR-22, NFR-55). What an incomplete turn leaves behind
belongs to `workflow-design.md`.

### 4. Concurrency and Deadlines

Independent evidence actions within a turn may be issued together. They share the turn's remaining
wall-clock deadline rather than each carrying an independent one, so no operation can outlive the
turn that owns it, and completed results from a group are preserved when a sibling times out.

Every model and source operation receives a timeout no greater than the turn's remaining time.
Configured bound values live in configuration (§13); what the bounds mean belongs to
`workflow-design.md`.

### 5. Runtime Failure Behavior

Where the application remains healthy enough to synthesize, ground, persist, and deliver a
trustworthy brief, a source or model failure is disclosed as a limitation and the turn completes.
Where it cannot, the attempt produces no completed-turn artifact and is visible on the stream and
in telemetry (NFR-19); a persistence failure is never reported as a successfully completed turn.
What a failed execution is, and which conditions fall there, belong to `workflow-design.md`
("Failure, Degradation, and Observability").

---

## Part II - Deployment Realization

### 6. Azure Services

Six services, and no more. Together they are what running in Azure means for this system (NFR-51):

| Service | Role |
| --- | --- |
| Azure Container Apps | Hosts the one application |
| Azure OpenAI | Chat and embedding deployments |
| Azure Cosmos DB for NoSQL | Investigation Record, knowledge collections, operational records |
| Azure Container Registry | Stores the application image |
| Azure Monitor with Application Insights | Traces, logs, and usage |
| Microsoft Entra ID | Caller authentication and workload identity |

Deliberately absent: no PostgreSQL or other relational database, no Azure AI Search, no Service Bus
or any queue, no Key Vault, no cache, no workflow service, no separate MCP Container App, and no
database that exists only to hold active turns.

### 7. Container Hosting and Cold Starts

One Container App runs one image built from one Dockerfile. Scale is zero to one replica.

Where the selected MCP library requires a companion process, it is launched inside the same
container alongside the application. It is not a second Container App, a second image, or a
separately deployed Azure service.

Scaling to zero when idle is what makes the environment startable on demand rather than maintained
as a running service (NFR-52). Scale-to-zero means the first request after idle pays a cold start.
That is accepted demonstration behavior. Operationally it is handled one of two ways: issue a warm-up
request before a planned demonstration, or temporarily set minimum replicas to one for the
demonstration window and return it to zero afterwards.

Cold starts are accepted scale-to-zero behavior: noted when they occur, not measured as a service
objective, and no part of any availability or latency guarantee. They justify no queue, no durable
dispatch, no always-on worker, and no active-turn persistence.

### Ordinary downtime is tolerated, not engineered around

The environment may be stopped or idle between demonstrations, and nothing keeps it warm on its
behalf. A request arriving then may wait for a cold start, and a request arriving while the
environment is stopped may simply fail. Neither is a defect, because no availability is promised
(NFR-54).

This is a posture, not a mechanism. It introduces no health-check retry policy, no readiness gating,
no automatic warm-up, and no uptime target. The two operational handling options above are things a
person may choose to do before a planned demonstration, not behavior the system performs for itself.

### 8. Local Development

Local development and evaluation run the same application process directly, outside Container Apps
(NFR-50). There is no second architecture and no local orchestration stack.

Configuration comes from local environment variables or an ignored local secret file. The model
connection uses the configured Azure OpenAI endpoint and API key. Cosmos access uses developer
credentials or configured local access against the same containers and scoped roles.

The component, adapter, model, and persistence seams are identical to the hosted runtime, so
behavior stays logically equivalent. Tests may replace dependencies at those seams with
deterministic fakes or fixtures where live Azure access adds nothing.

No local Kubernetes cluster, local Service Bus, local workflow engine, or full Azure emulator stack
is required.

### 9. Model Connectivity

Azure OpenAI is the model provider, reached through one narrow adapter so the application depends on
configuration rather than provider-specific calls spread through the code.

The adapter is configured with:

- endpoint or base URL;
- API credential;
- deployment name;
- role-specific parameters;
- an API or version compatibility setting where the selected SDK requires one.

Three deployments serve the baseline: one primary chat deployment for evidence interpretation and
RCA synthesis, one lower-cost chat deployment for a bounded simple task, and one embedding
deployment where retrieval uses Azure OpenAI embeddings. There is no dedicated reranking service
and no model reranker; runtime reranking is deterministic (`decisions.md` D-003).

Because endpoint, credential, and deployment name are configuration, moving to another
OpenAI-compatible endpoint would be a small adapter and configuration change. Portability is not a
product requirement, and no claim is made that a provider change is always a one-setting change.
There is no provider factory, no fallback chain, and no routing policy engine.

### 10. Cosmos Layout and Access

One Cosmos DB for NoSQL account carries every persisted concern, separated logically rather than by
buying more services:

```text
Cosmos account
├── OpsPilot database
│   └── investigations container             [application read/write]
└── RetailEase database
    ├── knowledge container                   [application read-only]
    └── operational-records container         [application read-only]
```

The investigations container holds the investigation identity, completed turns, admitted evidence
belonging to those turns, assessments and delivered briefs where produced, follow-up history, and
trace references. It is created by the first successful completed-turn commit. What a failed first
execution leaves behind, and which turns produce no assessment or brief, belong to
`workflow-design.md`.

Evaluation artifacts are not stored in these containers, and no path mutates a completed turn after
it is committed. What a completed turn does and does not carry belongs to `data-and-evidence.md`.

The knowledge container holds the three routed logical collections retrieval requires (runbooks,
service knowledge, incident history), distinguished by a collection category field on every
document; routing selects a category filter, not a container. The operational-records container
holds the structured operational facts the authored incidents need: incidents and alerts,
deployment and change records, service and dependency records, and remediation or ticket records.

The application writes only to the investigations container and holds read-only access everywhere
else. A separate setup identity populates the RetailEase containers with synthetic corpus data.

Partitioning follows the obvious access paths, by investigation for the Record and by entity or
incident for the corpus. No further containers are added unless a requirement makes one necessary.

### 11. Retrieval and Structured-Query Realization

**Retrieval** runs over the knowledge container, with the collection category field selecting the
routed logical collection. Each selected collection is searched for semantic similarity using
vector search over stored embeddings, and for exact operational identifiers using term matching
over the same records, with metadata filters narrowing either path by service, entity, or time. The
two candidate sets are fused and reranked down to the passages actually supplied for reasoning, and
what returns is the matched passage itself with its provenance.

The corpus is seven authored incidents and its supporting knowledge. Where a Cosmos query operates as
a full scan at that size, that is acceptable so long as correctness and demonstration behavior hold.
Nothing here is designed for production search scale. Index configuration, embedding and reranking
method, chunking, and fusion detail belong to `decisions.md`.

Reranking is deterministic at runtime: after fusion, passages whose extracted identifiers match the
query's identifiers, or whose metadata matches a requested entity or window, are stably promoted
before the passage budget is applied (`decisions.md` D-003). No model reranker exists in the
baseline; adding one would be an explicit change to that decision record, never a fallback the
application takes on its own.

**Structured query** generates a bounded Cosmos NoSQL query against the operational-records
container. The governed path is: an approved schema context describing the permitted collection,
fields, predicates, projections, and the count aggregate; a generated query; deterministic
validation before anything executes; parameterized, read-only execution under a result limit and
timeout; a normalized result; and evidence admission. The representable structure is the baseline
subset `system-design.md` ("Operational and structured access") defines; grouping, ordering, and
non-count aggregate forms have no representation in that structure, so model output proposing one
fails structured decoding or validation and is rejected before any source execution.

The requirement is natural-language-to-structured-query, not natural-language-to-relational-SQL. No
relational database, relational role administration, or general query compiler is introduced.
Provider syntax and provider errors never leave the Evidence Access boundary.

### 12. Identity, Secrets, and Network Posture

This section is where identity and secret handling are settled, and approved data access is what the
scoped roles below define (NFR-13).

**Stored data.** The application uses managed identity with scoped Cosmos data-plane roles: read and
write on the investigations container, read-only on every RetailEase container. The write boundary is
enforced by the role assignment, not by application convention (NFR-1).

**Model access.** Azure OpenAI uses API-key authentication in this baseline. Locally the key comes
from an ignored environment file or environment variable; in Azure it is held as a Container Apps
secret. Key Vault is not introduced. The key is never committed, logged, emitted in traces, included
in health output, or written into a completed-turn artifact.

The accurate statement of this posture is: no long-lived operational-data credential is embedded in
code; the Azure OpenAI key is held as a deployment secret. The runtime is not secretless.

**Callers.** Caller authentication uses Container Apps built-in authentication with one Entra
application registration, which is the smallest credible posture for a hosted demonstration. No
roles, groups, tenant administration, or authorization policy machinery is created.

**Network.** The baseline uses public service endpoints protected by authentication, TLS, scoped
data-plane roles, and simple resource firewall rules where they are available. No VNet, private
endpoint, private DNS, or stable outbound IP is provisioned. Private networking is a future option if
the demonstration ever needs it, and unused network infrastructure is not provisioned in advance.

### 13. Configuration

Configuration covers:

- model endpoint, key reference, and deployment names;
- Cosmos endpoint and container names;
- execution bounds;
- enabled capabilities;
- telemetry connection;
- environment name.

The configured execution bounds are the six enforcement mechanisms `workflow-design.md` ("Bounded
Investigation") defines: the turn deadline, the capability-call cap, the model-call cap, the
per-operation transport-retry cap, the shared correction allowance, and the further-evidence cycle.
Context is bounded by prompt assembly and the retrieval passage budget, and token usage is measured
rather than separately budgeted; no context-token ledger exists.

Required configuration is validated at startup, and the application refuses to start with an
undefined authorization posture or an unapproved capability enabled. Secret values never appear in
configuration dumps or health output.

### 14. Observability

Telemetry correlates one investigation and turn end to end across: agent role, model call, tool,
retrieval, structured-query and MCP operation, evidence admission, grounding result, terminal outcome
or execution failure, latency, model and tool call counts, token usage, and approximate cost
(NFR-14, NFR-18).

That is enough to reconstruct a run locally, diagnose a smoke-test failure, and troubleshoot a hosted
demonstration without redeploying to add instrumentation (NFR-20). No dashboards, alert rules,
retention tiers, service objectives, or production monitoring organization are defined. Secret and
raw source content are filtered before anything is emitted.

### 15. Build and Deployment

One image, one Container App, one Bicep deployment, one GitHub Actions workflow.

The workflow restores dependencies, runs static checks and tests, runs the advisory evaluation
signal, builds and publishes the image, applies Bicep, deploys a new revision, and runs smoke
verification. The evaluation signal informs; it does not gate merge.

Deployment is a new revision plus a readiness check. There is no staged rollout, canary, or
production release process.

---

## Part III - Operational Verification

### 16. Verification Suite

Eight environment-dependent checks prove a deployment. Behavior the environment does not change is
owned by deterministic tests in `code-guidelines.md` ("Testing Expectations"), including a lost
request leaving nothing persisted, structured-query rejection, and MCP parity; evaluation aggregates
those results. Investigation quality belongs to
`evaluation.md`.

| Check | Confirms |
| --- | --- |
| 1. Application starts and reports health | The image, configuration, and dependencies are viable |
| 2. Caller authentication works | An unauthenticated caller is refused and an authenticated one admitted |
| 3. Model call succeeds without secret leakage | Azure OpenAI is reachable and the key appears in no log, trace, or health output |
| 4. Cosmos permissions hold | The application writes the Record and is refused a write to any RetailEase container |
| 5. One end-to-end streamed turn completes | Identities arrive first, activity streams, a brief and outcome arrive, and the persisted completed-turn artifact for that turn exists; exhaustive ordering logic and persistence-failure branches are owned by deterministic tests (`code-guidelines.md`) |
| 6. Citations resolve after restart | A completed turn's evidence references still resolve once the process has been replaced |
| 7. Telemetry reconstructs one turn | One investigation and turn can be followed end to end with its usage reported |
| 8. Deployment from Bicep is repeatable | The environment can be recreated from declared infrastructure |
