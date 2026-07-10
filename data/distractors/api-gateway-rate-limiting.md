---
id: runbook:api-gateway-rate-limiting
title: API Gateway Rate Limiting and 429s
kind: runbook
services: [checkout-api, catalog-api, payment-api]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# API Gateway Rate Limiting and 429s

## Summary
Covers client-facing HTTP 429 (Too Many Requests) returned by the API gateway /
ingress in front of the RetailEase Container Apps. This is *gateway* rate limiting —
not Cosmos DB RU 429 throttling (which is a data-tier concern, covered separately).

## Symptoms
- Clients receive HTTP 429 with `Retry-After` from the gateway (not from cosmos-db).
- Gateway metrics show throttled request counts rising for a specific API key/route.
- Application Insights shows requests rejected before reaching backend containers.

## Likely causes
1. A single client (bot, integration, load test) exceeding its per-key quota.
2. Global limit too low for a legitimate traffic surge (sale/flash event).
3. Misconfigured burst policy after a gateway policy deploy.
4. Retry storm: clients retrying 429s without backoff, amplifying the load.

## Diagnosis
1. Identify top talkers by subscription/API key in gateway analytics.
2. Distinguish gateway 429 from data-tier 429:
   ```kusto
   requests
   | where resultCode == 429
   | summarize count() by tostring(customDimensions.throttleSource), bin(timestamp,5m)
   ```
   `throttleSource == "gateway"` confirms this runbook (vs. `cosmos`).
3. Check whether `Retry-After` is being honored by the offending client.

## Mitigation
- Abusive single client: apply a stricter per-key policy or temporarily block the key.
- Legitimate surge: raise the rate-limit policy and scale backend replicas together.
- Retry storm: publish guidance / enforce exponential backoff + jitter; enable
  `Retry-After` compliance checks.

## Verification
- 429 rate at the gateway returns to baseline.
- Legitimate clients succeed; abusive traffic remains capped.

## Escalation
Policy changes go through the Platform/API-gateway owners. For suspected abuse, involve
Security before permanently revoking keys.
