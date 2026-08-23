---
id: postmortem:inc-107
title: "INC-107: Reservation backlog during a flash sale"
kind: postmortem
incident_id: inc-107
services: [inventory-reservation-worker, inventory-api]
severity: SEV3
source: "synthetic (RetailEase); structure after real SRE practice"
---

# INC-107: Reservation backlog during a flash sale

## Summary
A flash sale drove reservation volume well past what `inventory-reservation-worker`
could apply, and `reservation_queue_depth` grew for most of an hour. Reservations were
accepted and eventually applied, so nothing was lost, but they landed minutes after
they were made. Scaling the worker out drained the queue.

## Impact
- `reservation_queue_depth` peaked around 300 against a normal depth of two.
- Reservations applied several minutes after acceptance for the duration.
- No oversells: stock reads were accurate throughout, so availability reflected
  reality even while the queue was deep.
- No alert fired. Queue depth on the worker is not a paged signal.

## Timeline (UTC)
- 14:00: Flash sale opens; `inventory-api` request rate roughly triples.
- 14:10: Reservation arrival rate passes the worker's drain rate; depth begins climbing.
- 14:45: A support query about slow order confirmation prompts a look at the worker.
- 14:50: Responder reads `reservation_queue_depth` and finds the backlog.
- 15:05: Worker scaled out; depth drains to baseline over the following ten minutes.

## Root cause
The worker was provisioned for ordinary traffic and applies reservations at a fixed
rate per replica. A sale multiplies arrivals without changing drain capacity, so the
queue grows for as long as the imbalance lasts. Nothing was broken; the capacity was
simply wrong for the day.

## Resolution
- Scaled `inventory-reservation-worker` out for the remainder of the sale.
- Let the accumulated queue drain rather than discarding it.

## Action items
- Scale the worker ahead of planned sale events rather than in response to them.
- Publish `reservation_queue_depth` on the inventory dashboard so a backlog is visible
  without knowing to ask for it.

## Lessons learned
A deep reservation queue on its own slows reservations; it does not corrupt them.
Availability stayed correct here because stock reads were fresh, and every queued
reservation applied in the end. Whether a backlog can do worse than delay depends on
what else is true at the time, which is worth establishing separately rather than
assuming from the depth alone.
