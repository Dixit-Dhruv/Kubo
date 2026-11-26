# Kubo Cloud Dashboard

A lightweight local frontend for the implemented IAM and Compute APIs. It uses no frontend
dependencies and does not change or configure either backend. The local Node server serves
the static page and proxies `/api/iam/*` to IAM and `/api/compute/*` to Compute, avoiding
browser CORS configuration changes.

## Run

Start IAM and Compute as described in the [IAM guide](../services/iam/README.md) and
[Compute contract](../docs/architecture/compute-api.md), then start the dashboard:

```powershell
Set-Location C:\Kubo\frontend
npm run dev
```

Open `http://127.0.0.1:5173`. The proxy defaults to IAM at `http://127.0.0.1:8001` and
Compute at `http://127.0.0.1:8000`. Override those upstreams with
`KUBO_DASHBOARD_IAM_URL` and `KUBO_DASHBOARD_COMPUTE_URL`; override the frontend port with
`KUBO_DASHBOARD_PORT`.

Sign in with an IAM user. Create an organization if needed, then create and operate compute
resources. The user token is held in page memory only. Recent operation IDs are kept in
`sessionStorage` because the Compute API does not expose an organization-wide operations
list.

The UI includes IAM and Compute only. Port mappings are intentionally omitted: the
Networking attachment adapter is not implemented, and the current worker fails port-bearing
creates safely. For an accepted create request, start the Compute outbox publisher and worker
separately; actual Docker provisioning also requires a valid digest-pinned image and a
Docker Engine that enforces the configured resource limits.
