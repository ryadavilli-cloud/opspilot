---
id: runbook:deployment-rollback
title: Deployment Rollback (Azure Container Apps Revisions)
kind: runbook
services: [checkout-api, notification-worker, inventory-api]
source: "synthetic (RetailEase); structure after real SRE practice"
---

## Symptoms
- Incident onset lines up (roughly) with a recent deploy of a RetailEase service.
- A change (`checkout-api`, `inventory-api`, `notification-worker`, etc.) is **suspected** as
  the cause of elevated errors/latency.

## CRITICAL FIRST STEP — verify correlation before rolling back
Rolling back an innocent deploy wastes time and does not fix the incident. Confirm ALL of:
1. **Timing:** the deploy timestamp precedes AND closely aligns with the error-onset timestamp
   from Application Insights — not minutes-to-hours apart.
2. **Path:** the deployed service is actually **in the failing path**. A `checkout-api` deploy
   is irrelevant to a payment-gateway-caused outage; an `inventory-api` deploy is irrelevant to
   a Service Bus backlog.
3. **Rule out coincidence:** check whether a downstream dependency's errors/latency
   **preceded** the deployed service's errors. If a downstream broke first, the deploy is a
   red herring — go to the matching runbook (`runbook:payment-timeout`,
   `runbook:cosmos-db-throttling`, `runbook:redis-cache-degradation`,
   `runbook:service-bus-backlog`) instead.
Only when timing + path + no-earlier-downstream-cause all hold should you roll back.

## Procedure (Azure Container Apps)
1. List revisions: `az containerapp revision list -n <app> -g <rg> -o table`. Identify the
   **current** (suspect) revision and the **previous last-known-good** revision.
2. Shift **ingress traffic** to the last-known-good revision:
   `az containerapp ingress traffic set -n <app> -g <rg> --revision-weight <good-rev>=100`
   (set the bad revision to `=0`). This is the rollback — no rebuild required.
3. **Verify recovery:** watch `http_5xx_rate` / `p95_latency_ms` (or the relevant metric) in
   Azure Monitor return to baseline and confirm the failing dependency in App Insights clears.
4. Then investigate the bad revision offline (diff config/image, logs) before re-deploying.

## Post-rollback reconciliation
- **Worker case (`notification-worker`):** dead-letter any poison messages so the good
  revision drains cleanly (see `runbook:service-bus-backlog`).
- **Cache-bug case (`inventory-api`):** flush stale cache keys so fresh values repopulate
  (see `runbook:redis-cache-degradation`); reconcile any oversold orders.
- **General:** reconcile any partial/inconsistent state written by the bad revision against
  Cosmos DB (the system of record).

## Escalation
Match the severity of the underlying incident. If rollback does **not** restore service, the
deploy was not the root cause — re-open diagnosis and return to the dependency-specific
runbook. Page the owning team for the affected service.
