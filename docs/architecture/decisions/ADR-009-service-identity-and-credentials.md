# ADR-009: Internal Service Identity and Credentials

- **Status:** Accepted
- **Decision date:** 2026-11-26
- **Decision owner:** Project Owner
- **Related decisions:** ADR-003, ADR-004, ADR-008

## Context

Compute, its worker, and Networking make internal requests on behalf of separate logical
services. User bearer tokens and RabbitMQ credentials do not authenticate these callers.
The first self-hosted deployment needs distinct service identities, least-privilege scopes,
and revocation without introducing an external identity provider.

## Decision

- IAM issues opaque, high-entropy bearer credentials to individual service identities.
- IAM stores only each credential's SHA-256 digest, identity, granted scopes, creation time,
  and revocation time. The plaintext credential is displayed once by the local CLI.
- Credentials remain valid until explicitly revoked. Rotation creates a replacement,
  deploys it to the caller, verifies the new credential, then revokes the old one.
- A receiving service validates the caller's requested scope through
  `POST /internal/v1/service-auth/authorize` on IAM for each request. Validation does not
  use a cache; revocation therefore takes effect on the next validation. If IAM is
  unavailable, internal authorization fails closed.
- The initial scope registry is limited to:
  - `api-gateway`: `iam:authenticate`
  - `compute-api`: `iam:authorize`
  - `compute-worker`: `iam:authorize`, `network:attachments:manage`
  - `networking`: `iam:authorize`
- The endpoint authenticates a service and checks a service scope. It does not assert that
  the initiating user is authorized for an organization or resource; domain authorization
  remains a separate IAM decision.
- Services authenticate the user's bearer token on the request, then pass the verified user
  ID, organization ID, and Compute action to IAM's internal
  `POST /internal/v1/user-auth/authorize` endpoint with the `iam:authorize` service scope.
  IAM checks current account activity and membership: all members may read, while only
  Owners and Admins may mutate. Workers recheck the actor ID persisted with the accepted
  operation; they do not depend on the original user token remaining valid.
- This endpoint trusts the authenticated internal service to assert the user ID it verified.
  Only `compute-api` and `compute-worker` may request these decisions, and every Compute
  operation must remain organization-scoped independently.
- Service credentials are distinct from human tokens and RabbitMQ credentials. They are
  provisioned and revoked through operator CLI commands, not public API endpoints.

## Consequences

Central IAM storage and live validation provide explicit identity, scope enforcement, and
prompt revocation without custom cryptography. Each internal call depends on IAM
availability and adds a bounded request to the call path. The deployment must deliver
credentials as secrets, protect internal network paths, and redact authorization headers
from logs.

## Alternatives considered

- **Shared credential across services:** rejected because it prevents least-privilege access
  and selective revocation.
- **Locally configured shared secrets:** rejected because each receiving service would need
  independent credential state and rotation procedures.
- **Short-lived signed service tokens:** deferred to avoid signing-key distribution and
  validation complexity in the first single-host release.
- **Mutual TLS:** deferred because it requires certificate authority provisioning and
  rotation procedures.

## Implementation constraints

Use maintained libraries and standard SHA-256 hashing only for the high-entropy opaque
credential digest; do not invent token cryptography. Do not log plaintext credentials.
Internal service routes must not be exposed through public ingress. Define service-to-user
authorization checks, deployment secret delivery, audit policy, timeouts, and recovery
behavior before dependent Compute and Networking APIs are exposed.
