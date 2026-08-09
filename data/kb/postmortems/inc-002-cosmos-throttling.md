---
id: postmortem:inc-002
title: Cosmos DB 429 throttling degrades inventory and catalog reads
kind: postmortem
incident_id: inc-002
services: [cosmos-db, inventory-api, catalog-api]
severity: SEV2
source: "synthetic (RetailEase); structure after real SRE practice"
# Machine-checkable recurrence signature — the known-issue fast path verifies a candidate match
# against these before trusting this postmortem's resolution. Mirrors the answer key.
required_signals:
  - metrics:cosmos-db:ru_throttled_rate
  - logs:inventory-api:error
disqualifying_signals:
  - metrics:redis-cache:evicted_keys_rate
affected_versions:
  - catalog-api@1.9.0
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
- ~27 minutes of degraded reads on `inventory-api` and `catalog-api`.
- `ru_throttled_rate` elevated; `used_ru_pct` pinned near 100% for the container.
- Checkout availability checks slowed and intermittently failed, contributing to a
  smaller rise in `checkout-api` `http_5xx_rate` (secondary effect).
- No data loss; the bulk import itself completed later after being rate-limited.

## Timeline
All times UTC on 2026-05-28. No application revision change to `inventory-api` or
`checkout-api` triggered this; the trigger was `catalog-api`'s scheduled
bulk-import job, shipped as `dep-20260528-01` (`catalog-api@1.9.0`).

- 09:00: The bulk-import rollout (`dep-20260528-01`) ships, issuing a query with no supporting index.
- 09:10: `used_ru_pct` and `ru_throttled_rate` begin climbing toward the provisioned ceiling.
- 09:15: Cosmos DB starts returning `429 TooManyRequests`; `inventory-api` and `catalog-api` log the throttled reads.
- 09:16: `ru_throttled_rate` crosses alert threshold; Azure Monitor alert fires; on-call paged.
- 09:20: `inventory-api` `p95_latency_ms` climbs as throttled reads queue; responder identifies the bulk-import job as the RU consumer and the query as unindexed.
- 09:28: Import job throttled/paused to relieve RU pressure; `used_ru_pct` begins dropping.
- 09:36: Missing composite index added; provisioned RU floor raised and autoscale enabled.
- 09:42: `ru_throttled_rate` returns to zero; reads recover. Incident resolved.

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
