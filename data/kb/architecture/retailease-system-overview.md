---
id: architecture:retailease-system-overview
title: RetailEase System Overview
kind: architecture
services: [checkout-api, payment-api, inventory-api, catalog-api, notification-worker, service-bus, cosmos-db, redis-cache, payment-gateway, email-provider]
source: "synthetic (RetailEase); structure after real SRE practice"
---

# RetailEase System Overview

RetailEase is an e-commerce checkout platform running on Azure. It lets customers browse a catalog, hold cart/session state, and place orders that are paid, stock-checked, persisted, and confirmed by email/SMS. All application services are deployed as containers on **Azure Container Apps**, backed by managed Azure data services and two third-party externals.

## Services (Azure Container Apps)

- **`checkout-api`** — the customer-facing edge and orchestrator. It receives checkout requests, coordinates the synchronous payment and inventory steps, reads/writes session and cart state, and publishes an order-placed event for downstream notification. It is the entry point where customer-facing symptoms first appear.
- **`payment-api`** — authorizes and captures payment. It calls the external `payment-gateway` to process the card and persists the payment record to `cosmos-db`.
- **`inventory-api`** — reserves and decrements stock for an order. It reads/writes stock state in `cosmos-db` and uses `redis-cache` for hot stock reads. It emits `reservation_error_rate` when reservations fail.
- **`catalog-api`** — serves product catalog data (listings, prices, descriptions). It reads from `cosmos-db` and caches hot reads in `redis-cache`. It is not on the synchronous checkout path.
- **`notification-worker`** — consumes order-placed events from `service-bus` and sends order confirmations through the external `email-provider`. It runs asynchronously, off the critical checkout path.

## Azure infrastructure backends

- **`cosmos-db`** (Azure Cosmos DB) — the system of record for orders, payments, stock, and catalog data. It is a shared, critical backend for `payment-api` and `inventory-api` (and read source for `catalog-api`).
- **`service-bus`** (Azure Service Bus) — the order-event queue decoupling checkout from notification. `checkout-api` publishes order-placed events; `notification-worker` consumes them.
- **`redis-cache`** (Azure Cache for Redis) — session/cart state plus a hot read cache used by `checkout-api`, `inventory-api`, and `catalog-api`.

## Externals

- **`payment-gateway`** — third-party card processor called by `payment-api` to authorize/capture card payments.
- **`email-provider`** — third-party transactional email/SMS service used by `notification-worker` to deliver order confirmations.

## Checkout request flow (end to end)

1. A **customer** submits a checkout request to **`checkout-api`**.
2. `checkout-api` reads session/cart state from **`redis-cache`**.
3. `checkout-api` synchronously calls **`payment-api`**, which:
   - calls the external **`payment-gateway`** to authorize and capture the card, and
   - persists the payment record to **`cosmos-db`**.
4. In parallel, `checkout-api` synchronously calls **`inventory-api`**, which reserves stock in **`cosmos-db`** (using **`redis-cache`** for hot stock reads).
5. Once payment and inventory both succeed, `checkout-api` publishes an **order-placed event** to **`service-bus`** and returns success to the customer.
6. Asynchronously, **`notification-worker`** consumes the order-placed event from `service-bus` and sends an order confirmation via the external **`email-provider`**.

Steps 3 and 4 are the **critical (synchronous) checkout path**: if payment or inventory fails, the customer cannot complete the purchase. Steps 5 and 6 are **asynchronous** — the customer's checkout completes independently of whether the notification is delivered, so notification failures degrade confirmations without blocking purchases. Product browsing via `catalog-api` is likewise off the synchronous checkout path.
