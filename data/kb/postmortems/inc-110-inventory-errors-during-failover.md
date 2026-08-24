---
id: postmortem:inc-110
title: "INC-110: inventory-api errors during a cosmos-db failover"
kind: postmortem
incident_id: inc-110
services: [inventory-api, cosmos-db]
severity: SEV2
source: "synthetic (RetailEase); structure after real SRE practice"
---

# INC-110: inventory-api errors during a cosmos-db failover

## Summary
A planned regional failover of `cosmos-db` took longer than its stated window.
`inventory-api` held connections against the old primary and returned errors on stock
reads until its connection pool recycled.

## Impact
- Roughly nine minutes of failed stock reads.
- `inventory-api` `http_5xx_rate` elevated for the duration; recovery was automatic.
- Checkout blocked for the affected requests, since inventory sits on the critical
  path.

## Timeline (UTC)
- 03:00: Planned failover begins during the maintenance window.
- 03:02: `inventory-api` stock reads begin failing.
- 03:11: Connection pool recycles onto the new primary; errors stop.
- 03:20: Failover completes and is confirmed healthy.

## Root cause
The client connection pool did not observe the failover promptly and continued to
direct reads at an endpoint that was no longer primary. The failover itself worked as
designed; the client's recovery behaviour was slower than the platform's.

## Resolution
- Waited for the pool to recycle; no manual intervention was needed.
- Shortened the connection idle lifetime so a future failover is observed sooner.

## Action items
- Rehearse failover against a staging environment and measure client recovery, not
  only platform recovery.

## Lessons learned
Maintenance windows make correlation cheap and misleading in both directions. A
failure inside a planned window is often the planned work, and occasionally is not.
See `runbook:cosmos-db-throttling` for the throttling shape this is often mistaken
for; the two are different, and `ru_throttled_rate` tells them apart.
