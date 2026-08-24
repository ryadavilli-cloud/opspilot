---
id: postmortem:inc-109
title: "INC-109: Checkout failures during a payment-gateway latency episode"
kind: postmortem
incident_id: inc-109
services: [payment-gateway, payment-api, checkout-api]
severity: SEV1
source: "synthetic (RetailEase); structure after real SRE practice"
---

# INC-109: Checkout failures during a payment-gateway latency episode

## Summary
The third-party card processor slowed sharply during a card-network incident on its
side. `payment-api` authorization calls exceeded their timeout, and `checkout-api`
surfaced the failures to customers. Nothing inside RetailEase had changed.

## Impact
- Roughly 40 minutes of failed checkouts at the payment step.
- `payment-api` `p95_latency_ms` rose to the timeout ceiling and stayed there.
- `checkout-api` `http_5xx_rate` tracked the payment failures.
- Inventory, catalog, and the data tier were unaffected.

## Timeline (UTC)
- 10:05: `payment-gateway` response times begin rising.
- 10:12: `payment-api` authorization calls start timing out; checkout errors appear.
- 10:20: On-call paged on `checkout-api` 5xx rate.
- 10:26: Responder rules out recent deploys and the data tier, and finds the latency
  originates at the external gateway.
- 10:45: Provider confirms an incident on their side; traffic shed to a
  timeout-and-retry posture until they recover.

## Root cause
An external dependency degraded. `payment-api` correctly gave up on calls that
exceeded the authorization timeout, and `checkout-api` correctly reported that payment
could not be completed. The customer-visible symptom was several hops from its cause,
and every service between the two behaved as designed.

## Resolution
- Confirmed the fault was outside RetailEase before changing anything internally.
- Shed load at the payment step and failed fast rather than holding connections.
- Waited for provider recovery, then restored normal timeouts.

## Action items
- Publish gateway latency as a first-class dashboard signal so an external episode is
  visible without inference.
- Hold a documented degraded-checkout posture for provider incidents.

## Lessons learned
The symptom appeared at `checkout-api`, which is where symptoms appear regardless of
where the fault is. Walking the dependency chain outward, rather than investigating
the service that reported the error, is what located this one. A recent deploy in the
same window would have been a plausible and wrong explanation. See
`runbook:payment-timeout`.
