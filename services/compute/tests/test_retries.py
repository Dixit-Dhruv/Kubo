from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from kubo_compute.catalog import ComputeProfile
from kubo_compute.models import ComputeOperation, OperationAction, OperationStatus, OutboxEvent
from kubo_compute.operations import accept_create
from kubo_compute.retries import (
    MAX_OPERATION_ATTEMPTS,
    claim_operation_attempt,
    record_operation_failure,
    record_outbox_publish_failure,
    retry_delay,
)
from kubo_compute.schemas import ComputeCreateRequest

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


def test_operation_attempt_claim_is_atomic_and_retries_with_capped_backoff(compute_session):
    accepted = accept_create(
        session=compute_session,
        organization_id=UUID("089b3a23-afb4-4a6d-819a-5e7fdbac0084"),
        actor_id=UUID("8c07034d-15ae-46cb-846b-fdb9911e637b"),
        idempotency_key="request-1",
        request=ComputeCreateRequest(name="web", image="approved-web", profile="small"),
        image_reference="registry.example.com/kubo/web@sha256:" + ("a" * 64),
        profile=ComputeProfile(
            cpu_millicores=500,
            memory_bytes=536870912,
            ephemeral_storage_bytes=1073741824,
        ),
        now=NOW,
    )
    compute_session.commit()

    first_attempt = claim_operation_attempt(compute_session, accepted.operation.id, NOW)
    assert first_attempt is not None
    assert first_attempt.status == OperationStatus.RUNNING.value
    assert first_attempt.attempt_count == 1
    compute_session.commit()
    assert claim_operation_attempt(compute_session, accepted.operation.id, NOW) is None

    assert record_operation_failure(
        first_attempt,
        NOW,
        error_code="provider_unavailable",
        safe_message="Compute provider is unavailable.",
        retryable=True,
    )
    assert first_attempt.status == OperationStatus.ACCEPTED.value
    assert first_attempt.next_attempt_at == NOW + timedelta(seconds=1)
    compute_session.commit()

    assert claim_operation_attempt(compute_session, accepted.operation.id, NOW) is None
    second_attempt = claim_operation_attempt(
        compute_session,
        accepted.operation.id,
        NOW + timedelta(seconds=1),
    )
    assert second_attempt is not None
    assert second_attempt.attempt_count == 2


def test_operation_failure_after_max_attempts_is_terminal():
    operation = ComputeOperation(
        id=uuid4(),
        organization_id=uuid4(),
        compute_id=uuid4(),
        initiated_by=uuid4(),
        action=OperationAction.CREATE.value,
        status=OperationStatus.RUNNING.value,
        idempotency_key="request-1",
        request_hash="a" * 64,
        attempt_count=MAX_OPERATION_ATTEMPTS,
        next_attempt_at=NOW,
    )

    retry_scheduled = record_operation_failure(
        operation,
        NOW,
        error_code="provider_failed",
        safe_message="Compute provider could not complete the operation.",
        retryable=True,
    )

    assert retry_scheduled is False
    assert operation.status == OperationStatus.FAILED.value
    assert operation.last_error_code == "provider_failed"


def test_outbox_retries_indefinitely_with_exponential_delay_capped_at_sixty_seconds():
    event = OutboxEvent(
        id=uuid4(),
        operation_id=uuid4(),
        event_type="compute.operation.requested",
        payload={"operation_id": str(uuid4())},
        publish_attempts=0,
        next_attempt_at=NOW,
        created_at=NOW,
    )

    expected_delays = [1, 2, 4, 8, 16, 32, 60, 60]
    for delay in expected_delays:
        record_outbox_publish_failure(event, NOW)
        assert event.next_attempt_at == NOW + timedelta(seconds=delay)

    assert event.publish_attempts == len(expected_delays)
    assert event.last_error_code == "broker_publish_failed"
    assert retry_delay(10_000) == timedelta(seconds=60)
