---
id: runbook:email-provider-bounce-handling
title: Email Provider Bounce and Suppression Handling
kind: runbook
services: [notification-worker, email-provider]
source: "synthetic (RetailEase); distractor — not a labeled retrieval target"
---

# Email Provider Bounce and Suppression Handling

## Summary
Covers rising hard/soft bounce rates and suppression-list growth from the external
email-provider. This is about *deliverability*, not the notification-worker crash-loop
or Service Bus backlog scenarios.

## Symptoms
- email-provider webhook reports bounce rate > 5% (baseline ~1%).
- notification-worker logs `emailBounced` and `recipientSuppressed` events.
- Customers report missing order-confirmation or shipping emails.

## Likely causes
1. A stale recipient list imported from a marketing campaign with invalid addresses.
2. Sender reputation dip triggering soft bounces / greylisting.
3. SPF/DKIM/DMARC alignment broke after a sending-domain change.
4. Suppression list accumulating valid addresses due to transient 4xx from the provider.

## Diagnosis
1. Pull the bounce breakdown from the email-provider dashboard: hard vs. soft, by domain.
2. In Log Analytics:
   ```kusto
   customEvents
   | where name in ("emailBounced","recipientSuppressed")
   | summarize count() by tostring(customDimensions.bounceType), bin(timestamp,15m)
   ```
3. Verify DNS: SPF include, DKIM selector record, DMARC policy for the sending domain.
4. Check whether transactional and marketing mail share an IP pool (they should not).

## Mitigation
- Hard bounces: honor suppression; scrub the offending list; never resend to hard bounces.
- Soft bounces: rely on provider retry; if greylisted, back off and warm the IP.
- Auth failures: restore SPF/DKIM/DMARC records; re-authenticate the sending domain.
- Wrongly-suppressed valid addresses: request targeted suppression-list removal via the
  provider API after confirming the address is legitimate.

## Verification
- Bounce rate back under 2% for 24h.
- Test transactional sends to seed inboxes deliver and pass DMARC.

## Escalation
Engage the email-provider account team for reputation/IP-pool issues. Loop in Security
before changing DNS auth records.
