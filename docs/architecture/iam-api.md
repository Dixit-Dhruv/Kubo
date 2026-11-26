# Kubo IAM API — First Implementation Contract

**Status:** Implemented initial contract; subject to versioned evolution

Base path: `/api/v1`. Requests and responses use JSON. Protected endpoints require an opaque bearer token. AWS compatibility is not provided.

## Authentication

| Method and path | Access | Behavior |
|---|---|---|
| `POST /auth/login` | Public; limited to 5 attempts per minute per source IP in the initial single-process deployment | Accepts email and password; returns opaque bearer token and UTC expiry |
| `POST /auth/logout` | Authenticated | Revokes the presented token; returns `204` |
| `GET /users/me` | Authenticated | Returns the current account |

Tokens expire after one hour. Only the SHA-256 digest of a randomly generated high-entropy token is stored. There is no refresh endpoint in this slice; clients authenticate again after expiry. Passwords must be at least 12 characters and are hashed using Argon2id through a maintained password-hashing library.

The in-process login limit is not shared across multiple workers or replicas. Public deployments must enforce an additional edge/shared rate limit before exposure.

The first administrator is created through the one-time `kubo-iam bootstrap-admin` CLI command. Further users are provisioned by an operator through `kubo-iam create-user`; public registration and invitations are not implemented.

## Organizations and memberships

| Method and path | Access | Behavior |
|---|---|---|
| `POST /organizations` | Authenticated | Creates an organization; caller becomes its Owner |
| `GET /organizations` | Authenticated | Lists only organizations of which caller is a member |
| `GET /organizations/{organization_id}/members` | Owner or Admin | Lists member IDs, emails, roles, and join timestamps |
| `PUT /organizations/{organization_id}/members` | Owner or Admin | Adds or changes an existing account's membership to `admin` or `member` |
| `DELETE /organizations/{organization_id}/members/{user_id}` | Owner or Admin | Removes a non-owner membership |

### Initial role rules

- **Owner:** assigns Admin or Member, manages organization access, and cannot be removed or demoted through this API.
- **Admin:** manages Member access only; cannot grant Admin, modify/remove another Admin, or change ownership.
- **Member:** may use the organization but cannot manage memberships.

Ownership transfer and last-owner removal are intentionally unsupported. A non-member receives `404` when accessing an organization to avoid disclosing its existence; insufficient permission within an accessible organization returns `403`.

## Health

- `GET /health/live`: process liveness.
- `GET /health/ready`: verifies database connectivity.

## Error behavior

The initial contract uses standard HTTP status codes and FastAPI's structured `detail` response. Login failures return the same `401` message for unknown, inactive, or incorrectly authenticated accounts. Authorization failures must not reveal another organization's resource data.
