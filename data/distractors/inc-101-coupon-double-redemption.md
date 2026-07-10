---
id: postmortem:inc-101-coupon-double-redemption
title: "INC-101: Coupon Double-Redemption via Concurrent Checkout"
kind: postmortem
services: [checkout-api, redis-cache, cosmos-db]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# INC-101: Coupon Double-Redemption via Concurrent Checkout

## Summary
A race condition in checkout-api allowed single-use coupons to be redeemed more than
once when a shopper submitted checkout concurrently (double-click / retry), causing
revenue leakage on high-value promo codes.

## Impact
- ~3,400 single-use coupons redeemed 2+ times over ~9 hours.
- Estimated ~$41k unintended discount before mitigation.
- No customer-facing errors; issue was silent until Finance flagged an anomaly.

## Timeline (UTC)
- 08:12 — Flash-sale promo goes live; traffic surges.
- 11:40 — Finance notices redemption counts exceeding issued single-use codes.
- 12:05 — Incident opened; checkout-api coupon path suspected.
- 12:30 — Reproduced: two parallel `coupons/apply` calls both pass the usage check.
- 12:55 — Mitigation: added a distributed lock on `coupon:{code}` in redis-cache.
- 13:20 — Redemption anomaly stops; incident monitored.

## Root cause
The usage-limit check was read-then-write without atomicity: both concurrent requests
read `used < limit` from cosmos-db before either incremented the counter, so both
proceeded. redis-cache was used only for read caching, not for mutual exclusion.

## Contributing factors
- No idempotency key on the checkout submit path, so retries were treated as new attempts.
- Load testing never exercised concurrent redemption of the *same* code.

## Resolution
- Introduced a short-lived distributed lock (`SET NX PX`) keyed by coupon code in
  redis-cache around the check-and-decrement.
- Made the redemption a conditional write in cosmos-db (optimistic concurrency via ETag)
  so the counter can never exceed the limit even if the lock is bypassed.
- Added an idempotency key to checkout submit.

## Action items
- [ ] Backfill/claw-back reconciliation of over-redeemed coupons (Finance + Promotions).
- [ ] Add concurrency test for same-code redemption to CI.
- [ ] Audit other check-then-write paths (loyalty points, gift cards) for the same class.

## Lessons learned
Uniqueness/limit invariants must be enforced at the data tier with conditional writes,
not by application-level read-then-write checks under concurrency.
