---
id: postmortem:inc-001
title: Payment authorization timeouts from Cosmos DB connection-pool exhaustion
kind: postmortem
incident_id: inc-001
services: [payment-api, cosmos-db, checkout-api]
severity: SEV2
source: "synthetic (RetailEase); structure after real SRE practice"
---

# Payment authorization timeouts from Cosmos DB connection-pool exhaustion

## Summary
During the evening traffic peak, payment authorizations began timing out and
`checkout-api` returned elevated `http_5xx_rate` to customers. The trigger was a
configuration change that shrank `payment-api`'s Azure Cosmos DB connection pool
from 100 to 10 connections. Under peak load the pool was exhausted, authorization
requests queued waiting for a connection, exceeded their timeout, and surfaced as
503s at checkout. Reverting the pool size restored service.

## Impact
- ~34 minutes of degraded checkout: `checkout-api` `http_5xx_rate` peaked around 12%.
- Payment authorization `p95_latency_ms` rose from ~180 ms to >5,000 ms (timeout ceiling).
- Customer impact: intermittent failed checkouts and abandoned carts during peak.
- No data loss; no duplicate charges (authorizations that timed out never completed).

## Timeline
All times UTC. Active revision at incident start: `payment-api` revision
`payment-api--rev-47` (deployed earlier same day with the config change).

- 18:52 — Config change to `payment-api--rev-47` reduces Cosmos DB max pool size 100 -> 10. No immediate effect at low traffic.
- 20:05 — Evening peak begins; `payment-api` `p95_latency_ms` starts climbing.
- 20:11 — First "connection pool exhausted" errors logged by `payment-api`; authorizations begin queuing.
- 20:14 — `checkout-api` `http_5xx_rate` crosses alert threshold; Azure Monitor alert fires; on-call paged.
- 20:23 — Responder correlates payment-api latency spike and pool-exhausted logs to `payment-api--rev-47` in Application Insights.
- 20:31 — Config reverted (pool size back to 100); new revision `payment-api--rev-48` activated via Container Apps.
- 20:39 — `p95_latency_ms` and `http_5xx_rate` return to baseline. Incident resolved.

## Root cause
A configuration change reduced `payment-api`'s Azure Cosmos DB client connection
pool from 100 to 10. At peak concurrency the ten connections were fully in use;
additional authorization requests blocked waiting to borrow a connection. The wait
exceeded the request timeout, so authorizations failed. `payment-api` returned
errors upstream, which `checkout-api` translated into 503 responses. The change was
low-risk in appearance and shipped without load validation, so the ceiling was only
hit under real peak traffic.

## Resolution
- Reverted the connection-pool configuration from 10 back to 100.
- Activated a corrected `payment-api` revision and shifted 100% traffic to it.
- Confirmed pool utilization, `p95_latency_ms`, and checkout `http_5xx_rate` recovered.

## Action items
- Add an Azure Monitor alert on connection-pool saturation (in-use connections
  approaching max) for `payment-api`, ahead of latency/5xx symptoms.
- Guardrail risky configuration changes: require review and a load check for
  connection-pool, timeout, and concurrency settings before rollout.
- Run a capacity review to size the Cosmos DB connection pool against measured peak
  concurrency, with headroom.

## Recurrence signature
- `checkout-api` `http_5xx_rate` elevated (503s to customers) during traffic peak.
- `payment-api` `p95_latency_ms` spikes toward the request timeout ceiling.
- `payment-api` logs contain "connection pool exhausted" / connection-wait timeouts.
- Often correlated with a recent `payment-api` revision that changed pool/timeout config.

If these symptoms match, follow `runbook:payment-timeout`.
