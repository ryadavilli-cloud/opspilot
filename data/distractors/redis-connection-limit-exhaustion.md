---
id: runbook:redis-connection-limit-exhaustion
title: Redis Connection-Limit Exhaustion
kind: runbook
services: [redis-cache, checkout-api, catalog-api]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# Redis Connection-Limit Exhaustion

## Summary
Covers exhaustion of the *connection* limit on Azure Cache for Redis, where clients
fail to acquire connections. This is deliberately adjacent to — but NOT — the memory
eviction-storm scenario. Here memory is fine; the constraint is concurrent connections.

## Symptoms
- Clients throw `RedisConnectionException` / "No connection is available".
- Azure Monitor Redis metric `Connected Clients` at or near the tier limit.
- `Used Memory` is normal; eviction rate is near zero (this is the tell-tale distinction).

## Likely causes
1. A service creating a new `ConnectionMultiplexer` per request instead of a singleton.
2. Connection leak: multiplexers not reused after a transient failure/reconnect.
3. Replica count scaled up without accounting for per-replica connection fan-out.
4. Undersized cache tier for the current number of app replicas.

## Diagnosis
1. In Azure Monitor, chart `Connected Clients` vs. the tier max and correlate with
   Container Apps replica scaling events.
2. Confirm `Used Memory` and `Evicted Keys` are flat — rules out the eviction scenario.
3. Review app startup logs to ensure a single shared multiplexer per process.
   ```kusto
   traces | where message has "RedisConnectionException"
   | summarize count() by cloud_RoleName, bin(timestamp,5m)
   ```

## Mitigation
- Enforce a singleton `ConnectionMultiplexer` per process; fix any per-request creation.
- Set a sane `PoolSize`/max connections and reuse across the app.
- Temporarily reduce over-aggressive replica maxReplicas to lower connection fan-out.
- If genuinely at capacity, scale the Redis tier up (higher connection ceiling).

## Verification
- `Connected Clients` well below the tier limit with headroom.
- `RedisConnectionException` rate returns to zero.

## Escalation
If scaling the tier, coordinate a brief maintenance note. For a suspected client leak,
hand off to the owning service team with the offending `cloud_RoleName`.
