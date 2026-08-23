---
id: postmortem:inc-104
title: "INC-104: checkout-api returning 500s shortly after a morning deployment"
kind: postmortem
incident_id: inc-104
services: [checkout-api]
severity: SEV1
source: "synthetic (RetailEase); structure after real SRE practice"
---

# INC-104: checkout-api returning 500s shortly after a morning deployment

## Summary
`checkout-api` began returning HTTP 500s within minutes of a morning deployment. The
release had shipped a change to the order-total serializer that threw on any cart
carrying a gift-card line, and roughly one checkout in nine hit that path. Rolling the
revision back cleared the errors immediately.

## Impact
- ~22 minutes of elevated `http_5xx_rate` on `checkout-api`, peaking around 9%.
- Customers with a gift card applied could not complete a purchase.
- `payment-api`, `inventory-api`, and the data tier were healthy throughout; the fault
  was entirely inside the newly deployed `checkout-api` revision.

## Timeline (UTC)
- 09:00: `checkout-api` deployment takes 100% traffic.
- 09:06: `http_5xx_rate` climbs past the alert threshold; on-call paged.
- 09:11: Responder correlates the onset with the 09:00 deployment.
- 09:14: Errors reproduce against the new revision with a gift-card cart; the stack
  trace points at the order-total serializer.
- 09:22: Revision rolled back. `http_5xx_rate` returns to baseline within one sample.

## Root cause
The deployed revision serialized order totals through a code path that assumed every
line item carried a positive unit price. A gift-card line carries a negative
adjustment, and the serializer threw an unhandled exception, which surfaced to the
customer as a 500 from `checkout-api`. The defect was in the released code itself, so
the deployment was both the trigger and the cause.

## Resolution
- Rolled `checkout-api` back to the previous known-good revision.
- Confirmed `http_5xx_rate` returned to baseline before closing.
- Shipped the serializer fix behind a test covering negative-adjustment lines.

## Action items
- Add a gift-card cart to the pre-deploy smoke suite.
- Shift `checkout-api` to gradual traffic-shift deploys so a bad revision is caught
  before it takes all traffic.

## Lessons learned
Onset within minutes of a deployment is a strong signal, and here it was the right
one. It is worth saying plainly that this is not always so: the same shape appears
when a downstream dependency degrades during a deployment window, and the deployment
is then a coincidence. Confirm the fault reproduces against the new revision before
attributing it to the release. See `runbook:deployment-rollback` and
`runbook:checkout-api-500-errors`.
