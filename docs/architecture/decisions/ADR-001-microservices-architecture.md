# ADR-001: Microservices and Service Ownership

- **Status:** Accepted
- **Decision date:** 2026-11-25
- **Decision owner:** Project Owner

## Context

Kubo has distinct IAM, compute, networking, object-storage, and user-facing queue domains. The project is intended to explore infrastructure engineering and independently deployable services. Microservices increase operational and distributed-systems complexity, especially on a single self-hosted machine, but the project owner selected them for the first implementation.

## Decision

Implement independently deployable services with explicit contracts and ownership. The first milestone contains:

1. API Gateway
2. IAM Service
3. Compute Service and its worker
4. Networking Service
5. RabbitMQ for internal asynchronous work

Object Storage and the user-facing Queue Service are deferred service domains. A management console is deferred; the first milestone is API-first.

## Data ownership

- Each service owns its authoritative data, schema, and migrations.
- Services must not directly read or modify another service's private tables.
- Development uses a separate SQLite store/file per service. Self-hosted deployments use PostgreSQL with separate service credentials and logical data boundaries.
- A shared database server is an infrastructure choice, not permission to share tables.
- Cross-service workflows use documented authenticated APIs or message contracts.

## Consistency rules

- Use local transactions inside a service.
- Do not assume a transaction spans multiple services.
- Design cross-service work for timeouts, duplicate messages, partial failures, retries, and compensation/reconciliation.
- Each service remains authoritative for its resources and operation status.

## Consequences

**Benefits:** clear data ownership, independent service contracts, and a path to evolve domains separately.

**Costs:** more local processes and configuration, service authentication, correlated observability, distributed consistency work, and higher resource use.

Mitigate these costs with a reproducible single-host deployment, explicit API/message schemas, bounded synchronous calls, durable operation state, and failure-focused tests.

## Alternatives considered

- **Modular monolith first:** simpler to build and operate, but not selected because the owner chose independently deployable services from the first release.
- **Microservices with shared tables:** rejected because it violates service ownership and couples independent deployments.

## Implementation constraints

Microservice boundaries do not require a separate physical database server per service. They do require separate ownership, credentials, migrations, and no cross-service table access.
