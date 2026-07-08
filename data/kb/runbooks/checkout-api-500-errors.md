---
id: runbook:checkout-api-500-errors
title: checkout-api Returning 5xx (Customer Checkout Failures)
kind: runbook
services: [checkout-api, payment-api, inventory-api]
source: "synthetic (RetailEase); structure after real SRE practice"
---

## Symptoms
- `checkout-api` returns HTTP 500/503 to customers; `http_5xx_rate` elevated on the edge.
- Customer-facing checkout failures ("something went wrong at checkout"), abandoned carts.
- May coincide with elevated `p95_latency_ms` on `checkout-api` as it waits on downstreams.

## Likely causes
`checkout-api` is the edge **orchestrator** for the synchronous checkout path. A 5xx here is
USUALLY a **downstream dependency failure surfacing upward**, not a fault in checkout itself.
Ranked by likelihood:
1. `payment-api` failing or timing out (critical dependency) — e.g. Cosmos pool exhaustion or
   payment-gateway latency (see `runbook:payment-timeout`).
2. `inventory-api` failing or timing out (critical dependency) — e.g. Cosmos throttling
   (see `runbook:cosmos-db-throttling`).
3. `redis-cache` degradation adding latency/misses (see `runbook:redis-cache-degradation`).
4. LEAST likely: a genuinely bad `checkout-api` revision. A recent checkout deploy is a
   **hypothesis to verify, not an assumption**.

## Diagnosis
1. In **Application Insights**, open **Failures** for `checkout-api`; group by failed
   **dependency** to identify WHICH downstream call is throwing/timing out. Follow the
   operation to the failing span.
2. Check `payment-api` and `inventory-api` `p95_latency_ms` and error rates. Confirm whether
   downstream latency/errors **preceded** the checkout 5xx onset (they almost always do when a
   dependency is the cause).
3. Consult the dependency graph: checkout→payment (critical), checkout→inventory (critical).
   The failing critical dependency is your prime suspect.
4. Review recent **Container Apps revisions** for checkout AND the suspected downstream. In
   the Azure portal / `az containerapp revision list`, compare each service's last deploy
   timestamp against the error-onset timestamp from App Insights.
5. Beware the coincidence trap: a checkout deploy that merely **precedes** a
   payment-gateway-caused outage is not the cause. Confirm ordering before acting.

## Remediation
- If a downstream dependency is the root cause (usual case): do NOT roll back checkout.
  Execute the matching runbook — `runbook:payment-timeout`, `runbook:cosmos-db-throttling`,
  or `runbook:redis-cache-degradation`.
- Only if a bad `checkout-api` revision **genuinely correlates** (deploy timestamp aligns with
  onset AND no downstream errors preceded it): follow `runbook:deployment-rollback` to shift
  ingress traffic back to the last-known-good checkout revision.
- Consider temporary graceful degradation (fail fast / clear customer messaging) while the
  downstream is repaired.

## Escalation
High severity — this is the customer-facing revenue path. Page the checkout on-call
immediately. Pull in the owning team for whichever downstream (`payment-api` /
`inventory-api`) is identified. If the payment-gateway is implicated, engage the vendor
liaison per `runbook:payment-timeout`.
