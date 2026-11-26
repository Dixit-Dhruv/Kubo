# Kubo Compute API — Initial Contract

**Status:** Accepted for the first implementation

Base path: `/api/v1`. Requests and responses use JSON. Client requests require an IAM bearer
token. Compute owns compute resources and their operations; it does not expose Docker API
details.

## Authorization

- Any active organization member may list and inspect that organization's compute resources
  and operations.
- Only organization Owners and Admins may create, start, stop, or delete resources.
- A non-member receives `404` for organization-scoped resources. A Member attempting a
  mutation receives `403`.
- Compute authenticates the user's IAM bearer token, then checks the actor and action through
  IAM's internal `/user-auth/authorize` endpoint using its own `iam:authorize` service credential.
  The worker rechecks the actor stored on the accepted operation before executing delayed work.
- Compute enforces organization scope itself; a gateway decision or unguessable identifier
  is not an authorization boundary.

## Resources

### Compute resource

A compute resource contains:

| Field | Meaning |
|---|---|
| `id` | Kubo resource UUID |
| `organization_id` | Owning organization UUID |
| `name` | Non-empty organization-scoped display name |
| `image` | Operator-approved image catalog key; clients cannot submit arbitrary Docker image references |
| `profile` | Operator-defined compute profile key |
| `desired_state` | `running`, `stopped`, or `terminated` |
| `observed_state` | `requested`, `provisioning`, `running`, `stopping`, `stopped`, `starting`, `terminating`, `terminated`, or `failed` |
| `ports` | Requested container ports and, after allocation, their managed host-port mappings |
| `created_at`, `updated_at` | UTC timestamps |

CPU, memory, storage, and other limits are defined by the selected operator-managed profile;
clients cannot override them in this contract. The profile catalog, concrete values, quotas,
and approved-image administration process remain implementation gates.

The operator-managed image catalog maps keys to immutable `repository@sha256:<digest>`
references. Compute rejects mutable tags and resolves client-supplied keys only; an image
update requires changing the operator catalog to a newly reviewed digest. The catalog is
provided as JSON with an `images` object and is validated when loaded.

Profiles are operator-provided JSON entries with positive `cpu_millicores`, `memory_bytes`,
and `ephemeral_storage_bytes` values; there are no built-in profile limits. The storage bound
applies to the container's ephemeral writable layer. Persistent volumes are out of scope.
The Docker provider must verify that the host can enforce the configured storage bound and
must fail closed rather than launch without it.

The Docker adapter resolves or pulls only the digest-pinned image, applies CPU, memory, and
per-container writable-layer limits on every create request, and creates the container with
networking disabled until Networking attaches it. If Docker rejects the storage option or
any other configured limit, the create operation fails; the adapter never retries without
the limit.

### Create request

`POST /organizations/{organization_id}/computes`

```json
{
  "name": "web",
  "image": "approved-web",
  "profile": "small",
  "ports": [
    { "container_port": 8080, "protocol": "tcp" }
  ]
}
```

`ports` is optional and defaults to an empty list. A requested port is a container port;
clients do not select a host port or bind address. Kubo's Networking service allocates the
host port. Omitting ports means no inbound host-port mapping is requested.

Creation targets `running` and is asynchronous. Return `202 Accepted` with the resource and
its accepted operation. Do not report the resource as running until the provider and required
network attachment have succeeded and the observed state is persisted.

## Endpoints

| Method and path | Behavior |
|---|---|
| `POST /organizations/{organization_id}/computes` | Accepts a create operation; returns `202` |
| `GET /organizations/{organization_id}/computes` | Lists only resources in the organization; supports opaque cursor pagination (`limit` defaults to 50, maximum 100) |
| `GET /organizations/{organization_id}/computes/{compute_id}` | Returns a scoped resource and current desired/observed state |
| `POST /organizations/{organization_id}/computes/{compute_id}/start` | Requests an asynchronous start; returns `202` |
| `POST /organizations/{organization_id}/computes/{compute_id}/stop` | Requests an asynchronous stop; returns `202` |
| `DELETE /organizations/{organization_id}/computes/{compute_id}` | Requests asynchronous cleanup; returns `202` |
| `GET /organizations/{organization_id}/operations/{operation_id}` | Returns operation status and safe failure details, scoped to the organization |

Create, start, stop, and delete responses contain an operation identifier. Operation states
are `accepted`, `running`, `succeeded`, and `failed`. The operation record is authoritative;
RabbitMQ is only a work transport. A failed operation includes a stable error code and a
client-safe message, never raw provider output or secrets.

Every create, start, stop, and delete request requires an `Idempotency-Key` header containing
1-128 visible ASCII characters. Keys are scoped to the organization and initiating user. A
replay with the same normalized method, path, and body returns the original resource and
operation; reusing the key for a different request returns `409`. The key is retained for at
least as long as its operation record.

The resource, operation, and outbox event are committed in one database transaction. The
outbox publisher retries until the event is published, using exponential delays of 1, 2, 4,
8, 16, 32, then 60 seconds maximum; broker downtime does not discard accepted work. Workers
claim operations atomically and make at most five total attempts. Retryable failures use
exponential backoff; non-retryable failures or exhausted attempts set the operation to
`failed` with safe error details.

An invalid lifecycle transition returns `409`. Invalid request fields or unsupported image
and profile keys return `422`. Missing/expired authentication returns `401`. A dependency
failure that prevents durable acceptance or authorization returns `503`. If a recoverable
outbox accepts work while RabbitMQ is unavailable, the response remains `202` and the
operation stays pending until publication recovers. Errors use the JSON `detail` response
convention established by the IAM API.

If asynchronous port allocation or provisioning fails after acceptance, the operation
returns `failed` with a stable error code and safe message; the original request remains
`202 Accepted`.

## Lifecycle and cleanup

- Create: `requested` → `provisioning` → `running`.
- Stop: `running` → `stopping` → `stopped`.
- Start: `stopped` → `starting` → `running`.
- Delete: non-terminated state → `terminating` → `terminated`.
- An unrecovered provider or cleanup failure is visible as `failed`; it is not reported as
  successful completion.
- The worker re-reads authoritative desired state and handles duplicate work safely.
- Terminated resources remain inspectable while their operation is retained. The retention
  duration and cleanup policy must be set before implementation.
- Cancellation, arbitrary resource updates, and client-supplied Docker options are out of
  scope for the first contract.

The exact idempotency-key behavior, retry/backoff values, and database-to-broker outbox
mechanism remain implementation gates under ADR-006.

## Compute API runtime configuration

The Compute API reads its runtime settings from the `KUBO_COMPUTE_` environment prefix:

| Variable | Purpose |
|---|---|
| `KUBO_COMPUTE_DATABASE_URL` | SQLAlchemy database URL; defaults to a local SQLite database |
| `KUBO_COMPUTE_IAM_URL` | IAM service base URL |
| `KUBO_COMPUTE_SERVICE_TOKEN` | Secret scoped for `iam:authorize`, issued to `compute-api` |
| `KUBO_COMPUTE_IMAGE_CATALOG_PATH` | Operator-managed image catalog JSON path |
| `KUBO_COMPUTE_PROFILE_CATALOG_PATH` | Operator-managed profile catalog JSON path |

The service token must be delivered through the deployment's secret mechanism and must not
be committed. There are no built-in images or compute profiles; missing or invalid catalog
files make create requests unavailable rather than providing defaults.
