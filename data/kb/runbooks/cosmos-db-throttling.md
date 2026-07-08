---
id: runbook:cosmos-db-throttling
title: Cosmos DB 429 Throttling (RU Exhaustion)
kind: runbook
services: [cosmos-db, inventory-api, catalog-api]
source: "synthetic (RetailEase); structure after real SRE practice"
---

## Symptoms
- `cosmos-db` returns **429 TooManyRequests**; `ru_throttled_rate` climbing.
- `used_ru_pct` near 100%.
- `inventory-api` and/or `catalog-api` show read failures, retries, and elevated
  `p95_latency_ms`. If inventory reads fail, checkout can surface 5xx upstream.

## Likely causes
Provisioned RU/s for the affected container is exhausted. Common drivers:
1. **Unindexed / inefficient query** scanning far more RUs than needed.
2. **Hot partition** — a skewed partition key concentrating load on one physical partition,
   so it throttles even while total provisioned RU/s looks adequate.
3. **Traffic or bulk-job spike** — e.g. a `catalog-api` bulk import or a demand surge pushing
   aggregate RU consumption over the provisioned ceiling.

## Diagnosis
1. **Azure Cosmos DB metrics (Azure Monitor)** — Total Requests split by status **429**;
   **Normalized RU Consumption** per container/partition-key range (a single hot partition at
   100% while others are idle indicates hot-partition or a bad key).
2. **Diagnostic Logs / Log Analytics** — identify the specific **query** and **container**
   burning RUs; inspect request charge (RU/request).
3. **Recent changes** — was a `catalog-api` bulk import or index-policy change deployed? Check
   Container Apps revisions and any data-load jobs correlating with the throttle onset.

## Remediation
- **Query/indexing:** add or adjust the container **indexing policy** to cover the hot query;
  fix the query to be partition-scoped.
- **Capacity:** raise provisioned **RU/s**, or enable **autoscale** on the container to absorb
  spikes. Right-size afterward to control cost.
- **Bulk job:** throttle or reschedule the offending import (lower concurrency / bulk RU cap)
  so it stops starving live reads.
- **Hot partition:** plan a partition-key change to a higher-cardinality key; short term,
  raise RU/s to relieve the hot partition.

## Escalation
Severity scales with impact: if `inventory-api` throttling is causing `checkout-api` 5xx,
treat as high and page the data/on-call owner. If only `catalog-api` (browse) is affected,
it is lower severity. Loop in the team that owns any correlated bulk job.
