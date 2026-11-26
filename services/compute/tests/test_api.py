from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from kubo_compute.api import (
    get_current_actor,
    get_iam_client,
    get_image_catalog,
    get_profile_catalog,
)
from kubo_compute.catalog import ComputeProfile, ImageCatalog, ProfileCatalog
from kubo_compute.database import Base, get_db, make_engine
from kubo_compute.main import app
from kubo_compute.models import ComputeResource

ORGANIZATION_ID = UUID("089b3a23-afb4-4a6d-819a-5e7fdbac0084")
ACTOR_ID = UUID("8c07034d-15ae-46cb-846b-fdb9911e637b")
IMAGE_REFERENCE = "registry.example.com/kubo/web@sha256:" + ("a" * 64)


class FakeIAMClient:
    def __init__(self) -> None:
        self.authorized_actions: list[str] = []
        self.forbidden_action: str | None = None

    def authorize(self, organization_id: UUID, user_id: UUID, action: str) -> None:
        assert organization_id == ORGANIZATION_ID
        assert user_id == ACTOR_ID
        self.authorized_actions.append(action)
        if action == self.forbidden_action:
            raise HTTPException(status_code=403, detail="Insufficient organization permissions.")


@pytest.fixture
def api_client():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    iam = FakeIAMClient()

    def override_db():
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_actor] = lambda: ACTOR_ID
    app.dependency_overrides[get_iam_client] = lambda: iam
    app.dependency_overrides[get_image_catalog] = lambda: ImageCatalog(
        images={"approved-web": IMAGE_REFERENCE}
    )
    app.dependency_overrides[get_profile_catalog] = lambda: ProfileCatalog(
        profiles={
            "small": ComputeProfile(
                cpu_millicores=500,
                memory_bytes=536870912,
                ephemeral_storage_bytes=1073741824,
            )
        }
    )

    with TestClient(app) as client:
        yield client, iam, test_sessions

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_create_api_authenticates_and_persists_accepted_work(api_client):
    client, iam, test_sessions = api_client

    response = client.post(
        f"/api/v1/organizations/{ORGANIZATION_ID}/computes",
        headers={"Idempotency-Key": "create-1"},
        json={"name": " web ", "image": "approved-web", "profile": "small"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["resource"]["name"] == "web"
    assert body["resource"]["image"] == "approved-web"
    assert body["resource"]["desired_state"] == "running"
    assert body["resource"]["observed_state"] == "requested"
    assert body["operation"]["status"] == "accepted"
    assert iam.authorized_actions == ["compute:create"]
    with test_sessions() as session:
        assert session.query(ComputeResource).count() == 1


def test_create_rejects_unsupported_catalog_entry(api_client):
    client, iam, _ = api_client
    response = client.post(
        f"/api/v1/organizations/{ORGANIZATION_ID}/computes",
        headers={"Idempotency-Key": "create-2"},
        json={"name": "web", "image": "not-approved", "profile": "small"},
    )

    assert response.status_code == 422
    assert iam.authorized_actions == ["compute:create"]


def test_create_replay_survives_catalog_removal(api_client):
    client, _, _ = api_client
    create_url = f"/api/v1/organizations/{ORGANIZATION_ID}/computes"
    headers = {"Idempotency-Key": "create-replay"}
    body = {"name": "web", "image": "approved-web", "profile": "small"}
    initial = client.post(create_url, headers=headers, json=body)
    app.dependency_overrides[get_image_catalog] = lambda: ImageCatalog(images={"other": IMAGE_REFERENCE})

    replay = client.post(create_url, headers=headers, json=body)

    assert replay.status_code == 202
    assert replay.json()["resource"]["id"] == initial.json()["resource"]["id"]
    assert replay.json()["operation"]["id"] == initial.json()["operation"]["id"]


def test_lifecycle_enforces_state_and_idempotency(api_client):
    client, _, test_sessions = api_client
    created = client.post(
        f"/api/v1/organizations/{ORGANIZATION_ID}/computes",
        headers={"Idempotency-Key": "create-3"},
        json={"name": "web", "image": "approved-web", "profile": "small"},
    )
    compute_id = created.json()["resource"]["id"]
    invalid_start = client.post(
        f"/api/v1/organizations/{ORGANIZATION_ID}/computes/{compute_id}/start",
        headers={"Idempotency-Key": "start-1"},
    )
    assert invalid_start.status_code == 409

    with test_sessions() as session:
        resource = session.get(ComputeResource, UUID(compute_id))
        resource.observed_state = "running"
        session.commit()

    stop_url = f"/api/v1/organizations/{ORGANIZATION_ID}/computes/{compute_id}/stop"
    first = client.post(stop_url, headers={"Idempotency-Key": "stop-1"})
    replay = client.post(stop_url, headers={"Idempotency-Key": "stop-1"})

    assert first.status_code == 202
    assert replay.status_code == 202
    assert replay.json()["operation"]["id"] == first.json()["operation"]["id"]
    assert replay.json()["resource"]["observed_state"] == "stopping"


def test_mutation_requires_authorization_before_acceptance(api_client):
    client, iam, test_sessions = api_client
    iam.forbidden_action = "compute:create"

    response = client.post(
        f"/api/v1/organizations/{ORGANIZATION_ID}/computes",
        headers={"Idempotency-Key": "create-4"},
        json={"name": "web", "image": "approved-web", "profile": "small"},
    )

    assert response.status_code == 403
    with test_sessions() as session:
        assert session.query(ComputeResource).count() == 0


def test_compute_list_uses_timezone_safe_cursor(api_client):
    client, _, _ = api_client
    create_url = f"/api/v1/organizations/{ORGANIZATION_ID}/computes"
    for key in ("page-1", "page-2"):
        response = client.post(
            create_url,
            headers={"Idempotency-Key": key},
            json={"name": key, "image": "approved-web", "profile": "small"},
        )
        assert response.status_code == 202

    first_page = client.get(
        f"/api/v1/organizations/{ORGANIZATION_ID}/computes",
        params={"limit": 1},
    )
    assert first_page.status_code == 200
    assert first_page.json()["next_cursor"] is not None
    second_page = client.get(
        f"/api/v1/organizations/{ORGANIZATION_ID}/computes",
        params={"limit": 1, "cursor": first_page.json()["next_cursor"]},
    )

    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 1
    assert second_page.json()["items"][0]["id"] != first_page.json()["items"][0]["id"]
