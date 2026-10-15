# ADR-003: Inter-Service Communication

- **Status:** Proposed
- **Date:** 2026-10-16
- **Decision Owners:** Kubo Project
- **Related Decisions:** ADR-001, ADR-002

## 1. Context

Kubo is designed as a microservices-based, self-hosted cloud platform.

Its domain services include:

- IAM Service
- Compute Service
- Object Storage Service
- Queue Service
- Networking Service
- Operation Workers

These services must communicate while maintaining independent deployment,
clear ownership of business logic, and separate authoritative data.

Kubo must support both immediate API interactions and long-running
infrastructure operations such as creating, starting, stopping, and
terminating compute resources.

A communication strategy must address:

- Service coupling
- Request latency and timeouts
- Long-running operations
- Service failures and retries
- Duplicate message delivery
- Event consistency
- Observability and debugging
- Local development and self-hosted deployment complexity

## 2. Decision

Kubo will use a hybrid inter-service communication model.

### 2.1 Synchronous Communication

Synchronous HTTP APIs will be used when a caller needs an immediate
response from another service.

Examples include:

- Retrieving resource metadata
- Checking resource ownership or permissions through an authoritative
  service interface, where required by the security design
- Fetching resource configuration
- Performing bounded internal queries
- Invoking operations that can return a clear result within a bounded
  request timeout

Synchronous calls must use explicit API contracts, request timeouts,
structured errors, and appropriate authentication.

Services must not depend on unbounded chains of synchronous calls.

### 2.2 Asynchronous Communication

Asynchronous messaging will be used for workflows that may take a
significant amount of time or that should not require the initiating
request to remain open.

Examples include:

- Compute provisioning
- Compute termination and cleanup
- Network resource provisioning
- Resource lifecycle coordination
- Retryable background work
- Domain event publication
- Recovery and reconciliation tasks

The initiating API should return an operation identifier when work has
been durably accepted but has not yet completed.

Clients can use that identifier to query operation status.

The system must distinguish between:

- Request accepted
- Operation in progress
- Operation succeeded
- Operation failed

An accepted request must not be represented as a successfully completed
infrastructure operation.

### 2.3 Internal Message Broker

RabbitMQ is the proposed internal message broker for Kubo.

Its initial responsibilities are limited to platform-internal messaging,
including:

- Asynchronous provisioning jobs
- Background lifecycle tasks
- Retryable infrastructure operations
- Domain events where asynchronous delivery is appropriate

RabbitMQ is not the authoritative store for resource state or operation
status. Those records must be persisted by their owning services.

The initial local development environment may use a single RabbitMQ
node. This simplifies setup but does not provide broker high availability.

Critical messages must use appropriate durability settings, publisher
confirms, and consumer acknowledgements.

Consumers must be idempotent, and retry behavior must be bounded.
Failed messages must have a documented dead-letter and investigation
path.

Queue type, retention, replication, retry topology, and production
high-availability settings require a separate workload-specific review.

The user-facing Kubo Queue Service remains logically separate from
RabbitMQ's internal platform messaging responsibilities.

### 2.4 Operation Tracking

Long-running operations must have durable status records.

An operation record should conceptually include:

- Operation identifier
- Operation type
- Target resource identifier, when applicable
- Current operation status
- Creation and update timestamps
- Error information, when applicable
- Correlation identifier

The exact schema and state transitions will be defined in a separate
design specification.

The service responsible for an operation owns its authoritative
operation state, unless a future architecture decision defines a
dedicated operation service as the owner.

### 2.5 Service Contracts

Every service interaction must use a defined contract.

Contracts may include:

- HTTP API specifications
- Message schemas
- Event schemas
- Versioning and compatibility rules
- Error and retry semantics

A service must not access another service's database directly.

A service must not depend on undocumented implementation details of
another service.

### 2.6 Event Handling

Asynchronous consumers must be designed to tolerate duplicate delivery.

Where practical, handlers should be idempotent so processing the same
message more than once does not produce unintended duplicate effects.

Messages should carry identifiers sufficient for tracing, deduplication,
and correlation with the originating operation.

The architecture must define how failed messages are retried, how
poison messages are handled, and how messages are recovered after
consumer failures.

The exact broker and delivery guarantees remain open decisions.

### 2.7 User-Facing Queue Service

Kubo's Queue Service is a cloud capability exposed to platform users.

It allows users to create and use application queues.

It is conceptually distinct from the internal messaging mechanism used
for Kubo's own provisioning jobs and domain events.

The two may use the same underlying messaging technology in the future,
but they must have separate contracts, authorization rules, resource
ownership, and operational policies.

Sharing an underlying technology does not imply sharing a logical
service or security boundary.

## 3. Consequences

### 3.1 Benefits

- Immediate API interactions remain straightforward.
- Long-running operations do not depend on extended HTTP connections.
- Infrastructure workflows can continue after the initiating request
  ends.
- Asynchronous processing supports retries and failure recovery.
- Explicit contracts reduce coupling between services.
- Operation records improve visibility into resource lifecycle changes.
- Correlation identifiers improve debugging across service boundaries.

### 3.2 Costs and Risks

- Asynchronous workflows introduce eventual consistency.
- Message delivery can be duplicated or delayed.
- Failed workflows may leave partially provisioned resources.
- Retry policies require careful design to prevent retry storms.
- Distributed tracing and debugging become more important.
- A message broker adds deployment and operational complexity.
- Event publication can become inconsistent with database changes unless
  an appropriate reliability pattern is implemented.

## 4. Alternatives Considered

### Alternative A: Synchronous HTTP for All Communication

Rejected as the default architecture.

Long-running provisioning would be vulnerable to request timeouts,
cascading failures, and tight runtime coupling between services.

Synchronous HTTP remains appropriate for bounded interactions.

### Alternative B: Asynchronous Messaging for All Communication

Not selected as the default architecture.

Using messages for every interaction would add unnecessary complexity
to simple queries and operations that require immediate results.

### Alternative C: Hybrid Communication

Recommended.

This approach uses synchronous APIs for bounded interactions and
asynchronous messaging for long-running or event-driven workflows.

It balances implementation simplicity with the reliability requirements
of infrastructure provisioning.

RabbitMQ is the proposed broker for asynchronous communication.
The broker choice does not change the decision to use synchronous HTTP
for bounded request-response interactions.

## 5. Required Design Rules

1. Every service interaction must have an explicit contract.
2. Services must not directly access another service's database.
3. Long-running operations must expose durable status.
4. HTTP requests must have bounded timeouts.
5. Asynchronous handlers must tolerate duplicate delivery.
6. Retries must be bounded and use an appropriate backoff policy.
7. Resource provisioning and cleanup must account for partial failure.
8. Cross-service workflows must not assume a single ACID transaction.
9. Internal platform messaging must remain logically distinct from the
   user-facing Queue Service.
10. Correlation identifiers must be propagated across service calls and
    messages where applicable.

## 6. Open Questions

The following decisions require separate evaluation:

- Which RabbitMQ queue types and policies should be used for each
  workload and deployment profile?
- What retry limits, backoff intervals, and dead-letter policies should
  apply to provisioning jobs and domain events?
- Should critical event publication use the transactional outbox pattern?
- What broker topology and recovery objectives are required for
  production self-hosted deployments?
- Should critical event publication use the transactional outbox pattern?
- What are the standard retry and dead-letter policies?
- Which service owns operation records and lifecycle coordination?
- Which interactions require synchronous permission checks?
- What message schema and versioning strategy should be used?
- How will distributed tracing and correlation be implemented?
- How will reconciliation recover resources after partial failure?

## 7. Acceptance Criteria

This ADR may be accepted when:

- The synchronous and asynchronous boundaries are documented.
- The operation ownership model is defined.
- The internal messaging and user-facing Queue Service distinction
  is reflected in the architecture diagrams.
- The broker and event reliability strategy have been evaluated.
- Failure handling, idempotency, and observability requirements are
  represented in the relevant design documents.

## 8. Review

This ADR is a proposal.

It must not be treated as an accepted architectural decision until
reviewed and explicitly approved.