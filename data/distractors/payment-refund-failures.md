---
id: runbook:payment-refund-failures
title: Payment Refund Failures
kind: runbook
services: [payment-api, payment-gateway, cosmos-db]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# Payment Refund Failures

## Summary
Handles failures on `POST /v1/payments/{id}/refund`. This is the *refund* path against
the external payment-gateway — deliberately adjacent to, but distinct from, payment
authorization timeouts or Cosmos connection-pool exhaustion.

## Symptoms
- Elevated failure rate on the refund operation in Application Insights.
- payment-api logs `refundRejected` or `refundGatewayError`.
- Finance reports customers not receiving refunds; support tickets rising.

## Likely causes
1. Refund attempted after the original capture was already voided/settled in a batch.
2. payment-gateway declines partial refunds exceeding the captured amount.
3. Idempotency key reuse causing the gateway to return a stale/duplicate result.
4. Currency mismatch between the original charge and the refund request.

## Diagnosis
1. Break down gateway response codes:
   ```kusto
   traces
   | where message has "refundGatewayError"
   | summarize count() by tostring(customDimensions.gatewayCode)
   ```
2. For a failing refund, fetch the payment record from cosmos-db and confirm original
   `capturedAmount`, `currency`, and settlement state.
3. Verify the idempotency key is unique per refund attempt (not reused from capture).

## Mitigation
- Over-refund/partial rejections: cap refund at `capturedAmount`; split into allowed amounts.
- Already-settled: route to the gateway's post-settlement refund flow (different endpoint).
- Idempotency reuse: generate a fresh key per refund; re-drive the request.
- Currency mismatch: refund in the original charge currency; never convert client-side.

## Verification
- Refund success rate back to baseline.
- Reconcile a sample of refunds against the payment-gateway settlement report.

## Escalation
Refund/settlement discrepancies go to Finance Ops and the payment-gateway support
channel. Never issue manual out-of-band refunds without a linked gateway transaction id.
