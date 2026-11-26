# Kubo

**A self-hosted, AWS-inspired platform for managing infrastructure on your own machines.**

Kubo provides custom APIs for provisioning and operating local compute workloads and related cloud-style resources. It is intended for learning and experimenting with infrastructure engineering without requiring paid public-cloud services for core functionality.

Kubo is not a complete AWS emulator and does not promise AWS API or SDK compatibility.

## Project status

**Current phase:** Initial implementation — IAM service started.

The architecture baseline is documented. The first implementation slice is the API-first IAM service; Compute and Networking follow.

## First implementation milestone

The first milestone is API-first and focuses on:

- IAM: native Kubo accounts, organizations, membership, and authorization.
- Compute: asynchronous lifecycle management of Docker containers.
- Networking: the connectivity required by managed compute resources.
- A self-hosted Linux deployment, with Windows development supported through Docker Desktop/WSL2.

Object storage and the user-facing Queue Service are later milestones. RabbitMQ is an internal platform dependency for asynchronous operations and is not the user-facing Queue Service.

## Architecture baseline

- Independently deployable services with explicit ownership of data and contracts.
- SQLite for development and tests; PostgreSQL for self-hosted deployments.
- Organization-owned resources, with users accessing them through membership and permissions.
- Native Kubo account authentication; security controls and remaining protocol details are documented in the security architecture.
- Docker as the initial compute runtime; Firecracker is a possible future provider for compatible Linux/KVM hosts.
- Durable operation records and RabbitMQ-backed asynchronous work.
- Local filesystem storage for the initial object-storage backend.

These choices and their consequences are recorded in [Architecture Decisions](docs/architecture/decisions/README.md).

## Documentation

Start with the [architecture index and workflow](docs/architecture/README.md), then read the [system architecture](docs/architecture/system-architecture.md) and [implementation requirements](docs/architecture/architecture-requirement.md).

| Document | Purpose |
|---|---|
| [System context](docs/architecture/system-context.md) | Actors, platform boundary, and external infrastructure |
| [Container architecture](docs/architecture/container-architecture.md) | Deployable services and infrastructure dependencies |
| [Component architecture](docs/architecture/component-architecture.md) | Responsibilities and service boundaries |
| [IAM API contract](docs/architecture/iam-api.md) | Initial account and organization APIs |
| [Compute API contract](docs/architecture/compute-api.md) | Compute lifecycle, authorization, operations, and port requests |
| [Networking service contract](docs/architecture/networking-api.md) | Automatic compute attachments and managed port allocations |
| [Deployment architecture](docs/architecture/deployment-architecture.md) | Windows development and Linux self-hosting |
| [Data flows](docs/architecture/data-flow.md) | Authentication, organization access, and compute lifecycle |
| [Security architecture](docs/architecture/security-architecture.md) | Trust boundaries, threats, and required controls |
| [Architecture decisions](docs/architecture/decisions/README.md) | Accepted decisions and remaining proposals |

## Design principles

- Local-first execution and cost awareness.
- Explicit resource ownership and lifecycle management.
- Least privilege and tenant isolation by design.
- Replaceable infrastructure providers with honest capability boundaries.
- Durable, observable operations with explicit failure behavior.
- Documented APIs, decisions, and verification.

## Contributing

Keep implementation consistent with the accepted architecture decisions. Propose changes that alter a recorded decision through an ADR before or alongside the implementation change.
