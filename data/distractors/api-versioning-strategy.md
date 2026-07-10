---
id: architecture:api-versioning-strategy
title: API Versioning Strategy
kind: architecture
services: [checkout-api, payment-api, inventory-api, catalog-api]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# API Versioning Strategy

## Purpose
Describes how RetailEase versions its public and internal HTTP APIs across the Container
Apps services, and how breaking changes are managed. Architecture reference, not a runbook.

## Versioning scheme
- **URI-based major versions**: `/v1/...`, `/v2/...`. Major = breaking change.
- Minor/additive changes (new optional fields, new endpoints) ship within the current
  major and never break existing clients.
- Each service advertises supported versions at `GET /versions`.

## Compatibility rules
- Additive-only within a major: new response fields are optional; clients must ignore
  unknown fields.
- Never repurpose or remove a field within a major version.
- Enums are extensible: clients must tolerate unknown enum values (default/fallback).
- Error shapes are stable within a major (`problem+json`).

## Deprecation lifecycle
1. **Announce**: new major published; old major marked deprecated in docs and via
   `Deprecation` + `Sunset` response headers.
2. **Overlap**: both majors run in parallel (min 6 months) as separate routes on the
   same Container App or side-by-side revisions.
3. **Sunset**: old major returns HTTP 410 after the sunset date; telemetry confirms
   near-zero traffic first.

## Implementation
- The API gateway routes by URI version to the correct backend revision/service.
- Internal service-to-service calls pin an explicit version; no implicit "latest".
- Contract tests run in CI against each supported major to catch accidental breaks.
- Version usage is tracked in Application Insights (`customDimensions.apiVersion`) to
  drive sunset decisions.

## Ownership
API Platform owns the strategy; each service team owns its own version lifecycle and
must not sunset a major while non-trivial client traffic remains.
