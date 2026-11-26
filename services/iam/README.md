# Kubo IAM Service

The first implementation slice provides native account authentication and organization membership APIs.

## Local development (PowerShell)

From `services/iam`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
kubo-iam upgrade-db
kubo-iam bootstrap-admin --email admin@example.com
uvicorn kubo_iam.main:app --reload
```

The default development database is `sqlite:///./iam.db`. Set `KUBO_IAM_DATABASE_URL` to use another supported SQLAlchemy URL. The Docker image runs as a non-root user; production database configuration and secret delivery must be supplied by the deployment.

Create additional operator-provisioned accounts with `kubo-iam create-user --email user@example.test`. Account creation and invitations are not exposed as public API endpoints in this slice.

## Tests

```powershell
python -m pytest
```

## API

See [IAM API contract](../../docs/architecture/iam-api.md). OpenAPI is available at `/docs` during development.
