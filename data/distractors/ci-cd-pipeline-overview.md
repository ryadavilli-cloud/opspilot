---
id: architecture:ci-cd-pipeline-overview
title: CI/CD Pipeline Overview
kind: architecture
services: [checkout-api, payment-api, inventory-api, catalog-api, notification-worker]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# CI/CD Pipeline Overview

## Purpose
Describes how RetailEase builds, tests, and deploys its services to Azure Container Apps.
Architecture reference. Note: routine deployment *rollback* procedure is covered elsewhere.

## Source and branching
- GitHub monorepo; trunk-based development on `main`.
- Feature work on short-lived branches; merge via PR with required checks.
- Each service has an independently versioned build tagged by commit SHA.

## CI (on PR)
1. Lint + unit tests per service.
2. Contract tests against supported API majors.
3. Container image build; push to Azure Container Registry (ACR) tagged with the SHA.
4. Trivy image scan; fail on high/critical CVEs.

## CD (on merge to main)
1. GitHub Actions authenticates to Azure via OIDC (federated credentials, no secrets).
2. Deploy to **staging** Container Apps environment as a new revision.
3. Smoke tests + synthetic checks against staging.
4. Manual approval gate for production.
5. Deploy to **production** as a new revision using **traffic-splitting** for progressive
   rollout: 10% -> 50% -> 100%, watching Application Insights failure rate at each step.

## Progressive delivery
- Container Apps revision traffic weights implement canary rollout.
- Automated guardrail: if the canary revision's 5xx rate or latency breaches thresholds,
  the pipeline halts and holds traffic on the previous revision.
- Config and secrets flow from Key Vault via Container Apps secret references; never baked
  into images.

## Environments
| Env | Purpose | Data |
|---|---|---|
| dev | per-PR ephemeral / shared dev | synthetic |
| staging | pre-prod validation | anonymized |
| prod | live | production |

## Ownership
Platform Engineering owns the pipeline templates; service teams own their app manifests
and smoke tests. All production deploys are auditable via GitHub Actions run history.
