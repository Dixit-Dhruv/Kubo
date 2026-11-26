import pytest
from sqlalchemy.orm import sessionmaker

from kubo_compute.database import Base, make_engine
from kubo_compute import models as _models


@pytest.fixture
def compute_session():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with test_sessions() as session:
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()
