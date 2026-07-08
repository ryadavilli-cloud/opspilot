---
id: runbook:redis-cache-degradation
title: Redis Cache Degradation (Eviction Storm or Stale Reads)
kind: runbook
services: [redis-cache, checkout-api, inventory-api]
source: "synthetic (RetailEase); structure after real SRE practice"
---

## Symptoms
Two distinct failure modes — identify which:
- **(a) Memory pressure / eviction storm:** `used_memory_pct` high, `evicted_keys_rate`
  spikes, cache **hit rate drops** (miss surge). Downstream load rises, `checkout-api`
  latency climbs, and users lose sessions/carts (session store evicted).
- **(b) Stale reads:** data served from cache is wrong even though Redis metrics look
  healthy — typically an app bug where a deploy dropped **cache invalidation on writes**, so
  stale inventory availability is read → **oversell**.

## Likely causes
- (a) Working set outgrew the cache tier's memory, or an eviction policy that discards hot
  keys; `redis-cache` backs both session/cart and the hot read cache, so pressure hits both.
- (b) A recent `inventory-api` (or `catalog-api`) revision that stopped invalidating/updating
  cache entries on write, leaving stale values until TTL.

## Diagnosis
1. **Azure Cache for Redis metrics (Azure Monitor)** — `used_memory_pct`, `evicted_keys_rate`,
   **Cache Hit Rate**, connected clients, server load. High memory + high evictions + falling
   hit rate confirms mode (a).
2. If metrics look healthy but data is wrong, suspect mode (b): review **recent deploys** that
   changed cache logic — Container Apps revisions for `inventory-api` — and correlate the
   revision timestamp with when stale/oversell reports began.
3. Cross-check the source of truth (Cosmos DB) against cached values to confirm staleness.

## Remediation
- **Mode (a) eviction storm:** scale the **Azure Cache for Redis** tier / memory up; tune the
  `maxmemory-policy` eviction policy (e.g. `allkeys-lru` for a pure cache, or isolate session
  data so it isn't evicted); add an alert on `used_memory_pct` / `evicted_keys_rate`. Consider
  shorter-TTL or smaller cached payloads.
- **Mode (b) stale-cache bug:** follow `runbook:deployment-rollback` to revert the offending
  revision, then **flush the stale keys** (targeted key delete, or flush the affected
  namespace) so fresh values repopulate from Cosmos. Reconcile any oversold orders.

## Escalation
Mode (a) affecting `checkout-api` latency/sessions is high severity — page on-call and the
platform owner. Mode (b) oversell is high severity due to order-integrity/customer impact —
engage the `inventory-api` owning team and notify order-fulfillment about reconciliation.
