---
id: postmortem:inc-106
title: "INC-106: Stale catalog prices after a deploy dropped cache invalidation"
kind: postmortem
incident_id: inc-106
services: [catalog-api, redis-cache]
severity: SEV2
source: "synthetic (RetailEase); structure after real SRE practice"
---

# INC-106: Stale catalog prices after a deploy dropped cache invalidation

## Summary
A `catalog-api` refactor removed the cache-invalidation call that ran after a price
write. Writes continued to land in `cosmos-db`, but `redis-cache` kept serving the
previous price until the entry expired on its own, so customers saw prices that had
already changed.

## Impact
- Roughly four hours of stale prices on entries repriced during the window.
- No errors, no latency change, and no alert: every service was healthy and answering.
- Discovered by a merchandising report, not by monitoring.

## Timeline (UTC)
- 08:30: `catalog-api` revision deployed.
- 09:00 to 12:40: Repriced entries continue to be served at their previous price.
- 12:40: Merchandising reports a mismatch between the pricing tool and the storefront.
- 13:05: Responder confirms `cosmos-db` holds the new price and `redis-cache` the old.
- 13:20: Affected keys flushed; the invalidation call restored and deployed.

## Root cause
The refactor moved the price-write handler and did not carry the invalidation call
with it. Nothing failed: the write path succeeded, the read path succeeded, and the
two simply disagreed. Because a stale read is indistinguishable from a fresh one at
the point of use, the fault stayed invisible until someone compared the cache against
the system of record.

## Resolution
- Flushed the affected cache keys so reads fell through to `cosmos-db`.
- Restored the invalidation call after the price write and redeployed.
- Reconciled the pricing report against the system of record.

## Action items
- Add a `stale_read_rate` signal comparing cached values against the system of record
  on a sample of reads, so a divergence is observable rather than reported.
- Treat cache invalidation as part of the write contract in review.

## Lessons learned
A dropped invalidation produces no failure signal at all. The system looks healthy on
every dashboard, because it is: the fault is that two healthy components hold
different answers. Look for it whenever a deploy touched a write path and the symptom
is wrong data rather than failed requests. Stale data explains incorrect answers on
its own; whether it also explains a conflict or a shortfall depends on what else was
happening at the same time.
