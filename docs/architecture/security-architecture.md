# Kubo — System Architecture Document

**Document ID:** KUBO-ARCH-001  
**Version:** 0.1  
**Status:** Draft — Architecture Review Required  
**Architecture style:** Modular control plane with pluggable infrastructure providers  
**Product model:** Hybrid AWS-inspired local infrastructure platform

---

## 1. Purpose

This document defines the proposed high-level architecture of Kubo.

Kubo will provide cloud-inspired resource management through custom APIs and a management interface while executing workloads on user-controlled infrastructure.

The architecture separates resource management, service APIs, persistent state and host-specific execution so that implementation technologies can evolve without requiring a redesign of the entire platform.

This document describes logical responsibilities and interactions. Technology selections and deployment details marked TBD require further review.

## 2. Architectural Goals

- Provision and manage real local compute workloads.
- Provide defined service boundaries for compute, object storage, queues, networking and IAM.
- Support multiple users with separate resources and permissions.
- Support local development and self-hosted deployment.
- Enable a future Firecracker provider without coupling the control plane to a specific runtime.
- Make resource lifecycle operations recoverable and observable.
- Minimize mandatory external infrastructure and cloud-provider expenditure.
- Provide stable, documented custom APIs.

## 3. Scope

### 3.1 Included

1. Compute resource management.
2. Object storage operations.
3. Queue creation and message operations.
4. Network configuration and controlled workload connectivity.
5. Identity, authentication and authorization.
6. Resource metadata and persistent state.
7. Asynchronous provisioning and lifecycle management.
8. Audit events, operational logs and basic metrics.
9. Local and self-hosted deployment modes.

### 3.2 Excluded from the initial scope

- Complete AWS service emulation.
- Guaranteed AWS SDK compatibility.
- Globally distributed infrastructure.
- Multi-region scheduling and replication.
- A managed Kubernetes service.
- A public multi-tenant cloud with production-grade availability guarantees.

## 4. System Context

Kubo sits between users and the infrastructure on which their workloads run.

Users interact through the management interface and custom APIs. Kubo authenticates requests, checks permissions, manages resource metadata, coordinates long-running operations and delegates execution to infrastructure providers.

The execution environment supplies the actual compute, storage and networking capabilities. Kubo remains responsible for presenting a consistent resource-management experience across supported providers.

See `system-context.md` for the context diagram.

## 5. Logical Architecture

The proposed architecture has the following logical layers.

### 5.1 Presentation Layer

**Responsibility:** Provide a consistent management experience.

Responsibilities include:

- Displaying resource inventories and status.
- Creating and managing resources.
- Showing provisioning progress and failures.
- Displaying logs, events and resource usage.
- Supporting user and access administration.

The frontend must not directly access privileged host interfaces or bypass the control plane.

Frontend technology: TBD.

### 5.2 API and Control Plane

**Responsibility:** Expose the Kubo API and coordinate resource operations.

Responsibilities include:

- Request validation and API versioning.
- Authentication and authorization enforcement.
- Tenant and resource ownership checks.
- Resource metadata management.
- Lifecycle transition validation.
- Job creation and coordination.
- Quota enforcement.
- Consistent error responses and operation status.

Proposed API framework: Python with FastAPI, pending an architecture decision.

### 5.3 Identity and Access Management

**Responsibility:** Establish user identity and authorize access to resources.

Responsibilities include:

- User and credential management.
- Authentication.
- Role and permission management.
- Resource ownership and tenant boundaries.
- Administrative operations.
- Authorization audit events.

The exact authentication protocol, tenant model and credential-storage mechanism remain TBD.

### 5.4 Compute Service

**Responsibility:** Manage the lifecycle of compute resources independently of the underlying execution engine.

Responsibilities include:

- Instance creation and configuration validation.
- Start, stop, restart and termination requests.
- Resource lifecycle tracking.
- CPU, memory and execution limits.
- Provider selection and capability validation.
- Runtime status reconciliation.
- Cleanup following failures or termination.

The compute service must not assume that a successful API request means that a workload is already running.

### 5.5 Compute Provider Interface

**Responsibility:** Isolate runtime-specific behavior from the compute service.

Initial proposed provider:
- Container execution provider.

Future proposed provider:
- Firecracker microVM provider.

Each provider will implement a defined contract for provisioning, lifecycle operations, status inspection and cleanup.

Provider-specific networking, storage and isolation capabilities must be declared explicitly rather than assumed to be identical.

### 5.6 Object Storage Service

**Responsibility:** Provide object-oriented storage operations.

Potential capabilities:

- Create and delete buckets or namespaces.
- Upload, retrieve and delete objects.
- List objects.
- Enforce ownership and access permissions.
- Persist object metadata.
- Apply storage quotas.

The backing storage engine, object naming rules, maximum object size and consistency guarantees remain TBD.

### 5.7 Queue Service

**Responsibility:** Provide asynchronous message processing.

Potential capabilities:

- Create and delete queues.
- Publish and receive messages.
- Acknowledge processed messages.
- Handle visibility timeouts and redelivery.
- Track queue metadata and message lifecycle.

Delivery semantics, message ordering, persistence and the queue backend must be specified before implementation.

The queue service may support provisioning workflows, but that relationship is not yet approved.

### 5.8 Networking Service

**Responsibility:** Manage supported connectivity for workloads.

Potential capabilities:

- Define logical networks.
- Allocate network addresses or ports.
- Configure controlled inbound access.
- Associate workloads with networks.
- Apply network access policies.
- Clean up networking resources during termination.

The initial network model and the differences between container and microVM networking require a separate design.

### 5.9 Persistence Layer

**Responsibility:** Persist authoritative resource metadata and any state assigned to durable storage.

Data categories include:

- Users, roles and permissions.
- Resource ownership and configuration.
- Resource lifecycle and operation status.
- Object metadata.
- Queue metadata and durable message state.
- Network configuration.
- Audit records.

The metadata database, blob-storage implementation and queue persistence mechanism remain TBD.

A workload's filesystem and the platform's authoritative resource metadata must have explicitly defined persistence and deletion semantics.

### 5.10 Observability

**Responsibility:** Make platform behavior diagnosable.

The design should account for:

- Structured application logs.
- Resource lifecycle events.
- Provisioning failures.
- Host and workload metrics.
- Audit events.
- Health checks.
- Correlation between API requests and asynchronous operations.

The initial metrics collector and log-retention policy remain TBD.

## 6. Principal Request and Execution Flow

A typical instance-creation operation should follow this logical sequence:

1. The user submits a create-instance request.
2. The API validates the request and authenticates the caller.
3. IAM and resource-ownership rules authorize the operation.
4. The control plane validates resource quotas and configuration.
5. The system persists an operation record and an initial resource state.
6. A provisioning operation is scheduled.
7. The compute service selects a compatible provider.
8. The provider creates the workload and requests any required networking or storage resources.
9. The system records observed runtime state and the operation result.
10. The frontend displays the resulting status.

The precise transaction boundaries, scheduling mechanism and compensation behavior are still to be designed.

The architecture must account for duplicate requests, worker crashes, partial provisioning, host failures and cleanup failures.

## 7. Resource Lifecycle

The proposed logical lifecycle is:

`REQUESTED → PROVISIONING → RUNNING`

Additional states include:

- `STOPPING`
- `STOPPED`
- `STARTING`
- `RESTARTING`
- `TERMINATING`
- `TERMINATED`
- `FAILED`

These are candidate states, not the final state machine.

The detailed lifecycle specification must define:

- Valid transitions.
- Triggering events.
- Whether operations are synchronous or asynchronous.
- Retry behavior.
- Timeouts.
- Cancellation behavior.
- Recovery after a process or host restart.
- The difference between desired state and observed runtime state.
- Cleanup and terminal-state retention.

## 8. Deployment Model

Kubo must support two intended deployment modes.

### 8.1 Local Development

The control plane and supporting services run in a developer-controlled environment.

Windows is the development platform, while advanced virtualization functionality may require a compatible Linux/KVM host.

The exact division of services between Windows, Linux and container environments remains TBD.

### 8.2 Self-Hosted Server

Kubo runs on user-controlled server infrastructure and can be accessed by authorized users over a network.

The deployment design must define:

- Network exposure and TLS.
- Administrative access.
- Persistent storage locations.
- Service startup and shutdown behavior.
- Backups and recovery.
- Resource quotas.
- Host and workload isolation.
- Configuration and secrets management.

A self-hosted deployment does not automatically imply support for high availability or production-grade multi-tenancy.

See `deployment-architecture.md` for the deployment topology, which remains pending host and persistence decisions.

## 9. Security Architecture Principles

Security must be enforced at both the control plane and the workload execution boundary.

Required design principles:

1. Authenticate every protected operation.
2. Authorize every resource access against its owner or tenant.
3. Deny access by default.
4. Separate administrative permissions from ordinary resource permissions.
5. Avoid exposing privileged host interfaces to users.
6. Apply CPU, memory, disk and network resource limits.
7. Validate workload images and configuration.
8. Protect credentials and sensitive configuration.
9. Record security-relevant administrative actions.
10. Define isolation controls appropriate to the execution backend.

The detailed threat model must assess malicious workloads, cross-tenant access, host compromise, credential theft, resource exhaustion and network abuse.

## 10. Architectural Constraints

- Core functionality should not require paid public-cloud infrastructure.
- Windows development must not be confused with native Firecracker host support.
- Provider-specific capabilities must not be hidden behind an interface that promises unsupported behavior.
- Long-running resource operations must have explicit status and failure reporting.
- Persistent resources must have documented deletion and recovery semantics.
- Resource ownership must be enforced consistently across all service domains.

## 11. Outstanding Architecture Decisions

The following decisions remain open:

1. Metadata database and transaction strategy.
2. Queue backend and delivery semantics.
3. Object storage backend and persistence guarantees.
4. Initial network implementation.
5. Authentication protocol and tenant model.
6. Compute-provider interface and resource profile.
7. Workload image and application deployment policy.
8. Host environment and service deployment topology.
9. Job scheduling, retries and crash recovery.
10. Logging, metrics and audit retention.
11. API versioning and error conventions.
12. Backup, restoration and resource cleanup policies.

These decisions must be documented through Architecture Decision Records where appropriate.

## 12. Architecture Approval Criteria

The architecture can be approved when:

- System boundaries and responsibilities are clear.
- Context, container and component diagrams are reviewed.
- Deployment assumptions are validated.
- Resource lifecycle and failure semantics are defined.
- Identity, authorization and isolation requirements are addressed.
- Data ownership and persistence requirements are explicit.
- Critical technical decisions have documented rationale.
- Risks and constraints have been reviewed.

**Current status:** Draft. Logical architecture proposed; detailed technology decisions and security review remain outstanding.