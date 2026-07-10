---
id: runbook:catalog-search-latency
title: Catalog Search Latency Degradation
kind: runbook
services: [catalog-api, redis-cache]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# Catalog Search Latency Degradation

## Summary
This runbook covers elevated p95/p99 latency on catalog-api search endpoints
(`GET /v1/catalog/search`) where results are correct but slow. This is distinct
from search *timeouts* or empty result sets — here queries succeed but exceed the
250ms p95 SLO.

## Symptoms
- Application Insights: `requests` for `search` operation show p95 > 400ms.
- `dependencies` telemetry shows increased duration on the search index lookup.
- No increase in HTTP 5xx; user complaints about "sluggish search box".

## Likely causes
1. Search index warm cache in redis-cache expired en masse (TTL stampede).
2. Query fan-out to too many catalog partitions after a category re-taxonomy.
3. Large `pageSize` values from a misbehaving client bypassing the 50-item cap.
4. Missing composite index for a new facet filter (brand + priceBand).

## Diagnosis
1. In Log Analytics, run:
   ```kusto
   requests
   | where name has "catalog/search"
   | summarize p50=percentile(duration,50), p95=percentile(duration,95) by bin(timestamp, 5m)
   ```
2. Check redis-cache hit ratio for the `search:*` keyspace via the Cache metrics blade.
3. Inspect top slow queries in the catalog-api structured logs (`slowQueryMs` field).
4. Confirm no active catalog reindex job is running (see reindex control table).

## Mitigation
- If TTL stampede: enable jittered TTLs and pre-warm hot categories via the
  `catalog-warmer` scheduled job.
- If oversized pages: reject `pageSize > 50` at the gateway; return 400.
- If missing index: create the composite facet index during a low-traffic window;
  reindex is online and non-blocking.
- Scale catalog-api replicas to absorb the tail while indexes rebuild.

## Verification
- p95 back under 250ms for 30 minutes.
- redis-cache `search:*` hit ratio > 90%.

## Escalation
Page the Catalog on-call. If a reindex is required, involve the Data Platform team
for partition-key guidance before running.
