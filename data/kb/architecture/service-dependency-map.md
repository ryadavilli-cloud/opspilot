---
id: architecture:service-dependency-map
title: RetailEase Service Dependency Map
kind: architecture
services: [checkout-api, payment-api, inventory-api, catalog-api, notification-worker, inventory-reservation-worker, service-bus, cosmos-db, redis-cache, payment-gateway, email-provider]
source: "synthetic (RetailEase); structure after real SRE practice"
---

# RetailEase Service Dependency Map

This document is the authoritative directed dependency graph for RetailEase. Use it to trace a customer-facing symptom back to its root cause by walking dependencies downstream.

## Directed dependency list

Each edge points from a caller to the dependency it relies on. Edges marked **[critical]** are on the synchronous checkout path — a failure there directly blocks a customer from completing a purchase.

- `checkout-api` → `payment-api` **[critical]**
- `checkout-api` → `inventory-api` **[critical]**
- `checkout-api` → `redis-cache`
- `checkout-api` → `service-bus`
- `payment-api` → `cosmos-db` **[critical]**
- `payment-api` → `payment-gateway`
- `inventory-api` → `cosmos-db` **[critical]**
- `inventory-api` → `redis-cache`
- `inventory-api` → `inventory-reservation-worker`
- `inventory-reservation-worker` → `cosmos-db` **[critical]**
- `catalog-api` → `cosmos-db`
- `catalog-api` → `redis-cache`
- `notification-worker` → `service-bus`
- `notification-worker` → `email-provider`

## Text diagram

```
                         customer
                            |
                            v
                     +--------------+
                     |  checkout-api|
                     +--------------+
             (crit) /   |      |    \
                   /    |      |     \  (async, off critical path)
                  v     |      v      v
          +-----------+ |  +---------+  +-------------+
          |payment-api| |  |redis-   |  | service-bus |
          +-----------+ |  |cache    |  +-------------+
        (crit)/    \    |  +---------+         |
             /      \   |(crit)                v
            v        v  |             +--------------------+
   +----------+  +--------------+     | notification-worker|
   |payment-  |  |  cosmos-db   |     +--------------------+
   |gateway   |  +--------------+               |
   +----------+       ^  ^                       v
    (external)  (crit)|  |(crit)          +---------------+
                      |  |                | email-provider|
              +-----------+  +---------+  +---------------+
              |inventory- |  |catalog- |     (external)
              |api        |  |api      |
              +-----------+  +---------+
                 |  |    \       |   \
             (crit) |     \      |    \
                 v  |      v     v     v
          cosmos-db |     redis  cosmos redis
                    | (async reservation hand-off)
                    v
       +------------------------------+
       | inventory-reservation-worker |
       +------------------------------+
                    | (crit)
                    v
                cosmos-db
```

Simplified critical checkout path (synchronous, customer-blocking):

```
customer -> checkout-api -> payment-api  -> cosmos-db
                         \             \-> payment-gateway (external)
                          -> inventory-api -> cosmos-db
```

`inventory-api` answers an availability check synchronously and hands the reservation itself to
`inventory-reservation-worker`, which applies it against `cosmos-db` out of band. A customer is
not blocked waiting for that, so the edge is off the critical path; what the customer sees when
the worker falls behind is availability that was true when it was read and no longer true when
the order lands.

## Failure propagation

Failures in RetailEase propagate **upstream** — from a dependency toward the caller that needs it — and surface to the customer at `checkout-api`, the edge orchestrator.

- A failure at **`cosmos-db`** (e.g. rising `ru_throttled_rate` / `used_ru_pct` at 100%) degrades **`payment-api`** and **`inventory-api`**, both of which depend on it on the critical path. Their `http_5xx_rate` and `p95_latency_ms` climb, and because `checkout-api` calls both synchronously, the failure surfaces as failed or slow checkouts. Root cause is `cosmos-db`; `checkout-api` is only where the symptom is observed.
- A failure at **`payment-gateway`** (external card processor) degrades **`payment-api`**, which then fails the payment step of checkout. `checkout-api` reports payment failures even though nothing inside RetailEase is broken.
- A backlog at **`inventory-reservation-worker`** fails nothing on its own. Reservations queue rather than applying, so `reservation_queue_depth` climbs while `inventory-api` goes on answering availability checks normally from what it can see. Nothing pages: the symptom appears at `checkout-api` as reservation conflicts, and the worker is reached by asking `inventory-api` what it depends on rather than by following an alert.
- A failure at **`redis-cache`** degrades session/cart reads and hot-read caching for `checkout-api`, `inventory-api`, and `catalog-api`. Impact is typically latency and cache-miss load rather than hard checkout failure, though severe eviction (`evicted_keys_rate`, `used_memory_pct`) can push read load onto `cosmos-db` and amplify an existing bottleneck.

Because propagation flows upstream to `checkout-api`, an investigator who sees a customer-facing symptom there should walk the dependency edges **downstream** to find where the failure actually originates.

## Off the critical checkout path

`service-bus` and `notification-worker` sit **off** the synchronous checkout path. `checkout-api` publishes an order-placed event to `service-bus` and returns to the customer immediately; `notification-worker` consumes the event asynchronously and sends via `email-provider`.

Consequently, a failure in `service-bus`, `notification-worker`, or `email-provider` **delays or drops notifications** (order confirmation emails/SMS) but does **not** take down checkout. Symptoms include a rising `active_message_count` (backlog) on `service-bus` and increasing `restart_count` on `notification-worker`. These incidents are inherently **lower severity** than anything on the critical path because customers can still complete purchases. Use this distinction to triage: a checkout-blocking symptom outranks a notification-delay symptom.
