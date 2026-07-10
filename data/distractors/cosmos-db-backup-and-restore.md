---
id: runbook:cosmos-db-backup-and-restore
title: Cosmos DB Backup and Point-in-Time Restore
kind: runbook
services: [cosmos-db, payment-api, catalog-api]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# Cosmos DB Backup and Point-in-Time Restore

## Summary
Procedure for restoring an Azure Cosmos DB container from continuous backup after
data corruption or accidental deletion. This is a data-recovery runbook — deliberately
adjacent to, but NOT, the RU/429 throttling or connection-pool scenarios.

## When to use
- Accidental bulk delete/overwrite (e.g., a bad migration script).
- Logical corruption discovered in a container (payments, catalog, orders).
- A ransomware/tampering event requiring rollback to a known-good timestamp.

## Preconditions
- The account uses continuous (point-in-time) backup mode, retaining 7/30 days.
- You have the exact UTC restore timestamp (just before the bad change).

## Procedure
1. Identify the restore point: correlate the bad change to a timestamp from change
   feed / audit logs.
2. Initiate a restore to a **new** account (Cosmos restores side-by-side, never in place):
   ```bash
   az cosmosdb restore \
     --account-name retailease-cosmos \
     --restore-timestamp "2026-06-27T14:05:00Z" \
     --location eastus \
     --target-database-account-name retailease-cosmos-restore
   ```
3. Validate the restored container (row counts, spot-check known records).
4. Cut over: either repoint the service connection string or copy the corrected
   partition back into production via a controlled data-movement job.
5. Decommission the temporary restore account once validated.

## Verification
- Restored counts match expectations for the pre-incident state.
- Application reads/writes succeed against the corrected data.
- No unintended data older than the restore timestamp is reintroduced.

## Escalation
Restores are high-risk: require an incident commander and Data Platform sign-off.
Freeze writes to the affected container during cutover to prevent split-brain.
