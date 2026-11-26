import os
from itertools import count

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from kubo_iam.database import Base, get_db, make_engine
from kubo_iam.main import create_app

_client_addresses = count(10)


@pytest.fixture
def test_context():
    database_url = os.environ.get("KUBO_IAM_TEST_DATABASE_URL", "sqlite://")
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        with test_sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    address = f"127.0.0.{next(_client_addresses)}"
    with TestClient(app, client=(address, 12345)) as client:
        yield client, test_sessions
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
