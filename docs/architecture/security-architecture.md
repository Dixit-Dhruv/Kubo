# Kubo — Security Architecture

**Document ID:** KUBO-ARCH-SEC-001
**Version:** 1.0
**Status:** Baseline requirements accepted; security-sensitive implementation details require review

## 1. Security objectives

Kubo must prevent unauthorized account, organization, and resource access; constrain infrastructure operations; preserve attribution for asynchronous actions; and make security-relevant failures observable. Authentication establishes an identity. Each service still authorizes actions against the relevant organization and resource.

## 2. Trust boundaries

| Boundary | Trust assumption and required control |
|---|---|
| API client to API Gateway | Untrusted network/client; use protected transport in deployed environments, validate all inputs, rate/size limit as appropriate |
| Gateway to domain services | Internal traffic is not inherently trusted; authenticate service callers and validate trusted identity context |
| User to organization/resource | User-supplied IDs are untrusted; domain services enforce membership, permissions, and ownership |
| Worker to RabbitMQ | Broker messages are untrusted inputs; authenticate/authorize broker access, validate schemas, deduplicate, and preserve attribution |
| Compute adapter to Docker Engine | Highly privileged host boundary; isolate adapter access and never expose the engine API to users or unrelated services |
| Workload to host/other organizations | Docker shares the host kernel; approved images and prohibited options reduce risk but do not provide strong hostile-tenant isolation |
| Service to its database | Each service is trusted only for its own data; separate credentials and prohibit cross-service database access |

## 3. Accounts, organizations, and authorization

- Kubo manages native local user accounts; no external identity provider is required by the first milestone.
- Organizations own compute and network resources. Users receive access through organization membership and permissions.
- IAM owns account and organization membership data. Compute and Networking enforce organization-scoped access to their own resources.
- The initial role names, permissions, invitation model, account recovery, and administrator bootstrap procedure are implementation design gates.
- A random resource identifier is not an authorization control. Unauthorized resource existence and data must not be disclosed.
- Disable/revoke access when an account or membership is disabled. Asynchronous workers must revalidate current operation and authorization state according to the policy defined for the operation.

## 4. Native account security requirements

Before native login ships, its design must specify:

- Password verifier using a modern password-hashing function with reviewed parameters; never store or log plaintext passwords.
- Credential transport and session/access-token format, expiry, revocation, rotation, and logout behavior.
- Login abuse controls, generic authentication failures, and account recovery/change flows.
- Initial administrator creation without hardcoded or shared default credentials.
- Protection of signing/session secrets and per-environment secret injection.
- Tests for disabled accounts, invalid credentials, expired/revoked sessions, and unauthorized organization/resource access.

The exact token/session mechanism, hashing library/parameters, and recovery flow are not yet selected. They must be resolved and security-reviewed before account authentication is exposed to users.

## 5. Compute and host security

The first release accepts only administrator-approved container images. Images must be explicitly configured by an operator; pinning an immutable image digest is preferred and the exact approval/update procedure is an implementation gate.

The compute API must reject privileged mode, host networking, host filesystem mounts, added capabilities, and any unapproved image. It must apply documented CPU, memory, storage, and network limits before a workload can be launched.

Docker containers share the host kernel. Therefore:

- Do not claim strong isolation against malicious workloads or production-grade multi-tenant isolation.
- Do not permit arbitrary member-supplied images in the first release.
- Restrict Docker Engine access to the privileged adapter; the Docker API/socket is effectively host-administrator access.
- Keep secrets and control-plane credentials out of workload environments and images unless explicitly scoped and authorized.
- Firecracker or another stronger isolation design requires a separate threat-model and provider decision before hostile workloads are supported.

## 6. Internal services and asynchronous work

- Each service and worker has a distinct logical identity and least-privilege credentials.
- RabbitMQ is restricted to internal network paths and service-specific permissions; its credentials are not user credentials.
- Messages are validated and idempotent handlers use authoritative service state. Message fields alone cannot grant permission.
- Preserve the initiating user, organization, action, target resource, operation ID, and correlation ID for audit and authorization.
- Audit records distinguish the initiating user from the executing service/worker and exclude passwords, bearer tokens, private keys, and other secrets.
- Service-to-service authentication mechanism, credential rotation/bootstrap, broker permissions, and audit retention are implementation design gates.

## 7. Data and operational security

- Separate service database credentials and restrict access to each service's own store.
- Protect backups and persistent volumes; define restore access and retention before production use.
- Use TLS for network-exposed deployments. Keep database, RabbitMQ, Docker, and service administration interfaces off public ingress.
- Log authentication/authorization denials and lifecycle failures without leaking secrets or sensitive internal details.
- Document vulnerability reporting, supported image updates, host patching, and incident response before describing the platform as production-ready.

## 8. Threats and first-release disposition

| Threat | First-release control / limitation |
|---|---|
| Cross-organization access | Organization scoping and authorization in each owning domain service; negative integration tests |
| Stolen or guessed credentials | Password/session controls, rate limiting, secret handling, account disablement; implementation details pending |
| Malicious container or host escape | Admin-approved images and restricted Docker options; shared-kernel risk remains, so arbitrary workloads are out of scope |
| Docker API compromise | Isolate privileged adapter and restrict access; Docker Engine remains a trusted host boundary |
| Forged/replayed internal message | Broker ACLs, schema validation, idempotency, authoritative state checks, and operation attribution |
| Resource exhaustion | Per-resource and per-organization quotas/limits; numeric defaults are an implementation gate |
| Host or disk failure | Documented backup/recovery and visible failed operations; single-host availability is not guaranteed |

## 9. Review gate

The native authentication flow, organization permission matrix, trusted service identity, compute resource limits, image approval process, and Docker adapter isolation must receive a focused security review before the first multi-user compute release.
