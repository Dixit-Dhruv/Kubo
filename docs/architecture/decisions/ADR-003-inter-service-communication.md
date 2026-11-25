# ADR-003: Inter-Service Communication and Internal Messaging

- **Status:** Accepted
- **Decision date:** 2026-11-25
- **Decision owner:** Project Owner
- **Related decisions:** ADR-001, ADR-006

## Context

Kubo needs bounded request/response interactions between independently deployable services and asynchronous execution for resource operations that can outlive an HTTP request.

## Decision

Use a hybrid communication model:

- Authenticated synchronous HTTP for bounded queries and commands with explicit timeouts and structured errors.
- RabbitMQ for internal asynchronous provisioning, lifecycle work, and other retryable background operations.
- Durable operation and resource status in the owning service's database. RabbitMQ transports work; it is not the source of truth.

The initiating API returns an operation identifier after durable acceptance. It must distinguish accepted/in-progress work from successful completion.

## Internal and user-facing queues

RabbitMQ is internal platform infrastructure. The later Kubo Queue Service is a separate user-facing domain with independent APIs, authorization, ownership, and operational policies. Sharing a future backend does not merge these security boundaries.

## Required rules

1. Every service interaction has a documented API or message contract.
2. Services do not access another service's private database.
3. Synchronous calls have bounded timeouts; avoid unbounded call chains.
4. Consumers validate messages and tolerate duplicate delivery.
5. Retries are bounded; poison messages and failed work remain observable.
6. Preserve operation and correlation identifiers across service boundaries.
7. Broker delivery is not proof of user authorization or operation success.
8. Address the database-to-broker dual-write gap with a transactional outbox or equivalent recovery mechanism before relying on asynchronous provisioning.

## Consequences

The hybrid approach keeps bounded queries straightforward while isolating long-running work from HTTP connection lifetime. It introduces eventual consistency, broker operations, duplicate delivery, retry policy, and partial-failure handling.

## Deferred implementation details

Queue types, retry/backoff values, dead-letter topology, schema compatibility rules, broker high-availability settings, and the precise outbox implementation are service-level design decisions. The first deployment is a single RabbitMQ node and does not provide broker high availability.
