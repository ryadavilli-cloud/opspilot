---
id: runbook:service-bus-dead-letter-replay
title: Service Bus Dead-Letter Queue Replay
kind: runbook
services: [service-bus, notification-worker, inventory-api]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# Service Bus Dead-Letter Queue Replay

## Summary
Procedure for inspecting and replaying messages from an Azure Service Bus dead-letter
queue (DLQ) after transient downstream failures. This is a DLQ *recovery* procedure —
NOT the active-queue backlog / crash-looping consumer scenario.

## When to use
Messages have landed in the DLQ because they exceeded max delivery count or were
explicitly dead-lettered, and the root cause (a downstream fault) is now resolved.

## Symptoms
- Azure Monitor `DeadletteredMessages` count is non-zero and stable (not growing).
- No active backlog on the main queue; consumers are healthy.
- Business impact: some notifications or inventory events never processed.

## Diagnosis
1. Inspect DLQ messages (peek, do not consume) in the Service Bus explorer.
2. Read `DeadLetterReason` and `DeadLetterErrorDescription` on sampled messages.
3. Group by reason to confirm a single, now-fixed root cause vs. mixed causes.
   ```kusto
   AzureMetrics
   | where MetricName == "DeadletteredMessages"
   | summarize max(Maximum) by Resource, bin(TimeGenerated,15m)
   ```

## Replay procedure
1. Confirm the downstream fault is resolved and consumers are healthy.
2. Verify handlers are idempotent (replays may cause duplicates).
3. Use the `dlq-replay` tool to move messages from `<queue>/$deadletterqueue` back to
   the main queue in controlled batches (e.g., 200 at a time).
4. Throttle replay to avoid overwhelming the consumer; watch active-queue depth.
5. For poison messages (malformed, will never succeed): export to blob for audit,
   then purge from the DLQ.

## Verification
- `DeadletteredMessages` returns to zero (or only true poison remains).
- Downstream side effects (emails sent, inventory updated) confirmed for a sample.

## Escalation
If replayed messages re-dead-letter, stop the replay — the root cause is not fixed.
Engage the owning consumer team.
