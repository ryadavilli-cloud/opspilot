---
id: runbook:service-bus-backlog
title: Service Bus Order-Event Backlog Not Draining
kind: runbook
services: [service-bus, notification-worker]
source: "synthetic (RetailEase); structure after real SRE practice"
---

## Symptoms
- Azure Service Bus `active_message_count` on the order-event queue climbing and **not
  draining**.
- Order notifications (confirmation emails) delayed.
- `notification-worker` `restart_count` rising (crash loop).

## Likely causes
The consumer is not keeping up or not consuming at all:
1. **Consumer down / crash-looping** — `notification-worker` is failing to start or repeatedly
   crashing, so nothing drains the queue.
2. **Poison message** — a malformed/undeserializable order event that kills the worker on
   receipt; it redelivers, crashes the worker again, and stalls the whole queue.
3. **Throughput mismatch** — a legitimate publish spike exceeding a single consumer's
   processing rate.

## Diagnosis
1. **Service Bus metrics (Azure Monitor)** — trend `active_message_count`; check the
   **dead-letter queue (DLQ)** count. A rising DLQ or a message with a high delivery-count
   points to a poison message.
2. **notification-worker health** — Container Apps replica status, `restart_count`, and
   **Log Analytics** logs. Look for a repeating exception (e.g. deserialization error) at a
   consistent point → poison message. Confirm whether the crash started after a recent
   `notification-worker` revision.
3. **Peek the queue/DLQ** (Service Bus Explorer) to inspect the offending message payload.

## Remediation
- **Poison message:** move it to the **DLQ** (dead-letter) so the worker can advance past it;
  capture the payload for offline analysis.
- **Bad worker revision:** if a recent deploy introduced the crash, follow
  `runbook:deployment-rollback` to shift traffic to the last-known-good `notification-worker`
  revision.
- **Throughput:** scale out consumers — increase `notification-worker` replica count / KEDA
  Service Bus scale rule — to drain the backlog, then reprocess.
- **Reprocess** any recoverable dead-lettered messages once the fix is in.

## Escalation
Usually **lower severity** — notifications are asynchronous and off the synchronous checkout
path, so orders still complete. Handle within normal on-call. Escalate only if the backlog
keeps growing unbounded (approaching queue quota / risking message loss) or if delayed
confirmations breach a customer-comms SLA.
