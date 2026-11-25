# Kubo Architecture

This directory is the architecture source of truth. The baseline records the decisions selected for the first implementation milestone while preserving later product capabilities as explicit future scope.

## Reading order

1. [Architecture requirements](architecture-requirement.md) — agreed scope, constraints, and milestone.
2. [System architecture](system-architecture.md) — logical structure and lifecycle model.
3. [System context](system-context.md), [container architecture](container-architecture.md), and [component architecture](component-architecture.md) — boundaries at different levels.
4. [Data flows](data-flow.md), [deployment architecture](deployment-architecture.md), and [security architecture](security-architecture.md) — runtime behavior and cross-cutting concerns.
5. [Architecture Decision Records](decisions/README.md) — rationale, alternatives, consequences, and status.

## Status conventions

- **Accepted** means the project owner selected the decision as the implementation baseline.
- **Proposed** means the direction is documented but needs a decision before implementation depends on it.
- **Deferred** means intentionally out of the first milestone; do not treat it as an implicit commitment.

An accepted architectural baseline does not imply production readiness. Detailed API schemas, resource limits, retry tuning, and operational procedures must be specified and tested as their services are implemented.

## Change workflow

1. Identify whether the change alters a requirement, boundary, deployment assumption, or accepted ADR.
2. For a material architectural change, update or add an ADR with context, decision, alternatives, consequences, and status.
3. Update affected architecture diagrams and flows in the same change.
4. Keep deferred capabilities and implementation-specific TBDs explicit; do not imply unsupported guarantees.
5. Verify internal links, Mermaid diagrams, and status references before proposing the documentation change.

## Document index

| Document | Purpose |
|---|---|
| [Requirements](architecture-requirement.md) | Product scope, first milestone, constraints, and readiness criteria |
| [System architecture](system-architecture.md) | Logical services, interfaces, and lifecycle |
| [System context](system-context.md) | Actors and system boundary |
| [Container architecture](container-architecture.md) | Runtime processes and dependencies |
| [Component architecture](component-architecture.md) | Responsibility and ownership boundaries |
| [Data flows](data-flow.md) | Key synchronous and asynchronous workflows |
| [Deployment architecture](deployment-architecture.md) | Development and self-hosted topologies |
| [Security architecture](security-architecture.md) | Threats, trust boundaries, and controls |
| [Decision records](decisions/README.md) | Decision status and rationale |
