import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from kubo_iam import cli
from kubo_iam.database import Base, make_engine
from kubo_iam.models import BootstrapClaim, User
from kubo_iam.security import hash_password


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
