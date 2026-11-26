# Kubo Networking Service — Initial Contract

**Status:** Accepted for the first implementation

The first Compute slice uses automatic, organization-scoped network attachments. Clients do
not create or manage Network resources independently; there are no public network CRUD
endpoints in this slice. Compute exposes requested and allocated port mappings through its
resource API.

## Service boundary

- Networking owns attachment and host-port allocation records.
- The Compute Worker requests or releases attachments through the authenticated internal
  service contract. It requires the `network:attachments:manage` scope; Networking validates
  that identity with IAM before processing a request.
- Requests carry the organization, compute resource, operation, and initiating-actor
  identifiers for validation and audit. A user bearer token alone is not a service identity.
- Service authentication does not by itself prove the initiating user's organization
  permission. The worker must revalidate current operation and user authorization separately
  through IAM's `/user-auth/authorize` endpoint, using the actor persisted on the operation.
- See [ADR-009](decisions/ADR-009-service-identity-and-credentials.md) for credential
  lifecycle and the initial scope registry.

## Internal attachment contract

### Ensure attachment

`POST /internal/v1/organizations/{organization_id}/compute-attachments`

Request:

```json
{
  "compute_id": "uuid",
  "operation_id": "uuid",
  "initiated_by": "user-uuid",
  "ports": [
    { "container_port": 8080, "protocol": "tcp" }
  ]
}
```

Networking creates or reuses the attachment for the compute resource and allocates a host
port for each requested container-port/protocol pair. It selects host ports from an
operator-configured range; callers cannot choose host ports or bind addresses. A repeated
request with the same organization, compute, and port set returns the existing allocation.
A different port set for an existing attachment is a conflict in this slice.

The response contains the attachment identifier and each requested container port, protocol,
allocated host port, and any operator-configured reachable host address. No public reachability
is implied when the deployment has not configured an address and firewall policy.

### Release attachment

`DELETE /internal/v1/organizations/{organization_id}/compute-attachments/{compute_id}`

Release is idempotent and returns `204`, including when the attachment is already absent.
The worker releases an attachment after successful resource cleanup. A failed cleanup keeps
the allocation reserved and visible for retry; stopping a resource does not release its
mapping, so a later start can retain the same endpoint.

## Security and failure behavior

- Host networking, caller-selected host ports, and host-interface selection are prohibited.
- Allocations are unique on the host for the configured protocol/port range and are scoped
  to the owning organization and compute resource.
- Invalid port requests return `422`; exhausted allocation capacity or conflicting attachment
  state returns `409`; unauthenticated or unauthorized service calls return `401` or `403`.
- The service validates message/request schema and authoritative state, and treats retries as
  expected. It does not trust a client-supplied organization or compute identifier by itself.
- Host bind address, ingress/firewall policy, egress policy, inter-compute connectivity,
  allocation range, and cleanup reconciliation remain deployment or implementation gates.

The attachment endpoint is an internal contract and must not be routed through public ingress.
RabbitMQ remains internal work transport, not a network-allocation authority.
