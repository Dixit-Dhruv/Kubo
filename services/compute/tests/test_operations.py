from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select

from kubo_compute.catalog import ComputeProfile
from kubo_compute.models import ComputeOperation, ComputeResource, OutboxEvent
from kubo_compute.operations import IdempotencyConflict, accept_create
from kubo_compute.schemas import ComputeCreateRequest

ORGANIZATION_ID = UUID("089b3a23-afb4-4a6d-819a-5e7fdbac0084")
ACTOR_ID = UUID("8c07034d-15ae-46cb-846b-fdb9911e637b")
OTHER_ACTOR_ID = UUID("633a8d75-4bf8-4e31-b6c1-3a5bbd706b0f")
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
PROFILE = ComputeProfile(
    cpu_millicores=500,
    memory_bytes=536870912,
    ephemeral_storage_bytes=1073741824,
)


def create_request(name: str = "web") -> ComputeCreateRequest:
    return ComputeCreateRequest(name=name, image="approved-web", profile="small")


def accept(session, actor_id: UUID, request: ComputeCreateRequest, key: str = "request-1"):
    return accept_create(
        session=session,
        organization_id=ORGANIZATION_ID,
        actor_id=actor_id,
        idempotency_key=key,
        request=request,
        image_reference="registry.example.com/kubo/web@sha256:" + ("a" * 64),
        profile=PROFILE,
        now=NOW,
    )


def test_create_persists_resource_operation_and_outbox_together(compute_session):
    accepted = accept(compute_session, ACTOR_ID, create_request())

    assert accepted.replayed is False
    assert accepted.resource.desired_state == "running"
    assert accepted.resource.observed_state == "requested"
    assert accepted.resource.cpu_millicores == PROFILE.cpu_millicores
    assert accepted.resource.ephemeral_storage_bytes == PROFILE.ephemeral_storage_bytes
    assert accepted.operation.status == "accepted"
    assert accepted.operation.initiated_by == ACTOR_ID
    assert accepted.operation.outbox_event is not None
    assert accepted.operation.outbox_event.payload == {"operation_id": str(accepted.operation.id)}
    assert compute_session.scalar(select(func.count()).select_from(ComputeResource)) == 1
    assert compute_session.scalar(select(func.count()).select_from(ComputeOperation)) == 1
    assert compute_session.scalar(select(func.count()).select_from(OutboxEvent)) == 1


def test_same_idempotency_key_and_request_replays_original_acceptance(compute_session):
    request = create_request()
    initial = accept(compute_session, ACTOR_ID, request)
    replay = accept_create(
        session=compute_session,
        organization_id=ORGANIZATION_ID,
        actor_id=ACTOR_ID,
        idempotency_key="request-1",
        request=request,
        image_reference="registry.example.com/kubo/web@sha256:" + ("b" * 64),
        profile=ComputeProfile(
            cpu_millicores=1000,
            memory_bytes=1073741824,
            ephemeral_storage_bytes=2147483648,
        ),
        now=NOW,
    )

    assert replay.replayed is True
    assert replay.resource.id == initial.resource.id
    assert replay.operation.id == initial.operation.id
    assert replay.resource.image_reference == initial.resource.image_reference
    assert replay.resource.cpu_millicores == PROFILE.cpu_millicores
    assert compute_session.scalar(select(func.count()).select_from(ComputeResource)) == 1


def test_reusing_idempotency_key_for_different_request_conflicts(compute_session):
    accept(compute_session, ACTOR_ID, create_request())

    with pytest.raises(IdempotencyConflict):
        accept(compute_session, ACTOR_ID, create_request("other"))

    assert compute_session.scalar(select(func.count()).select_from(ComputeResource)) == 1


def test_idempotency_key_is_scoped_to_organization_and_actor(compute_session):
    first = accept(compute_session, ACTOR_ID, create_request())
    second = accept(compute_session, OTHER_ACTOR_ID, create_request())

    assert first.operation.id != second.operation.id
    assert compute_session.scalar(select(func.count()).select_from(ComputeResource)) == 2


@pytest.mark.parametrize("key", ["", "x" * 129, "non-ascii-\u2603", "has space"])
def test_rejects_invalid_idempotency_key(compute_session, key):
    with pytest.raises(ValueError, match="Idempotency-Key"):
        accept(compute_session, ACTOR_ID, create_request(), key)
