# Kubo — Architecture Requirements Reconciliation

**Document ID:** KUBO-ARCH-REC-001  
**Version:** 0.1  
**Status:** Draft — Open Decisions  
**Date:** 2026-10-16

## 1. Confirmed Requirements

| ID | Requirement | Architectural implication |
|---|---|---|
| REQ-01 | Hybrid AWS-inspired local infrastructure platform | Combine real local resource provisioning with cloud-style service APIs and workflows. |
| REQ-02 | Containers first, Firecracker later | Define a compute-provider abstraction so execution engines can be replaced. |
| REQ-03 | Initial services: compute, object storage, queues, networking, IAM | Establish service boundaries and contracts for all five capabilities. |
| REQ-04 | Local development and self-hosted server deployment | Separate application logic from host-specific infrastructure and configuration. |
| REQ-05 | Multiple users with separate resources and permissions | Establish tenant/resource ownership, authorization checks, and isolation boundaries. |
| REQ-06 | AWS-inspired concepts with custom APIs | Reuse cloud concepts without promising AWS API or SDK compatibility. |
| REQ-07 | Windows development plus Linux/KVM | Support a Windows development workflow while reserving Firecracker execution for a compatible Linux/KVM host. |
| REQ-08 | Infrastructure engineering depth | Prioritize lifecycle management, isolation, networking, failure recovery, and observability. |

## 2. Conflicts and Constraints

### 2.1 Windows development versus Firecracker

Firecracker requires a suitable Linux environment with KVM access. Windows development alone does not establish that this requirement is satisfied.

**Resolution:** Design a compute-provider interface. Implement the initial execution path using containers. Introduce Firecracker as a separate provider when a compatible Linux/KVM host is available.

The exact development topology remains open: Docker Desktop, WSL2, a Linux virtual machine, or a separate Linux host must be evaluated against the required capabilities.

### 2.2 Local execution versus multi-user isolation

A local installation and a shared self-hosted server have different threat models. Users sharing a server must not be able to access another tenant's resources or bypass resource limits.

**Resolution:** Design tenant ownership and authorization into the control plane from the beginning. Treat operating-system and workload isolation as separate security concerns.

Application-level authorization alone is not sufficient to establish strong workload isolation.

### 2.3 Cloud-style services versus implementation scope

Five service domains are in scope, but implementing every AWS capability would substantially expand the project.

**Resolution:** Implement narrowly defined Kubo APIs for compute, object storage, queues, networking, and IAM. AWS-inspired terminology does not imply complete service compatibility.

### 2.4 Queues and asynchronous provisioning

Resource provisioning can take longer than a typical HTTP request. Queues are also an explicit service requirement.

**Resolution:** Design asynchronous operations and durable state transitions. Whether the queue service also serves as the internal provisioning job system must be decided before detailed design.

### 2.5 Networking and self-hosted deployment

Local-only networking differs from exposing workloads through a shared server. Port allocation, tenant boundaries, inbound access, and firewall behavior depend on the target host.

**Resolution:** Define networking as a separate service boundary. Do not assume that Docker networking and Firecracker networking can share an identical implementation.

## 3. Missing Decisions

| ID | Decision required | Why it matters |
|---|---|---|
| OPEN-01 | Initial deployment topology | Determines the relationship between the API, worker processes, host and data stores. |
| OPEN-02 | Metadata database | Determines transactions, constraints, migrations and recovery strategy. |
| OPEN-03 | Object storage backend | Determines file layout, persistence, isolation and supported object operations. |
| OPEN-04 | Queue semantics and backend | Determines durability, ordering, visibility timeouts, retries and delivery guarantees. |
| OPEN-05 | Authentication model | Determines local login, credentials, token handling and administrator bootstrap. |
| OPEN-06 | Tenant model | Determines whether tenants are users, organizations, workspaces or another abstraction. |
| OPEN-07 | Network implementation | Determines address allocation, port publishing, firewall rules and isolation. |
| OPEN-08 | Compute resource limits | Determines CPU, memory, disk and concurrency enforcement. |
| OPEN-09 | Application deployment scope | Determines whether users launch predefined images, arbitrary images, source code or all three. |
| OPEN-10 | Observability scope | Determines which host and workload metrics, logs and events are required in the first release. |
| OPEN-11 | Recovery and persistence guarantees | Determines behavior after API crashes, host restarts and failed provisioning. |
| OPEN-12 | API versioning and compatibility | Determines the stability policy for custom Kubo APIs. |

## 4. Provisional Architecture Decisions

These are proposals for review, not approved technology choices.

1. Separate the control plane from workload execution.
2. Keep compute execution behind a provider interface.
3. Represent resource lifecycle state independently from the underlying runtime.
4. Enforce resource ownership at every relevant API boundary.
5. Use asynchronous jobs for long-running infrastructure operations.
6. Define explicit contracts between compute, networking, storage, IAM and queue services.
7. Make persistence and recovery behavior explicit rather than relying on in-memory state.
8. Keep host-specific operations behind privileged, narrowly scoped infrastructure adapters.
9. Treat monitoring, auditing and operational diagnostics as cross-cutting architectural requirements.
10. Avoid requiring public-cloud services for core functionality.

## 5. Review Gate

The System Architecture Document may be reviewed as a logical architecture proposal. The architecture should not be marked fully approved until the critical open decisions, security boundaries, persistence model, deployment topology and resource lifecycle have been resolved.

**Current decision:** Proceed with logical architecture and diagrams. Keep unresolved implementation choices explicitly marked as TBD.