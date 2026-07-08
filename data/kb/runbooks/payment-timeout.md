---
id: runbook:payment-timeout
title: payment-api Latency Spikes and Authorization Timeouts
kind: runbook
services: [payment-api, cosmos-db, payment-gateway, checkout-api]
source: "synthetic (RetailEase); structure after real SRE practice"
---

## Symptoms
- `payment-api` `p95_latency_ms` spikes; card authorizations time out.
- Logs contain `Cosmos connection pool exhausted` or `PaymentGatewayTimeout`.
- Upstream `checkout-api` returns 5xx (payment is a critical checkout dependency).

## Likely causes
Two dominant failure modes — determine which before remediating ("is it us or them?"):
- **(a) Cosmos DB connection-pool exhaustion (us).** `payment-api`→`cosmos-db` is a critical
  dependency. If the client connection pool is sized too low (e.g. a config regression), auths
  queue waiting for a connection and time out. Look for `Cosmos connection pool exhausted`.
- **(b) External payment-gateway latency (them).** The 3rd-party card processor is slow, so
  auth calls hang. Look for `PaymentGatewayTimeout` and elevated outbound dependency latency.

## Diagnosis
1. **Application Insights** — `payment-api` latency and failures; split the outbound
   dependency latency between the **Cosmos DB** call and the **payment-gateway** call to see
   which one owns the time.
2. **Cosmos DB (Azure Monitor metrics)** — check `used_ru_pct`, `ru_throttled_rate`, and
   normalized RU consumption. Also inspect the `payment-api` **connection-pool config**
   (max pool size) and compare against the last known-good value.
3. **payment-gateway** — check the vendor status page/health and outbound call latency. If
   only the gateway dependency is slow (Cosmos healthy, no pool errors), the cause is external.
4. **Container Apps revisions** — `az containerapp revision list` for `payment-api`; correlate
   any recent revision/config change (pool size, timeouts) against the latency-onset timestamp.

## Remediation
- **Pool exhaustion (a):** restore the connection-pool size to the known-good value in the
  `payment-api` Container Apps config and deploy a new revision; verify latency recovers. If
  Cosmos is ALSO throttling, follow `runbook:cosmos-db-throttling` (raise RU/s or enable
  autoscale).
- **Gateway latency (b):** apply/tighten client **timeouts**, bounded **retries**, and a
  **circuit breaker** to fail fast instead of hanging; shed non-critical load; engage the
  payment-gateway vendor. Do not roll back an innocent `payment-api` revision for a vendor-side
  outage.
- If a recent `payment-api` revision genuinely introduced the regression, use
  `runbook:deployment-rollback`.

## Escalation
High severity — blocks checkout revenue. Page payment on-call. For gateway-side latency,
open a vendor incident and notify the checkout on-call that upstream 5xx are expected until
the gateway recovers or the circuit breaker trips.
