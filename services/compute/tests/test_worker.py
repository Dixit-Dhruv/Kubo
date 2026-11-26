import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import HTTPException
from pika import BasicProperties

from kubo_compute.catalog import ComputeProfile
from kubo_compute.models import ComputeOperation, ComputeResource, OperationAction, OutboxEvent
from kubo_compute.operations import accept_create, accept_lifecycle
from kubo_compute.providers import (
    ContainerState,
    ProviderError,
    ProviderFailureCode,
)
from kubo_compute.retries import MAX_OPERATION_ATTEMPTS, OPERATION_LEASE, claim_operation_attempt
from kubo_compute.schemas import ComputeCreateRequest
from kubo_compute.worker import InvalidWorkMessage, parse_operation_message, process_operation

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
ORGANIZATION_ID = UUID("089b3a23-afb4-4a6d-819a-5e7fdbac0084")
ACTOR_ID = UUID("8c07034d-15ae-46cb-846b-fdb9911e637b")
PROFILE = ComputeProfile(
    cpu_millicores=500,
    memory_bytes=536870912,
    ephemeral_storage_bytes=1073741824,
)


class FakeIAM:
    def __init__(self, error: HTTPException | None = None) -> None:
        self.error = error
        self.actions = []

    def authorize(self, organization_id, user_id, action):
        assert organization_id == ORGANIZATION_ID
        assert user_id == ACTOR_ID
        self.actions.append(action)
        if self.error is not None:
            raise self.error


class FakeProvider:
    def __init__(self, error: ProviderError | None = None) -> None:
        self.error = error
        self.created = []
        self.create_calls = 0
        self.started = []
        self.stopped = []
        self.deleted = []
        self.status = "created"

    def create(self, compute_id, image_reference, profile):
        self.create_calls += 1
        if self.error:
            raise self.error
        self.created.append((compute_id, image_reference, profile))
        return "container-id"

    def inspect(self, container_id):
        if self.error:
            raise self.error
        return ContainerState(container_id=container_id, status=self.status, exit_code=None)

    def start(self, container_id):
        if self.error:
            raise self.error
        self.started.append(container_id)
        self.status = "running"

    def stop(self, container_id):
        if self.error:
            raise self.error
        self.stopped.append(container_id)
        self.status = "exited"

    def delete(self, container_id):
        if self.error:
            raise self.error
        self.deleted.append(container_id)


def accept(session, ports=None):
    return accept_create(
        session=session,
        organization_id=ORGANIZATION_ID,
        actor_id=ACTOR_ID,
        idempotency_key="worker-1",
        request=ComputeCreateRequest(
            name="web",
            image="approved-web",
            profile="small",
            ports=ports or [],
        ),
        image_reference="registry.example.com/kubo/web@sha256:" + ("a" * 64),
        profile=PROFILE,
        now=NOW,
    )


def test_worker_executes_and_completes_create_idempotently(compute_session):
    accepted = accept(compute_session)
    provider = FakeProvider()
    iam = FakeIAM()

    assert process_operation(compute_session, accepted.operation.id, provider, iam, now=NOW)
    assert not process_operation(compute_session, accepted.operation.id, provider, iam, now=NOW)

    compute_session.refresh(accepted.operation)
    compute_session.refresh(accepted.resource)
    assert accepted.operation.status == "succeeded"
    assert accepted.resource.observed_state == "running"
    assert accepted.resource.provider_resource_id == "container-id"
    assert len(provider.created) == 1
    assert provider.started == ["container-id"]
    assert iam.actions == ["compute:create"]


def test_worker_rechecks_actor_and_fails_nonretryably_on_revocation(compute_session):
    accepted = accept(compute_session)
    provider = FakeProvider()
    iam = FakeIAM(HTTPException(status_code=403, detail="forbidden"))

    assert not process_operation(compute_session, accepted.operation.id, provider, iam, now=NOW)

    compute_session.refresh(accepted.operation)
    compute_session.refresh(accepted.resource)
    assert accepted.operation.status == "failed"
    assert accepted.operation.last_error_code == "actor_not_authorized"
    assert accepted.resource.observed_state == "failed"
    assert provider.created == []


def test_retryable_provider_failure_requeues_outbox_at_operation_due_time(compute_session):
    accepted = accept(compute_session)
    provider = FakeProvider(
        ProviderError(ProviderFailureCode.DOCKER_UNAVAILABLE, "safe provider error")
    )

    assert not process_operation(compute_session, accepted.operation.id, provider, FakeIAM(), now=NOW)

    compute_session.refresh(accepted.operation)
    compute_session.refresh(accepted.operation.outbox_event)
    assert accepted.operation.status == "accepted"
    assert accepted.operation.next_attempt_at.replace(tzinfo=UTC) == NOW + timedelta(seconds=1)
    assert accepted.operation.outbox_event.published_at is None
    assert (
        accepted.operation.outbox_event.next_attempt_at.replace(tzinfo=UTC)
        == accepted.operation.next_attempt_at.replace(tzinfo=UTC)
    )


def test_worker_stops_resource_and_persists_success(compute_session):
    accepted = accept(compute_session)
    accepted.resource.observed_state = "running"
    accepted.resource.provider_resource_id = "container-id"
    compute_session.commit()
    stopped = accept_lifecycle(
        session=compute_session,
        organization_id=ORGANIZATION_ID,
        compute_id=accepted.resource.id,
        actor_id=ACTOR_ID,
        idempotency_key="stop-1",
        action=OperationAction.STOP,
        now=NOW,
    )
    provider = FakeProvider()
    provider.status = "running"

    assert process_operation(compute_session, stopped.operation.id, provider, FakeIAM(), now=NOW)

    compute_session.refresh(stopped.resource)
    assert stopped.operation.status == "succeeded"
    assert stopped.resource.observed_state == "stopped"
    assert provider.stopped == ["container-id"]


def test_worker_stops_after_five_total_attempts(compute_session):
    accepted = accept(compute_session)
    provider = FakeProvider(
        ProviderError(ProviderFailureCode.DOCKER_UNAVAILABLE, "safe provider error")
    )
    attempt_times = [0, 1, 3, 7, 15]

    for delay in attempt_times:
        result = process_operation(
            compute_session,
            accepted.operation.id,
            provider,
            FakeIAM(),
            now=NOW + timedelta(seconds=delay),
        )
        assert result is False

    compute_session.refresh(accepted.operation)
    compute_session.refresh(accepted.resource)
    assert accepted.operation.attempt_count == MAX_OPERATION_ATTEMPTS
    assert accepted.operation.status == "failed"
    assert accepted.resource.observed_state == "failed"
    assert provider.create_calls == MAX_OPERATION_ATTEMPTS


def test_create_with_requested_ports_fails_without_claiming_running(compute_session):
    accepted = accept(
        compute_session,
        ports=[{"container_port": 8080, "protocol": "tcp"}],
    )
    provider = FakeProvider()

    assert not process_operation(compute_session, accepted.operation.id, provider, FakeIAM(), now=NOW)

    compute_session.refresh(accepted.operation)
    compute_session.refresh(accepted.resource)
    assert accepted.operation.status == "failed"
    assert accepted.operation.last_error_code == "network_attachment_unavailable"
    assert accepted.resource.observed_state == "failed"
    assert provider.created == []


def test_expired_worker_lease_can_be_reclaimed(compute_session):
    accepted = accept(compute_session)
    accepted.operation.status = "running"
    accepted.operation.attempt_count = 1
    accepted.operation.updated_at = NOW - OPERATION_LEASE - timedelta(seconds=1)
    compute_session.commit()

    reclaimed = claim_operation_attempt(compute_session, accepted.operation.id, NOW)

    assert reclaimed is not None
    assert reclaimed.status == "running"
    assert reclaimed.attempt_count == 2


def test_expired_last_attempt_is_failed_and_resource_marked_failed(compute_session):
    accepted = accept(compute_session)
    accepted.operation.status = "running"
    accepted.operation.attempt_count = MAX_OPERATION_ATTEMPTS
    accepted.operation.updated_at = NOW - OPERATION_LEASE - timedelta(seconds=1)
    compute_session.commit()

    claimed = claim_operation_attempt(compute_session, accepted.operation.id, NOW)

    compute_session.refresh(accepted.operation)
    compute_session.refresh(accepted.resource)
    assert claimed is None
    assert accepted.operation.status == "failed"
    assert accepted.operation.last_error_code == "worker_lease_expired"
    assert accepted.resource.observed_state == "failed"


def test_work_message_validates_event_and_operation_identifiers():
    operation_id = UUID("267a88a3-4ad0-49da-b41f-1aa708f8329e")
    properties = BasicProperties(type="compute.operation.requested", message_id=str(operation_id))

    assert parse_operation_message(
        json.dumps({"operation_id": str(operation_id)}).encode(),
        properties,
    ) == operation_id
    with pytest.raises(InvalidWorkMessage):
        parse_operation_message(
            json.dumps({"operation_id": str(operation_id), "unexpected": True}).encode(),
            properties,
        )
