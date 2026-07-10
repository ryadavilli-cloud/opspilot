---
id: postmortem:inc-102-email-provider-outage
title: "INC-102: Transactional Email Delay During Provider Outage"
kind: postmortem
services: [notification-worker, email-provider, service-bus]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# INC-102: Transactional Email Delay During Provider Outage

## Summary
A partial outage at the external email-provider caused transactional emails (order
confirmations, shipping notices) to be delayed by up to 3 hours. No emails were lost;
delivery caught up once the provider recovered.

## Impact
- ~92,000 transactional emails delayed (not dropped) over a ~2.5 hour window.
- Increased support contacts ("did my order go through?").
- No data loss; notification-worker and Service Bus remained healthy throughout.

## Timeline (UTC)
- 15:03 — email-provider begins returning HTTP 503 on its send API (regional incident).
- 15:08 — notification-worker send failures rise; messages are retried, not dropped.
- 15:20 — Alert fires on `emailSendFailureRate`. Incident opened.
- 15:35 — Confirmed upstream provider outage via their status page.
- 15:40 — Decision: keep messages on Service Bus (do not dead-letter), let retries ride
  out the outage; disable aggressive redelivery to avoid hammering the provider.
- 17:25 — Provider recovers; queued sends drain over ~40 min.
- 18:05 — Backlog cleared; incident resolved.

## Root cause
External dependency (email-provider) regional outage. RetailEase had no secondary
sending path, so all transactional mail queued behind the single provider.

## Contributing factors
- Retry/backoff was too aggressive initially, risking self-inflicted rate limiting once
  the provider partially recovered.
- No fallback provider or degraded-mode messaging for customers.

## Resolution
- Tuned notification-worker backoff to exponential + jitter and capped in-flight sends
  during provider degradation.
- Messages were held on Service Bus (visibility-timeout based retry) rather than
  dead-lettered, guaranteeing eventual delivery.

## Action items
- [ ] Evaluate a secondary email-provider with automated failover for transactional mail.
- [ ] Add a customer-facing status banner for known notification delays.
- [ ] Add a provider-health circuit breaker to pause/resume sends automatically.

## Lessons learned
For critical external dependencies, prefer queue-and-retry over drop, and design a
degraded mode (fallback provider or user messaging) before the next outage.
