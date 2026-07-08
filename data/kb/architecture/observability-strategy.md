---
id: architecture:observability-strategy
title: RetailEase Observability & Investigation Strategy
kind: architecture
services: [checkout-api, payment-api, inventory-api, catalog-api, notification-worker, service-bus, cosmos-db, redis-cache, payment-gateway, email-provider]
source: "synthetic (RetailEase); structure after real SRE practice"
---

# RetailEase Observability & Investigation Strategy

RetailEase is observed through **Azure Monitor**. This document describes what telemetry exists, where it lives, how alerts relate to incidents, and the recommended method for investigating a customer-facing symptom.

## What telemetry exists and where

- **Logs** — application and platform logs are collected in **Log Analytics**. Query these for error detail, stack traces, and correlation with metric spikes.
- **Metrics** — **Azure Monitor** platform metrics plus custom metrics emitted per entity (listed below).
- **Traces, failures, dependency latency** — **Application Insights** provides distributed traces, failed-request analysis, and per-dependency latency. This is the primary tool for following a request across `checkout-api` and its downstream calls.
- **Deploy history** — **Azure Container Apps revisions** record what shipped and when. A revision change is a candidate correlation for a symptom that began at a specific time.
- **Dependency map** — the service dependency map (`architecture:service-dependency-map`) defines the directed edges and the critical checkout path used to reason about blast radius.

## Key metrics per entity

Services (`checkout-api`, `payment-api`, `inventory-api`, `catalog-api`, `notification-worker`):
- `http_5xx_rate` — server-error rate; the primary signal that a service is failing requests.
- `p95_latency_ms` — 95th-percentile request latency; the primary signal that a service is slow.

Entity-specific metrics:
- `inventory-api`: `reservation_error_rate` — rate of failed stock reservations.
- `notification-worker`: `restart_count` — container restarts, indicating crash loops or instability.
- `cosmos-db`: `ru_throttled_rate` — rate of throttled (429) requests; `used_ru_pct` — provisioned throughput utilization.
- `service-bus`: `active_message_count` — queue backlog of unconsumed order events.
- `redis-cache`: `used_memory_pct` — memory utilization; `evicted_keys_rate` — rate of keys evicted under memory pressure.

## How alerts relate to incidents

A single root cause typically fires an **alert storm** across its blast radius rather than one clean alert. For example, a `cosmos-db` throughput exhaustion (`ru_throttled_rate` up, `used_ru_pct` at 100%) fires:

- a **root-cause alert** on the upstream dependency (`cosmos-db` throttling), plus
- **symptom alerts** on the services that depend on it (`payment-api` and `inventory-api` `http_5xx_rate` / `p95_latency_ms`), plus
- the **customer-facing alert** on `checkout-api`, since it orchestrates both.

The customer-facing alert is usually what **opens the investigation**, but it is the symptom, not the cause. The set of alerts firing together outlines the blast radius; the dependency map tells you which alert is upstream of the others.

## Recommended investigation method

1. **Start from the customer-facing symptom.** This is almost always at `checkout-api` (failed or slow checkouts) — the edge where upstream failures surface.
2. **Walk the dependency graph downstream.** From `checkout-api`, follow its critical edges to `payment-api` and `inventory-api`, then to their dependencies (`cosmos-db`, `payment-gateway`, `redis-cache`). Failure propagates upstream, so the root cause is downstream of where you first see the symptom.
3. **Correlate metrics + logs + recent deploys.** At each hop, check the entity's key metrics (above), pull matching logs from Log Analytics, and note any Container Apps revision that shipped just before the symptom began.
4. **Use Application Insights for traces and failures.** Follow individual failed requests across service boundaries to confirm exactly which downstream call is failing or slow, and to measure per-dependency latency.
5. **Triage by critical path.** A symptom on the synchronous checkout path (payment/inventory) outranks one that is off it. A `service-bus` backlog (`active_message_count`) or `notification-worker` instability (`restart_count`) delays notifications asynchronously and is inherently lower severity than a checkout-blocking failure.

**On recent deploys:** a recent deploy is a **hypothesis to verify by correlation, not an automatic culprit.** Confirm it by lining up the deploy timestamp with the onset of the symptom and the affected entity's metrics/logs before concluding it is the cause. Incidents also arise from load, data growth, throughput exhaustion, or external-dependency degradation with no deploy involved.
