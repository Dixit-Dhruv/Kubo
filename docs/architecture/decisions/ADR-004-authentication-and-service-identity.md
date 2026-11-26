# ADR-004: Native Account Authentication and Service Identity

- **Status:** Accepted
- **Decision date:** 2026-11-25
- **Decision owner:** Project Owner
- **Related decisions:** ADR-001, ADR-003

## Context

Kubo is self-hosted and must support multiple users and organizations. The owner selected native Kubo accounts instead of requiring an external identity provider for the first milestone. Human users, services, and workers have different identities and permissions.

## Decision

### User accounts and organizations

- Kubo manages local user accounts and authenticates users.
- Organizations own resources. Users access resources through organization membership and permissions.
- IAM owns accounts, organizations, membership, and authorization policy data.
- Compute and Networking enforce organization/resource authorization for their own data; API Gateway checks are not sufficient by themselves.
- OIDC or another external identity provider is not required for the first milestone.

### Service and worker identity

- Each service and worker has a distinct logical identity and least-privilege access.
- Service credentials are distinct from user credentials and RabbitMQ credentials are restricted to required queues/exchanges.
- Workers preserve the initiating user, organization, action, resource, operation, and correlation context. They validate current authoritative state rather than trusting message fields as authorization.
- The infrastructure adapter is the only component allowed to invoke privileged Docker operations.

### Security requirements

- Never store or log plaintext passwords, tokens, signing keys, or recovery secrets.
- Use a reviewed password-hashing implementation; do not implement cryptographic primitives.
- Do not ship default production credentials.
- Protect authentication with abuse controls and generic failure responses.
- User bearer tokens have a one-hour lifetime and support revocation and logout. Account
  recovery and password-change flows remain deferred.
- Record security-sensitive actions with actor, organization, action, target, outcome, and correlation/operation identifiers, without secrets.

## Consequences

Native accounts simplify a self-hosted first release and avoid requiring a separately operated identity provider. Kubo takes on security-sensitive credential lifecycle and account recovery responsibilities, so the authentication flow requires focused security review before release.

Domain-service authorization is duplicated at service boundaries by design; each service must enforce the policy needed to protect its own resources. A service identity does not inherit the user's identity or permissions automatically.

## Alternatives considered

- **Self-hosted or external OIDC provider:** not selected as a first-release dependency; may be considered later.
- **Gateway-only authorization:** rejected because domain services must protect their own data and operations.
- **Shared credentials for all services:** rejected because it prevents least-privilege access, attribution, and selective revocation.
- **Custom cryptography:** rejected. Native account ownership does not permit inventing cryptographic primitives or skipping security review.

## Implementation design gates

The first implementation uses one-hour opaque bearer tokens with server-side revocation, stores only token hashes, hashes passwords with Argon2id through a maintained library, and enforces a 12-character minimum. Login is limited to five attempts per minute per source IP in the single-process deployment; this in-memory limit is not sufficient for multiple workers or replicas, which require a shared or edge rate limit.

The one-time CLI bootstrap creates the first platform administrator. Additional accounts are operator-provisioned through the CLI; public registration and invitations are not included yet. Owner/Admin/Member semantics and the initial membership API are specified in the [IAM API contract](../iam-api.md).

Account recovery, stronger shared rate limiting, deployment secret delivery/rotation
procedures, and the policy for permission changes between operation acceptance and execution
remain release gates. The login flow must receive a focused security review before public
deployment.

The first internal service-credential mechanism is selected in
[ADR-009](ADR-009-service-identity-and-credentials.md): opaque per-service bearer credentials,
stored as hashes in IAM, scoped, and valid until revoked. Receivers validate requested
scopes through IAM on each internal request. Deployment secret delivery and service-to-user
authorization checks remain implementation gates.
