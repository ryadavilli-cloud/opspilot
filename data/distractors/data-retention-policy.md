---
id: architecture:data-retention-policy
title: Data Retention and Purge Policy
kind: architecture
services: [payment-api, catalog-api, inventory-api, notification-worker]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# Data Retention and Purge Policy

## Purpose
Defines how long RetailEase retains operational and customer data across Azure stores,
and how it is purged. This is a governance/architecture reference, not an incident runbook.

## Data classes and retention
| Data class | Store | Retention | Purge mechanism |
|---|---|---|---|
| Order records | cosmos-db (orders) | 7 years (financial/tax) | Legal hold aware; no auto-purge |
| Payment transactions | cosmos-db (payments) | 7 years | Tokenized; no raw PAN stored |
| Cart / session | redis-cache | 30 min idle TTL | Redis key expiry |
| Catalog snapshots | cosmos-db (catalog) | 90 days of versions | Change-feed compaction job |
| Notification events | service-bus + cosmos-db | 30 days | TTL on container + queue auto-delete |
| App logs / traces | Log Analytics | 90 days hot, 1 year archive | Workspace retention + archive tier |
| Metrics | Azure Monitor | 93 days | Platform default |

## Principles
- **Minimize**: store only what a service needs; PII lives in the fewest containers possible.
- **Tokenize**: payment-api stores gateway tokens, never raw card data.
- **TTL by default**: transient data (carts, ephemeral events) uses native store TTL.
- **Right to erasure**: a GDPR/CCPA delete request triggers the `customer-erasure` job,
  which redacts PII across cosmos-db containers and suppresses the address at the email-provider.

## Implementation notes
- Cosmos containers set `defaultTtl` where auto-expiry applies; long-retention containers
  set `defaultTtl = -1` (never expire) and rely on explicit purge jobs.
- Log Analytics retention configured per-table; sensitive tables shortened.
- Backups (continuous PITR on cosmos-db) inherit the account's retention window and are
  excluded from erasure SLAs (documented exception, legal-approved).

## Ownership and review
Data Governance owns this policy; reviewed quarterly. Any new container or store must
register its data class and retention here before go-live.
