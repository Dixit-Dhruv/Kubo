# ADR-006: Asynchronous Operations and Recovery

- **Status:** Accepted
- **Decision date:** 2026-11-25
- **Decision owner:** Project Owner
- **Related decisions:** ADR-001, ADR-002, ADR-003, ADR-005

## Context

Provisioning and cleanup can outlive an API request and can partially succeed across Compute, Networking, RabbitMQ, and Docker. A request accepted by the API must not be confused with a completed infrastructure action.

## Decision

- Persist an operation record and resource desired state in the owning service before reporting acceptance.
- Return an operation identifier for asynchronous work and expose its current state and failure details.
- Distinguish accepted, in-progress, succeeded, failed, and (where supported) cancelled operations.
- Keep desired state separate from observed runtime state; reconcile after worker restart or observed drift.
- Use RabbitMQ for internal work, with consumers that validate messages, re-read authoritative state, and tolerate duplicate delivery.
- Make retries bounded and failures visible. Cleanup failure remains retryable and must not be presented as successful termination.
- Preserve the initiating actor and correlation context for authorization and audit.
- Use compensation or reconciliation for partial cross-service operations; do not assume distributed ACID transactions.
- Close the database/broker dual-write gap using a transactional outbox or equivalent recoverable design before productionizing provisioning.
- Require an `Idempotency-Key` for every Compute mutation. Scope it to the organization and
  initiating actor; the same normalized method/path/body replays the original operation, and
  a different request with the same key conflicts. Retain the key with its operation record.
- Compute's outbox publisher retries until publication with exponential delay capped at
  60 seconds. Workers claim operations atomically and make at most five total attempts;
  retryable failures use exponential backoff, then operation failure is durable and visible.

## Ownership

Each domain service owns operation records for the resources it owns. The Compute Service owns compute operations; Networking owns network operations. A separate global operation service is not required for the first milestone.

## Consequences

Durable status supports client polling and recovery after process failure, at the cost of state-machine design, idempotency, reconciliation, and operational tooling. RabbitMQ is transport, not authoritative operation state.

## Deferred implementation details

Cancellation semantics, dead-letter policy, operation retention, reconciliation cadence, and
the concrete broker topology remain service-level implementation details.
