# Kubo System Architecture

**Document ID:** KUBO-ARCH-001
**Version:** 1.0
**Status:** Accepted baseline for the first implementation milestone
**Product model:** Self-hosted, AWS-inspired local infrastructure platform

## 1. Purpose

Kubo exposes custom APIs for managing cloud-style resources that run on user-controlled infrastructure. This document defines the first implementation boundary and the logical design used by the detailed architecture documents and ADRs.

The architecture is intentionally a small self-hosted platform, not a public cloud or a complete AWS emulator.

## 2. First milestone

The first milestone is API-first and includes:

- IAM: native Kubo accounts, organizations, membership, and authorization.
- Compute: asynchronous lifecycle management of Docker containers.
- Networking: the connectivity required by managed compute resources.
- RabbitMQ for internal asynchronous work.
- Durable per-service metadata and operation status.
- Linux self-hosted deployment and Windows development through Docker Desktop/WSL2.

Only administrator-approved container images may be launched in this milestone. Privileged containers, host networking, host mounts, and added Linux capabilities are prohibited.

Object storage, the user-facing Queue Service, a management console, and Firecracker are deferred. The filesystem object backend is the selected initial direction for the later object-storage milestone.

## 3. Logical service boundaries

| Service | Owns | First milestone responsibility |
|---|---|---|
| API Gateway | External routing and request-level controls; no domain data | Single public API entry point |
| IAM | Accounts, organizations, memberships, roles/permissions, credential records | Authenticate users and authorize organization access |
| Compute | Compute resources, desired/observed lifecycle, operations and provisioning records | Validate requests and coordinate container lifecycle |
| Networking | Logical network configuration, address/port allocations and network operations | Configure the connectivity needed by compute |
| Compute worker | Execution within the Compute service boundary | Consume internal work and reconcile Docker state |

Object Storage and Queue are later domain services. The user-facing Queue Service remains distinct from RabbitMQ used internally by Kubo.

Services own their schemas and migrations. They communicate through documented APIs or messages; direct access to another service's private tables is prohibited. A shared PostgreSQL server does not change this ownership rule.

## 4. Request and operation model

Bounded reads and validation use synchronous HTTP calls with timeouts. Resource operations that can outlive an HTTP request are asynchronous:

1. Authenticate and validate the request.
2. Resolve the organization and authorize the requested action.
3. Persist the resource intent and operation as accepted.
4. Publish or enqueue internal work through RabbitMQ.
5. Return an operation identifier; do not report the infrastructure action as complete.
6. A worker performs the action through the Docker/network adapters.
7. Persist observed state and terminal operation outcome.
8. Reconcile or report partial failure; never silently convert failure to success.

The owning service remains authoritative for its resource and operation state. Workflows must tolerate duplicate delivery, bounded retries, timeouts, worker restarts, and partial provisioning. The database-to-broker reliability mechanism is an implementation design to be selected before the compute worker ships.

## 5. Resource lifecycle

The initial compute lifecycle is:

`REQUESTED → PROVISIONING → RUNNING`

Additional states include `STOPPING`, `STOPPED`, `STARTING`, `TERMINATING`, `TERMINATED`, and `FAILED`. The implementation must define valid transitions and distinguish desired state from observed Docker state. A user request being accepted is not equivalent to a completed transition.

Deletion must clean up owned runtime and networking resources. Failed cleanup remains visible and retryable; it must not be hidden by marking the resource as successfully terminated.

## 6. Persistence

- Development and tests use SQLite, with a separate database/file boundary per service.
- Self-hosted deployments use PostgreSQL, with separate logical databases/schemas and credentials for each service.
- Each service owns and migrates its schema.
- Object payloads use a local filesystem backend when Object Storage is implemented; metadata and object bytes have separate ownership and backup requirements.
- RabbitMQ transports internal work but is not authoritative for resource or operation status.

SQLite/PostgreSQL behavioral differences must be covered by tests. The implementation must not rely on SQLite-specific behavior for deployed correctness.

## 7. Security and isolation

Organizations own resources; users access them through membership and permissions. Every domain service must enforce organization scope on reads and mutations. Guessing a resource identifier must not bypass authorization.

The initial IAM API implements native account authentication, organization roles, and one-time administrator bootstrap; see the [IAM API contract](iam-api.md) and [authentication ADR](decisions/ADR-004-authentication-and-service-identity.md). Internal service credentials and account recovery remain unimplemented security gates and must be designed before dependent APIs ship. No default production credentials are permitted.

The Docker Engine is a privileged host boundary. Only the isolated compute adapter may invoke it. Docker containers share the host kernel and are not a security boundary suitable for hostile arbitrary workloads. The first release therefore limits launches to administrator-approved images and prohibits privileged Docker options. This is not a claim of strong isolation or production-grade multi-tenancy.

## 8. Deployment

The supported self-hosted execution target is Linux. Windows is the development platform using Docker Desktop/WSL2 and Linux containers. Firecracker requires a compatible Linux/KVM host and is not part of the first milestone.

See [deployment architecture](deployment-architecture.md) for process placement and host boundaries.

## 9. Explicitly out of scope

- AWS API or SDK compatibility.
- Complete AWS service emulation.
- Arbitrary untrusted container execution.
- Public multi-tenant cloud availability guarantees or high availability.
- Multi-region operation, Kubernetes management, and Firecracker execution.
- A graphical management console in the first milestone.

## 10. Implementation design gates

Before the corresponding capability ships, specify its API contract and error model, authorization matrix, resource quotas, retry/recovery policy, service identity, data migration strategy, and operational procedures. Remaining detailed questions are tracked in [architecture requirements](architecture-requirement.md) and the ADR index.
