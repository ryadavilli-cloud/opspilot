---
id: runbook:checkout-coupon-validation-errors
title: Checkout Coupon Validation Errors
kind: runbook
services: [checkout-api, catalog-api, redis-cache]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# Checkout Coupon Validation Errors

## Summary
Handles spikes in HTTP 422 responses from `POST /v1/checkout/coupons/apply` where
coupon codes are rejected as invalid or expired. This is a validation-logic issue,
not a checkout 500 or payment failure.

## Symptoms
- Elevated 422 rate on the coupon-apply operation in Application Insights.
- Users report "This code is no longer valid" for codes that should work.
- checkout-api logs show `couponValidationFailed` with reason codes.

## Likely causes
1. Promotion rules cache in redis-cache is stale after a marketing config push.
2. Timezone/date-boundary bug: coupon expiry compared in UTC vs. store-local time.
3. Coupon usage-limit counter drifted from the source of truth in cosmos-db.
4. A new promotion type not yet supported by the validation ruleset.

## Diagnosis
1. Query reason-code distribution:
   ```kusto
   traces
   | where message has "couponValidationFailed"
   | summarize count() by tostring(customDimensions.reasonCode)
   ```
2. Compare the promo config version in redis-cache (`promo:config:version`) to the
   latest published version in the marketing config store.
3. Spot-check a failing code's expiry against `now()` in UTC.

## Mitigation
- Stale cache: invalidate `promo:config:*` keys; checkout-api reloads on next request.
- Timezone bug: hotfix comparison to normalize both sides to UTC; add a regression test.
- Counter drift: run the usage-limit reconciliation job to rebuild counters from
  the cosmos-db redemption ledger.

## Verification
- 422 rate returns to baseline (< 1% of coupon-apply calls).
- Sampled known-good codes apply successfully across store regions.

## Escalation
Coordinate with the Promotions/Marketing team before disabling any live promotion.
Do not manually edit redemption counters — always use the reconciliation job.
