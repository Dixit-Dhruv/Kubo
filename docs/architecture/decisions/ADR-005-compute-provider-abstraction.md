# ADR-005: Compute Provider Abstraction and Initial Image Policy

- **Status:** Accepted
- **Decision date:** 2026-11-25
- **Decision owner:** Project Owner
- **Related decisions:** ADR-001, ADR-004

## Context

Kubo manages real local workloads but must not couple resource lifecycle state to one runtime. The first release targets Docker; Firecracker is a possible future provider and requires compatible Linux/KVM.

## Decision

- Define a compute-provider contract for create, start, stop, inspect, and delete/cleanup operations.
- Implement the first provider using Docker Engine on Linux; Windows development uses Docker Desktop/WSL2.
- Keep provider-specific capabilities explicit. A provider must not claim unsupported networking, storage, or isolation behavior.
- The first release permits only administrator-approved images.
- Reject privileged mode, host networking, host mounts, added capabilities, and other configurations that cross the documented host boundary.
- Isolate Docker Engine access behind a restricted compute adapter. Docker API access is host-level privilege.
- Treat Firecracker as future scope requiring a separate implementation and security review; it is not a fallback silently selected at runtime.

## Consequences

The provider boundary supports runtime evolution and independent lifecycle testing. Docker containers share the host kernel; the first release does not provide strong isolation for arbitrary hostile workloads. Image approval, resource limits, cleanup, and Docker API access require explicit implementation controls.

## Alternatives considered

- **Direct Docker calls throughout the compute service:** rejected because it couples lifecycle policy to the runtime.
- **Firecracker first:** deferred because the target requires Linux/KVM and is outside the first milestone.
- **Arbitrary member-provided images:** rejected for the first milestone because of the host-kernel and host-control risk.

## Implementation design gates

Specify the provider contract/error mapping, approved-image management and update process, digest policy, CPU/memory/storage/network limits, persistent-volume semantics, Docker API protection, and cleanup/reconciliation behavior before exposing compute to multiple organizations.
