# ADR-007: IAM Implementation Stack

- **Status:** Accepted
- **Decision date:** 2026-11-25
- **Decision owner:** Project Owner
- **Related decisions:** ADR-002, ADR-004

## Context

The IAM service is the first implementation slice. It must support the accepted Python/FastAPI direction, SQLite for development, PostgreSQL for deployment, and independently versioned service migrations.

## Decision

- Implement IAM with Python 3.12 or newer and FastAPI.
- Use SQLAlchemy 2.x for persistence and Alembic for schema migrations.
- Use Pydantic for request/response validation and settings.
- Use pytest and HTTPX for service tests.
- Use `pwdlib` with its Argon2 support for password verification; do not implement password-hashing primitives.
- Keep the IAM service's package, dependencies, migrations, tests, and container definition under `services/iam`.

## Consequences

FastAPI provides the API and OpenAPI surface; SQLAlchemy and Alembic support SQLite/PostgreSQL persistence with explicit migrations. The service remains independently installable and deployable. Dependency upgrades require compatibility tests across both database backends.

## Alternatives considered

Other Python web frameworks and database libraries were not selected for the first service. The service boundaries and API contracts remain independent of this implementation stack.

## Implementation constraints

- Pin dependency ranges in the service manifest and review security updates.
- Run migrations as an explicit deployment step; do not make application startup silently mutate the schema.
- Keep authentication logic behind IAM service functions and use maintained cryptographic libraries.
- The container runs as a non-root user and must not receive Docker Engine access.
