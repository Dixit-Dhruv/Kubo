# Kubo — Architecture Requirements and Implementation Baseline

**Document ID:** KUBO-ARCH-REC-001  
**Version:** 0.2
**Status:** Baseline selected; detailed service contracts remain in progress

## 1. Product definition

Kubo is a self-hosted, AWS-inspired local infrastructure platform. It exposes Kubo-defined APIs and manages real workloads on user-controlled infrastructure. AWS terminology is conceptual only: complete AWS emulation and AWS API/SDK compatibility are out of scope.

## 2. Confirmed requirements and decisions

| ID | Requirement or decision | Baseline |
|---|---|---|
| REQ-01 | Product model | Hybrid cloud-style management over local/self-hosted infrastructure |
| REQ-02 | Service topology | Independently deployable microservices |
| REQ-03 | First implementation scope | IAM, compute, and the networking needed by compute; API first |
| REQ-04 | Later service domains | Object storage and the user-facing Queue Service |
| REQ-05 | Compute runtime | Docker first; Firecracker is a possible later provider on Linux/KVM |
| REQ-06 | Metadata persistence | SQLite for development/tests; PostgreSQL for self-hosted deployments |
| REQ-07 | Internal asynchronous work | RabbitMQ; separate from the user-facing Queue Service |
| REQ-08 | Object data | Local filesystem backend initially |
| REQ-09 | Identity and ownership | Native Kubo accounts; organizations own resources and users receive access through membership/permissions |
| REQ-10 | Host support | Windows development via Docker Desktop/WSL2; Linux is the self-hosted execution target |
| REQ-11 | API compatibility | Custom Kubo APIs; no AWS compatibility promise |
| REQ-12 | Operational behavior | Long-running work is asynchronous, durably tracked, observable, and recoverable |
| REQ-13 | Workload policy | Only administrator-approved container images; no privileged mode, host networking, host mounts, or added capabilities in the first milestone |
| REQ-14 | IAM implementation baseline | Python/FastAPI; one-hour opaque bearer tokens stored as hashes; Argon2id password hashing with a 12-character minimum; Owner/Admin/Member roles |
| REQ-15 | Initial administrator | One-time interactive CLI bootstrap; operator-provisioned accounts for the first implementation |

## 3. First milestone boundaries

### Included

- User account bootstrap, authentication, organizations, membership, and authorization needed to secure API access.
- Compute resource create, inspect, start, stop, and delete lifecycle using Docker.
- The minimum networking behavior required to create and operate those compute resources.
- Durable resource and operation metadata, RabbitMQ-backed work, and operational health/error visibility.
- Linux self-hosted deployment and a reproducible Windows development environment.

### Deferred

- A management console.
- User-facing object storage and queue APIs.
- Firecracker, multi-region operation, high availability, and production-grade availability guarantees.
- General arbitrary-code execution beyond the documented compute image/configuration policy.

## 4. Architecture constraints

1. Each service owns its authoritative data and migrations; a service must not read or write another service's private tables.
2. Resource ownership and authorization are enforced by the owning service, not solely by the API gateway.
3. Host-level privileges are isolated behind narrowly scoped adapters; they are never exposed to API clients.
4. A successful request to start asynchronous work means accepted, not completed.
5. Cross-service workflows tolerate timeouts, retries, duplicate delivery, partial failure, and process restart.
6. Development and deployment backends must not silently promise identical behavior where their capabilities differ.
7. Core functionality must not depend on paid public-cloud services.

## 5. Detailed design items for the implementation milestone

These are deliberately narrower than the selected architectural baseline and must be specified before the affected feature ships:

- API versioning/evolution beyond the initial IAM, Compute, and Networking contracts.
- Account recovery, password changes, and organization invitations.
- Shared rate limiting for multiple service workers or replicas.
- Service secret delivery/rotation and RabbitMQ credential provisioning for local and deployed environments.
- Docker image approval/update process (catalog references pinned by digest), concrete resource-profile values/quotas, and cleanup behavior.
- Networking allocation ranges, host bind address, inbound exposure, egress, and host-firewall policy.
- RabbitMQ topology, bounded retry/backoff, dead-letter handling, and outbox/reconciliation requirements.
- Migration and test strategy for SQLite/PostgreSQL behavior parity.
- Backup/restore, audit retention, log policy, and supported Linux distributions.

These details do not reopen the selected product and service boundaries; they are implementation designs with security and operational impact.

## 6. Implementation readiness gate

Implementation may begin by building the shared foundation and IAM/compute vertical slice. Before exposing a capability to users, its API contract, authorization rules, failure semantics, operational limits, and automated verification must be documented. The first release is not complete until the deferred production risks are either addressed or explicitly accepted.
