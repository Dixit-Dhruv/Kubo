# ADR-001: Adopt a Microservices Architecture

- **Status:** Proposed
- **Date:** 2026-10-16
- **Decision owner:** Project Owner

## Context

Kubo is a self-hosted cloud platform with multiple distinct service
domains: compute, object storage, queues, networking, and IAM.

The project prioritizes independent service development, explicit
service boundaries, infrastructure integration, and distributed
systems engineering.

A modular monolith would simplify the initial deployment but would
provide fewer opportunities to design and operate independently
deployable services.

## Decision

Adopt a microservices architecture with independently deployable
domain services.

The proposed initial service boundaries are:

1. API Gateway
2. IAM Service
3. Compute Service
4. Object Storage Service
5. Queue Service
6. Networking Service
7. Operation Workers

The exact deployment boundaries of workers and infrastructure
adapters remain subject to detailed design.

### Database Ownership Policy

- Each service owns its logical database and schema.
- Services must not directly query or modify another service's
  private database.
- Each service owns its database migrations and schema evolution.
- Separate database credentials and least-privilege permissions
  must be used for each service.
- The initial deployment may use one shared database server.
- Moving a service to a dedicated database server must not require
  changes to its public API contract.
- Cross-service workflows must use documented APIs or messaging
  contracts rather than shared-table access.

A shared database server is an infrastructure optimization, not
permission to share database ownership.

### Transaction and Consistency Policy

- Use local database transactions for operations within a service.
- Do not assume atomic transactions across service databases.
- Design cross-service workflows to tolerate retries, timeouts,
  partial failures and duplicate messages.
- Evaluate the transactional outbox pattern for critical events.
- Define consistency requirements for each cross-service workflow.
- Use compensating actions or reconciliation where distributed
  operations cannot be rolled back atomically.

### Initial Database Infrastructure

A shared PostgreSQL server is the leading candidate for relational
metadata persistence, subject to a separate technology decision.

The database implementation for queue persistence and object
storage remains independently configurable. Not every service
is required to use PostgreSQL for every data category.

## Architectural Principles

- Each service owns its business logic and authoritative data.
- Services communicate through documented APIs or messaging
  contracts.
- Services do not directly access another service's private database.
- Long-running operations support explicit status tracking.
- Infrastructure providers are accessed through defined interfaces.
- Service failures and retries must have documented behavior.
- Local development must remain reproducible through a documented
  deployment configuration.

## Consequences

### Benefits

- Independent development and testing of service domains.
- Clear ownership and API contracts.
- Ability to evolve service implementations independently.
- Practical experience with distributed systems and failure handling.

### Costs and Risks

- More complex local deployment and debugging.
- Additional service-to-service communication.
- Distributed consistency and retry challenges.
- More demanding authentication, observability, and integration tests.
- Potential resource overhead on development machines.

## Additional Consequences

### Benefits

- Clear data ownership and service boundaries.
- Independent schema migrations and service evolution.
- Reduced initial infrastructure overhead.
- A path toward independent database scaling and deployment.
- Better alignment with microservice data-management practices.

### Costs and Risks

- Distributed workflows require explicit consistency handling.
- Shared database infrastructure remains a common failure domain.
- Database connection pools require capacity planning.
- Cross-service debugging requires correlated logs and operation IDs.
- Backup and restoration procedures must account for dependencies
  between services.
- Independent database ownership does not automatically provide
  tenant isolation or workload security.

### Mitigations

- Establish database ownership and access policies.
- Use idempotent APIs and explicit lifecycle state transitions.
- Define retry, timeout and compensation behavior.
- Monitor database connections, latency and resource consumption.
- Test partial failures and recovery procedures.
- Document cross-service dependencies and restoration order.

## Alternatives Considered

### Modular Monolith

Rejected as the primary architecture because independent service
deployment is an explicit project objective.

Its simpler development and operational model remains a useful
comparison when deciding which components warrant separate processes.

### Microservices with Shared Database Tables

Rejected because direct cross-service database access would weaken
service ownership and increase coupling.

## Open Questions

- Metadata database and per-service data isolation strategy.
- Internal service authentication.
- Synchronous versus asynchronous communication.
- Internal provisioning job mechanism.
- Local deployment topology.
- Service discovery and configuration.
- Failure recovery and observability requirements.

## Review Criteria

The decision can be approved when service boundaries, data ownership,
communication contracts, deployment topology, and operational costs
have been reviewed.