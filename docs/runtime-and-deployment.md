# OpsPilot Runtime and Deployment

**How does OpsPilot run, how is it hosted in Azure, and how is a deployment verified?**

This document owns runtime execution, hosting realization, configuration, and hosted verification.
It describes a capstone-sized posture. Nothing here is a production availability, scaling, or
security architecture, and the resource list is what the current design needs, not a contract on
service count.

---

## 1. Runtime posture

One application, one process, one container image, one Container App, zero to one replica.

One streaming HTTP request owns one investigation run: it mints the `investigation_id`, streams
activity as the graph executes, saves the completed investigation, and ends by streaming the brief
or a failure. In-progress state lives in that request's memory and nowhere else. If the request
disconnects, the run is abandoned and nothing is persisted. There is no reconnection, no job, no
queue, no worker, and no checkpoint.

A question over a completed investigation is an ordinary request that reads the record and returns
one answer.

---

## 2. Transport

| Interaction | Transport |
| --- | --- |
| Start an investigation from a selected incident | Streaming request; ordinary HTTP streaming body, newline-delimited events |
| Ask a question about a completed investigation | Ordinary request |
| Read a completed investigation | Ordinary request |
| Health and version | Ordinary requests |

The stream carries: the investigation identity first, then activity events as they happen, then one
terminal event with the brief and outcome or the sanitized failure category. Activity events are a
compact projection of what the run did; they carry no prompts, no hidden reasoning, and no
provider-shaped content.

The engineer-facing screen is one static page served by the same application: incident selection,
the activity feed, the brief, one expandable details area, and the question box.

---

## 3. State

| State | Lives | Lifetime |
| --- | --- | --- |
| In-progress investigation: objective, bounds, evidence set, passages, proposal, flags | Process memory | The streaming request |
| Completed investigation, with the contents `data-and-evidence.md` states | Cosmos, one container, keyed by `investigation_id` | Retained |
| Corpus: knowledge passages, operational records | Cosmos, prepared offline | Retained |

The completed investigation is saved once, before the terminal event. The repository is `save` and
`get`; an in-memory implementation serves tests. No compare-and-swap, lease, outbox, or version
protocol is needed for one writer at zero to one replica.

---

## 4. Concurrency and deadlines

One deadline per investigation, propagated into every model and capability call so nothing outlives
the run. Concurrent investigations in one replica are isolated by construction: each run's state is
local to its request.

---

## 5. Azure

| Resource | Why |
| --- | --- |
| Container Apps environment and one app, replicas 0 to 1 | Hosts the application, starts on demand |
| Container Registry | Holds the image |
| One Azure OpenAI account with one chat deployment and one embedding deployment | Every model task, the judge, and query embeddings |
| One Cosmos account: `investigations`, `knowledge`, `operational-records` containers | The completed record, the prepared corpus |
| Log Analytics and Application Insights | Telemetry sink |
| Managed identity and role assignments | The application reads the corpus, writes only completed investigations, and calls the model deployments as its managed identity; corpus preparation writes the corpus under a separate identity |
| Container Apps built-in authentication with one app registration | Caller authentication; presence of an authenticated caller is the whole check |
| OIDC deployment workflow | Builds, pushes, deploys, smokes |

Absent by design: Service Bus, workers, queues, Key Vault unless a secret genuinely needs it, VNet,
private endpoints, HA, DR, scaling rules, a second frontend, a second chat deployment.

---

## 6. Model connectivity

One adapter to Azure OpenAI. One chat deployment serves objective interpretation, evidence-source
selection, structured-query proposal, synthesis, correction, the question, and the offline judge.
One embedding deployment serves corpus preparation and query embedding. Every model call records
its task label, deployment, latency, and token usage. Cassette replay and a fake model stand in for
deterministic tests.

---

## 7. Cosmos realization

Three containers. `knowledge` holds section-level passages with text, embedding, collection
category, extracted identifiers, and reference; retrieval reads it with vector search and reads the
same category-filtered candidates for the lexical pass. `operational-records` holds the RetailEase
records the tools and the structured query read; the query is one parameterized read-only statement
over an approved surface. `investigations` holds one document per completed investigation.

The application identity holds read on the corpus and contributor on `investigations` only.
Preparation writes the corpus under a different principal.

---

## 8. Configuration and secrets

Configuration is environment variables with a validated startup. The application refuses to start
with a required setting missing or a capability enabled that the registry does not know, and says
which setting by name and never its value. Model access is keyless: the application calls the
model deployments as its managed identity, and no provider key exists. No secret enters source,
configuration files, images, logs, telemetry, health output, or artifacts.

---

## 9. Telemetry

One tracing seam, correlated by `investigation_id`, with spans for the run, each phase or agent
step, each model call, each capability call including transport (`direct` or `mcp`), admission,
grounding and its issues, persistence, and the terminal outcome or failure category. Application
Insights is the hosted sink; the in-memory exporter serves tests. The startup record names the
running revision and image tag so a deployment can be joined to the application that started from
it. This is a troubleshooting baseline: no dashboards, alerts, metric registry, or telemetry viewer.

---

## 10. Local development

`uv` for everything. The application runs locally against the in-memory repository, the fake or
replay model, and fixture corpora, or against real Azure OpenAI and Cosmos where a check needs
them. Corpus preparation is a separate offline script with its own identity.

---

## 11. Hosted verification

A small smoke suite runs after each deployment. It proves: the application started and reports
healthy at the deployed revision; an authenticated caller is admitted and an unauthenticated one is
refused; one investigation streams identity, activity, and a terminal brief; the completed record
is readable afterwards and its citations resolve; a question about it is answered; and the run's
telemetry is queryable by `investigation_id` in Application Insights. Behavior the environment does not change is owned by
deterministic tests, not repeated here.
