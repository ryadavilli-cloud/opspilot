---
id: postmortem:inc-108
title: "INC-108: Notification delays from an under-scaled worker at peak"
kind: postmortem
incident_id: inc-108
services: [notification-worker, service-bus]
severity: SEV3
source: "synthetic (RetailEase); structure after real SRE practice"
---

# INC-108: Notification delays from an under-scaled worker at peak

## Summary
Evening peak traffic produced more order events than the single `notification-worker`
replica could consume. Queue depth on Service Bus rose steadily for about forty
minutes and order confirmations arrived late. The worker was healthy throughout: it
never crashed, never restarted, and processed continuously.

## Impact
- `active_message_count` climbed to roughly 1,400 before recovering.
- Order confirmation emails delayed by up to eleven minutes.
- `restart_count` stayed at zero and `msg_processed_rate` stayed at its normal
  per-replica ceiling for the whole window.

## Timeline (UTC)
- 18:30: Evening peak begins; order rate rises above the day's average.
- 18:45: Incoming rate passes single-replica consumption; queue depth begins climbing.
- 19:00: Backlog alert fires on `active_message_count`.
- 19:12: Responder confirms the worker is healthy and simply outpaced.
- 19:25: Replica count raised; the queue drains and confirmations catch up.

## Root cause
Consumer capacity was fixed at one replica while producer volume follows a daily
curve. At peak the arrival rate exceeded the drain rate and the queue accumulated the
difference. No message was bad and no consumer failed.

## Resolution
- Raised the replica count for `notification-worker`.
- Let the backlog drain; all delayed notifications were delivered.

## Action items
- Autoscale the worker on queue depth rather than holding a fixed replica count.

## Lessons learned
A rising queue means consumption is not keeping up with arrival, and that has two very
different explanations: the consumer is too small, or the consumer is not consuming.
`restart_count` and `msg_processed_rate` separate them immediately. A healthy worker
processing at its ceiling is a capacity problem; a worker restarting with processing
at zero is a failure, and the two call for opposite responses. See
`runbook:service-bus-backlog`.
