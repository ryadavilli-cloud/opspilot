---
id: postmortem:inc-105
title: "INC-105: Cart sessions dropped when redis-cache reached its memory ceiling"
kind: postmortem
incident_id: inc-105
services: [redis-cache, checkout-api]
severity: SEV2
source: "synthetic (RetailEase); structure after real SRE practice"
---

# INC-105: Cart sessions dropped when redis-cache reached its memory ceiling

## Summary
`redis-cache` reached its configured `maxmemory` and began evicting under an
`allkeys-lru` policy. Cart and session keys were evicted alongside cold read-cache
entries, so `checkout-api` lost sessions mid-flow and fell back to slower reads from
`cosmos-db`. Raising the ceiling and separating the eviction policy stopped it.

## Impact
- `used_memory_pct` sat at the ceiling for roughly 35 minutes.
- `evicted_keys_rate` climbed sharply; `hit_rate` fell from about 0.95 to about 0.6.
- `checkout-api` `p95_latency_ms` roughly doubled as reads missed cache.
- A minority of customers were returned to an empty cart and had to start again.

## Timeline (UTC)
- 11:20: A scheduled catalog warm-up job loads a large batch of product entries.
- 11:35: `used_memory_pct` reaches the ceiling; eviction begins.
- 11:40: `hit_rate` drops and `checkout-api` latency rises; alert fires.
- 11:52: Responder identifies eviction rather than a cache outage.
- 12:10: Memory ceiling raised and the warm-up job capped; metrics recover.

## Root cause
Session state and hot read-cache entries shared one keyspace under one eviction
policy. When total memory reached the ceiling, `allkeys-lru` was free to evict a live
cart session as readily as a cold catalog entry, because neither carried a hint about
which one mattered. The warm-up job was the trigger, not the cause: any sustained
growth would have reached the same ceiling.

## Resolution
- Raised the `maxmemory` ceiling to restore headroom.
- Capped the warm-up job's batch size.
- Moved session keys to a separate logical database with `volatile-ttl`, so a live
  session is no longer an eviction candidate while cold entries remain.

## Action items
- Alert on `evicted_keys_rate` above zero, not only on memory saturation.
- Track cache headroom as a capacity metric reviewed before seasonal peaks.

## Lessons learned
Eviction reads as a latency incident rather than a cache failure: the cache is up and
answering, it is simply answering less often. `hit_rate` and `evicted_keys_rate`
together tell that story faster than latency alone. See
`runbook:redis-cache-degradation`.
