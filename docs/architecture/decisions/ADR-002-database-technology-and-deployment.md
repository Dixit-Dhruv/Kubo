# ADR-002: Metadata Database and Deployment

- **Status:** Accepted
- **Decision date:** 2026-11-25
- **Decision owner:** Project Owner
- **Related decisions:** ADR-001

## Context

Kubo needs durable metadata for accounts, organizations, resources, and asynchronous operations. Developers use Windows, while self-hosted deployments target Linux. Each microservice must own its data.

## Decision

- Use SQLite for development and tests.
- Use PostgreSQL for self-hosted deployments.
- Maintain a separate data boundary and migration history for each service. Development uses a separate SQLite database/file per service; deployed services use separate PostgreSQL databases or equivalently isolated schemas and least-privilege credentials.
- Service code and migrations must preserve equivalent correctness across both backends. Do not rely on SQLite-specific behavior for deployed correctness.

The object payload backend is a separate concern: the later Object Storage Service initially uses local filesystem storage, not PostgreSQL blobs. RabbitMQ is not a metadata database.

## Consequences

**Benefits:** lightweight local setup and a durable relational database for deployed use, while retaining service-level data ownership.

**Costs and risks:** two database backends require compatibility tests; SQLite locking/concurrency behavior differs from PostgreSQL; PostgreSQL operations require backup, upgrade, and credential procedures.

## Alternatives considered

- PostgreSQL in every environment: closer development/deployment parity, but not selected for local development.
- SQLite in deployment: rejected as the shared self-hosted multi-user metadata backend.
- One shared schema with unrestricted cross-service access: rejected by ADR-001.

## Implementation requirements

- Add migrations and backend-specific integration tests for every service.
- Test upgrades from an empty database and from the previous supported schema.
- Document connection configuration, backup/restore, and credential rotation before deployment is considered production-ready.
- Decide the migration library and exact PostgreSQL database/schema layout during implementation design; neither is selected by this ADR.
