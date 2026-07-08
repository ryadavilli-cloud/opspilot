---
id: postmortem:inc-002
title: Cosmos DB 429 throttling degrades inventory and catalog reads
kind: postmortem
incident_id: inc-002
services: [cosmos-db, inventory-api, catalog-api]
severity: SEV2
source: "synthetic (RetailEase); structure after real SRE practice"
---

# Cosmos DB 429 throttling degrades inventory and catalog reads

## Summary
A catalog bulk-import job ran an unindexed query that spiked Azure Cosmos DB
request-unit (RU) consumption to the provisioned ceiling. Cosmos DB began returning
`429 TooManyRequests`, throttling reads for `inventory-api` and `catalog-api`. Because
checkout performs inventory availability checks, throttling degraded checkout
reliability as well. Adding the missing index and throttling the import restored
normal RU headroom.

## Impact
- ~41 minutes of degraded reads on `inventory-api` and `catalog-api`.
- `ru_throttled_rate` elevated; `used_ru_pct` pinned near 100% for the container.
- Checkout availability checks slowed and intermittently failed, contributing to a
  smaller rise in `checkout-api` `http_5xx_rate` (secondary effect).
- No data loss; the bulk import itself completed later after being rate-limited.

## Timeline
All times UTC. No application revision change triggered this; the trigger was a
scheduled catalog bulk-import job. Active revisions: `catalog-api--rev-19`,
`inventory-api--rev-33`.

- 09:40 — Catalog bulk-import job starts, issuing a query with no supporting index.
- 09:44 — `used_ru_pct` climbs toward 100%; Cosmos DB starts returning `429 TooManyRequests`.
- 09:47 — `ru_throttled_rate` crosses alert threshold; Azure Monitor alert fires; on-call paged.
- 09:52 — `inventory-api` and `catalog-api` surface elevated read latency and 429-derived errors in Application Insights.
- 09:58 — Responder identifies the bulk-import job as the RU consumer and the query as unindexed (high RU/query in diagnostics).
- 10:06 — Import job throttled/paused to relieve RU pressure; `used_ru_pct` begins dropping.
- 10:14 — Missing composite index added; provisioned RU floor raised and autoscale enabled.
- 10:21 — `ru_throttled_rate` returns to zero; reads recover. Incident resolved.

## Root cause
The catalog bulk-import executed a query without a supporting composite index, so
Cosmos DB scanned far more data than necessary and consumed RUs at a rate that
saturated the container's provisioned throughput. Once `used_ru_pct` reached the
ceiling, Cosmos DB throttled with `429 TooManyRequests` across all consumers of that
container — including the interactive `inventory-api` and `catalog-api` read paths,
not just the batch job. Shared throughput plus an unindexed hot query turned a
background task into a customer-facing degradation.

## Resolution
- Added the missing composite index so the import query no longer scans/consumes
  excessive RUs.
- Throttled (rate-limited) the bulk-import job so batch work cannot monopolize RUs.
- Raised the provisioned RU floor and enabled Cosmos DB autoscale to absorb spikes.

## Action items
- Index review for all import/batch queries before they run against production
  containers; reject unindexed high-RU queries.
- Enable RU autoscale (or a higher floor) so transient spikes do not immediately throttle.
- Rate-limit import jobs and, where possible, isolate batch workloads from
  interactive read throughput.

## Recurrence signature
- Cosmos DB returns `429 TooManyRequests` to `inventory-api` / `catalog-api`.
- `ru_throttled_rate` rising above zero; `used_ru_pct` near 100% on the container.
- Read latency up on inventory/catalog; often coincident with a batch/import job.

If these symptoms match, follow `runbook:cosmos-db-throttling`.
