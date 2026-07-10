---
id: postmortem:inc-103-catalog-search-timeout
title: "INC-103: Catalog Search Timeouts After Reindex"
kind: postmortem
services: [catalog-api, redis-cache, cosmos-db]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# INC-103: Catalog Search Timeouts After Reindex

## Summary
A full catalog reindex ran during business hours and saturated catalog-api, causing
search requests to time out (HTTP 504) for roughly 35 minutes. Browse and PDP pages
were unaffected; only the search endpoint degraded.

## Impact
- Search 504 rate peaked at ~22% for ~35 minutes.
- Estimated single-digit-percent dip in add-to-cart from search during the window.
- No data corruption; the reindex itself completed successfully.

## Timeline (UTC)
- 13:00 — A catalog taxonomy change triggers a full reindex job (misconfigured to run now,
  not in the off-peak window).
- 13:06 — Search p99 climbs; first 504s appear as the index rebuild competes for resources.
- 13:12 — Alert on search availability; incident opened.
- 13:18 — Identified concurrent reindex consuming cosmos-db RUs and evicting the warm
  search cache in redis-cache.
- 13:22 — Mitigation: throttled the reindex job's concurrency and RU budget; pre-warmed
  top categories.
- 13:41 — Search 504s subside; latency normalizes.
- 14:30 — Reindex completes at reduced concurrency; incident resolved.

## Root cause
The reindex job had no off-peak schedule guard and no resource governor, so it ran at
full concurrency during peak traffic, starving live search of Cosmos throughput and
cold-flushing the search cache.

## Contributing factors
- Reindex and live-serving workloads shared the same Cosmos throughput.
- Cache warm-up was not part of the reindex completion step.

## Resolution
- Added a schedule guard: reindex only runs in the off-peak window unless explicitly forced.
- Gave the reindex job a bounded RU budget and lower concurrency.
- Reindex now finishes with a cache pre-warm step for hot categories.

## Action items
- [ ] Isolate reindex throughput from live-serving (separate throughput/container).
- [ ] Add a canary that fails the reindex job if launched during peak without override.
- [ ] Alert earlier on search p99 before 504s occur.

## Lessons learned
Heavy background jobs must be scheduled off-peak and resource-governed so they cannot
starve interactive, latency-sensitive paths.
