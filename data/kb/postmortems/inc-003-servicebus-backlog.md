---
id: postmortem:inc-003
title: Notification backlog from a crash-looping worker stuck on a poison message
kind: postmortem
incident_id: inc-003
services: [notification-worker, service-bus]
severity: SEV3
source: "synthetic (RetailEase); structure after real SRE practice"
# Machine-checkable recurrence signature — the known-issue fast path verifies a candidate match
# against these before trusting this postmortem's resolution. Mirrors the answer key.
required_signals:
  - metrics:service-bus:active_message_count
  - metrics:notification-worker:restart_count
  - logs:notification-worker:error
disqualifying_signals:
  - metrics:checkout-api:http_5xx_rate
affected_versions:
  - notification-worker@3.1.0
---

# Notification backlog from a crash-looping worker stuck on a poison message

## Summary
A bad `notification-worker` deploy crash-looped on a single malformed ("poison")
message and stopped consuming from Azure Service Bus. With no consumer draining the
queue, `active_message_count` grew unbounded and order notifications (confirmation
emails and status updates) were delayed. Checkout and payments were unaffected because
notifications are off the critical purchase path, so this was scoped SEV3. Rolling
back the worker and dead-lettering the poison message cleared the backlog.

## Impact
- ~2 hours 10 minutes of delayed order notifications (emails via `email-provider`).
- `active_message_count` on the Service Bus queue grew steadily throughout the window.
- `notification-worker` `restart_count` climbed as the new revision crash-looped.
- No impact to checkout, payments, inventory, or catalog — purchases still completed;
  only the async notification side was delayed. Backlog was fully reprocessed, so no
  notifications were permanently lost.

## Timeline
All times UTC. Active revision at incident start: `notification-worker--rev-12`
(newly deployed).

- 13:20 — `notification-worker--rev-12` deployed via Azure Container Apps and takes 100% traffic.
- 13:26 — Worker receives a malformed message; the new revision throws and crashes instead of handling it.
- 13:26–14:00 — Container Apps restarts the crashed replica repeatedly; each restart re-reads the same poison message and crashes again (`restart_count` rising). No messages are consumed.
- 14:05 — `active_message_count` crosses the backlog alert threshold; Azure Monitor alert fires; on-call paged (SEV3).
- 14:18 — Responder correlates the crash loop and rising `restart_count` to `notification-worker--rev-12` in Application Insights.
- 14:22 — Worker rolled back to the previous good revision `notification-worker--rev-11` via Container Apps.
- 14:29 — Poison message identified and moved to the dead-letter queue so it stops blocking the consumer.
- 15:30 — Backlog drained/reprocessed; `active_message_count` back to baseline. Incident resolved.

## Root cause
The new `notification-worker` revision lacked safe handling for a malformed message.
On encountering it the process threw an unhandled exception and exited; Azure Container
Apps restarted the replica, which immediately picked up the same un-acknowledged
("poison") message and crashed again — a tight crash loop. While looping, the worker
consumed nothing, so Service Bus `active_message_count` grew unbounded and downstream
notifications were delayed. The blast radius stayed small only because notifications
are asynchronous and off the checkout critical path.

## Resolution
- Rolled the `notification-worker` back to the last known-good revision.
- Moved the poison message to the dead-letter queue so a healthy consumer could proceed.
- Let the recovered worker reprocess the accumulated backlog until the queue drained.

## Action items
- Add poison-message handling with a max-delivery-count / dead-letter policy so a
  single bad message auto-dead-letters instead of crash-looping the worker.
- Use canary (gradual traffic-shift) deploys for `notification-worker` so a bad
  revision is caught before it takes 100% of the queue.
- Add a backlog alert on Service Bus `active_message_count` (and on worker
  `restart_count`) to catch stalled consumption earlier.

## Recurrence signature
- Service Bus `active_message_count` climbing steadily with no drain.
- `notification-worker` `restart_count` rising (crash loop), notifications delayed.
- Checkout/payments healthy — impact confined to async notifications.
- Frequently follows a recent `notification-worker` revision.

If these symptoms match, follow `runbook:service-bus-backlog` and, for reverting the
bad revision, `runbook:deployment-rollback`.
