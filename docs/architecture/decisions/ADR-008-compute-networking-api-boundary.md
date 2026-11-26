# ADR-008: First-Milestone Compute and Networking API Boundary

- **Status:** Accepted
- **Decision date:** 2026-11-26
- **Decision owner:** Project Owner
- **Related decisions:** ADR-003, ADR-005, ADR-006, ADR-009

## Context

The first Compute slice needs organization-scoped container lifecycle management and
networking, but public network creation and host-port controls would expand the initial
surface before allocation, firewall, and service-identity policies are fully implemented.

## Decision

- Expose organization-scoped Compute resources and operations through the public `/api/v1`
  API.
- Allow all active organization members to read Compute resources and operations. Only
  Owners and Admins may create, start, stop, or delete them.
- Require an operator-approved image catalog key and an operator-defined resource profile;
  clients cannot submit arbitrary Docker image references or override profile limits.
- Allow clients to request container ports and protocols. Networking allocates host ports
  from an operator-configured range; clients cannot choose host ports, bind addresses, or
  host networking.
- Make Networking an internal service for this first slice. Compute requests automatic,
  organization-scoped attachments; independent user-managed network CRUD is deferred.
- Keep allocation, provisioning, and cleanup asynchronous and expose outcomes through
  durable Compute operations.

## Consequences

The public API stays focused on Compute while Networking owns attachments and port
allocations. Clients can discover allocated mappings through Compute resources, but network
addressing, host firewall policy, egress, inter-compute connectivity, profile values, image
administration, and deployment secret delivery remain implementation gates.

The HTTP and internal attachment shapes are defined in the [Compute API contract](../compute-api.md)
and [Networking service contract](../networking-api.md).

## Alternatives considered

- **Public user-managed networks in the first slice:** deferred until network lifecycle,
  isolation, and authorization behavior are specified.
- **Caller-selected host ports or host networking:** rejected because they bypass central
  allocation and weaken host-boundary controls.
- **Caller-supplied CPU and memory values:** deferred in favor of operator-managed profiles
  with enforceable limits.

## Implementation constraints

Internal Networking endpoints must not be routed through public ingress. Compute and
Networking must enforce organization scope, authenticate service calls, validate all
requests, and make retries safe. The host-port range, bind address, firewall policy, and
allocation cleanup/reconciliation behavior must be configured and tested before exposure.
