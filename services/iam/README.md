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

Create or revoke scoped internal service credentials with `kubo-iam create-service-credential`
and `kubo-iam revoke-service-credential`. The credential is printed once; inject it through
the deployment's secret mechanism and never commit it or include it in logs.

## Tests

```powershell
python -m pytest
```

The API tests use in-memory SQLite by default. To run them against PostgreSQL, set
`KUBO_IAM_TEST_DATABASE_URL` to a dedicated disposable test database before running pytest.
The test fixture creates and drops the IAM tables, so do not point it at a development or
production database.

## API

See [IAM API contract](../../docs/architecture/iam-api.md). OpenAPI is available at `/docs` during development.
