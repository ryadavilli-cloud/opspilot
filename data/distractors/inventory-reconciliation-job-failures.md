---
id: runbook:inventory-reconciliation-job-failures
title: Inventory Reconciliation Job Failures
kind: runbook
services: [inventory-api, cosmos-db, service-bus]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# Inventory Reconciliation Job Failures

## Summary
Handles failures of the nightly inventory reconciliation job that compares on-hand
counts in cosmos-db against warehouse/ERP feeds. This is a batch-job reliability topic —
NOT the real-time oversell-from-stale-cache scenario.

## Symptoms
- The `inventory-reconciliation` scheduled job (Container Apps Job) exits non-zero.
- Alert: reconciliation did not complete within its 2-hour SLA window.
- Downstream: stock levels not corrected; discrepancy report missing.

## Likely causes
1. ERP/warehouse feed file late, missing, or malformed for the run.
2. Job hit a cosmos-db RU ceiling during bulk upserts and aborted after retries.
3. A schema change in the feed broke the parser.
4. Job pod OOM-killed processing an unusually large delta.

## Diagnosis
1. Inspect the job execution logs:
   ```kusto
   ContainerAppConsoleLogs_CL
   | where ContainerAppName_s == "inventory-reconciliation"
   | where Log_s has_any ("ERROR","Traceback","exit code")
   | order by TimeGenerated desc
   ```
2. Confirm the feed landed in the expected blob container with the right schema version.
3. Check cosmos-db throttling metrics during the job window (RU saturation).
4. Review the job's memory limit vs. peak usage.

## Mitigation
- Late/missing feed: hold the job and re-trigger once the feed lands; do not run partial.
- RU saturation: raise the container's throughput for the batch window or add
  bulk-execution backoff; re-run.
- Schema break: update the parser to the new feed version; add a schema-validation gate.
- OOM: raise the job memory limit or chunk the delta into smaller batches.

## Verification
- Job completes with exit 0 within SLA.
- Discrepancy report generated; corrected counts reflected in inventory-api.

## Escalation
Persistent feed problems go to the ERP/Warehouse integration team. Never manually edit
on-hand counts — always let the reconciliation job apply corrections.
