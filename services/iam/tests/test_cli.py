import os
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from kubo_iam import cli
from kubo_iam.database import Base, make_engine
from kubo_iam.models import BootstrapClaim, ServiceCredential, User
from kubo_iam.security import hash_password, hash_service_token


@pytest.fixture
def cli_sessions(monkeypatch):
    database_url = os.environ.get("KUBO_IAM_TEST_DATABASE_URL", "sqlite://")
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(cli, "upgrade_database", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", test_sessions)
    monkeypatch.setattr(cli, "prompt_for_password", lambda: hash_password("correct horse battery"))

    try:
        yield test_sessions

    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_bootstrap_claim_prevents_a_second_initial_admin(cli_sessions):
    cli.bootstrap_admin("admin@example.com")
    with pytest.raises(ValueError, match="Bootstrap is only available"):
        cli.bootstrap_admin("another-admin@example.com")

    with cli_sessions() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1
        assert session.scalar(select(func.count()).select_from(BootstrapClaim)) == 1


def test_bootstrap_rejects_a_claim_already_taken_by_another_process(cli_sessions):
    with cli_sessions() as session:
        session.add(BootstrapClaim(name="initial_admin"))
        session.commit()

    with pytest.raises(ValueError, match="Bootstrap is only available"):
        cli.bootstrap_admin("admin@example.com")

    with cli_sessions() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 0


def test_service_credential_cli_creates_hashed_scoped_credential_and_revokes_it(
    cli_sessions,
    capsys,
):
    with cli_sessions() as session:
        session.add(
            User(
                email="admin@example.com",
                password_hash=hash_password("correct horse battery"),
                is_platform_admin=True,
            )
        )
        session.commit()

    cli.create_service_credential(
        "compute-worker",
        ["network:attachments:manage", "iam:authorize"],
    )
    output = capsys.readouterr().out.splitlines()
    credential_id = output[0].split()[3]
    token = output[1].split(": ", maxsplit=1)[1]

    with cli_sessions() as session:
        credential = session.get(ServiceCredential, UUID(credential_id))
        assert credential is not None
        assert credential.token_hash == hash_service_token(token)
        assert token not in credential.token_hash
        assert credential.scopes == ["iam:authorize", "network:attachments:manage"]

    cli.revoke_service_credential(credential_id)

    with cli_sessions() as session:
        credential = session.get(ServiceCredential, UUID(credential_id))
        assert credential is not None
        assert credential.revoked_at is not None


def test_service_credentials_reject_ungranted_scopes(cli_sessions):
    with pytest.raises(ValueError, match="not allowed"):
        cli.create_service_credential("compute-worker", ["iam:authenticate"])
