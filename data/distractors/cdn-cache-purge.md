---
id: runbook:cdn-cache-purge
title: CDN Cache Purge for Stale Catalog Assets
kind: runbook
services: [catalog-api]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# CDN Cache Purge for Stale Catalog Assets

## Summary
Procedure for purging stale content from Azure Front Door / CDN when product images,
prices in cached responses, or static assets do not reflect a recent catalog update.
This is a content-freshness runbook, unrelated to backend cache eviction or oversell.

## Symptoms
- Shoppers see outdated product images, old badges, or a stale price on a PDP.
- A catalog-api update published, but CDN edges still serve the previous version.
- `Age`/`X-Cache: HIT` headers show long-lived cached objects at the edge.

## Likely causes
1. Cache-Control `max-age` on catalog assets is longer than the update cadence.
2. A publish did not change the asset URL/version hash, so the edge kept the old copy.
3. Purge after the last publish was scoped too narrowly (missed a path/host).

## Diagnosis
1. Confirm origin freshness: request the asset directly from catalog-api origin and
   compare to the edge response.
2. Inspect response headers for `Age`, `Cache-Control`, and `X-Cache`.
3. Identify the exact paths/hosts serving stale content.

## Mitigation
- Targeted purge (preferred):
  ```bash
  az afd endpoint purge \
    --resource-group retailease-rg \
    --profile-name retailease-fd \
    --endpoint-name catalog-assets \
    --content-paths "/images/sku/12345/*" "/pdp/12345"
  ```
- For systemic staleness, adopt versioned/hashed asset URLs so publishes are
  self-busting and purges become unnecessary.
- Tune `Cache-Control` to match the real update cadence.

## Verification
- `X-Cache: MISS` then fresh content on first request post-purge; subsequent HITs correct.
- Spot-check the affected PDPs across regions.

## Escalation
Avoid broad wildcard purges (`/*`) in peak hours — they cause origin load spikes.
For a full-site purge, coordinate with the Platform team and pre-warm critical paths.
