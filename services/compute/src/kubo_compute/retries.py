from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from kubo_compute.models import ComputeOperation, ComputeResource, OperationStatus, OutboxEvent

MAX_OPERATION_ATTEMPTS = 5
MAX_RETRY_DELAY_SECONDS = 60
OPERATION_LEASE = timedelta(minutes=5)


def retry_delay(attempt_number: int) -> timedelta:
    if attempt_number < 1:
        raise ValueError("Attempt number must be positive.")
    exponent = min(attempt_number - 1, 6)
    return timedelta(seconds=min(2**exponent, MAX_RETRY_DELAY_SECONDS))


def claim_operation_attempt(
    session: Session,
    operation_id: UUID,
    now: datetime,
) -> ComputeOperation | None:
    stale_before = now - OPERATION_LEASE
    exhausted = session.execute(
        update(ComputeOperation)
        .where(
            ComputeOperation.id == operation_id,
            ComputeOperation.status == OperationStatus.RUNNING.value,
            ComputeOperation.updated_at <= stale_before,
            ComputeOperation.attempt_count >= MAX_OPERATION_ATTEMPTS,
        )
        .values(
            status=OperationStatus.FAILED.value,
            last_error_code="worker_lease_expired",
            last_error_message="Compute worker stopped before completing the operation.",
            updated_at=now,
            next_attempt_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if exhausted.rowcount == 1:
        session.execute(
            update(ComputeResource)
            .where(
                ComputeResource.id
                == select(ComputeOperation.compute_id)
                .where(ComputeOperation.id == operation_id)
                .scalar_subquery()
            )
            .values(observed_state="failed", updated_at=now)
        )
        session.expire_all()
        return None

    result = session.execute(
        update(ComputeOperation)
        .where(
            ComputeOperation.id == operation_id,
            (
                (
                    (ComputeOperation.status == OperationStatus.ACCEPTED.value)
                    & (ComputeOperation.next_attempt_at <= now)
                )
                | (
                    (ComputeOperation.status == OperationStatus.RUNNING.value)
                    & (ComputeOperation.updated_at <= stale_before)
                )
            ),
            ComputeOperation.attempt_count < MAX_OPERATION_ATTEMPTS,
        )
        .values(
            status=OperationStatus.RUNNING.value,
            attempt_count=ComputeOperation.attempt_count + 1,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        return None
    session.expire_all()
    return session.get(ComputeOperation, operation_id)


def record_operation_failure(
    operation: ComputeOperation,
    now: datetime,
    error_code: str,
    safe_message: str,
    retryable: bool,
) -> bool:
    if operation.status != OperationStatus.RUNNING.value:
        raise ValueError("Only running operations can record execution failures.")

    operation.last_error_code = error_code
    operation.last_error_message = safe_message
    operation.updated_at = now
    if retryable and operation.attempt_count < MAX_OPERATION_ATTEMPTS:
        operation.status = OperationStatus.ACCEPTED.value
        operation.next_attempt_at = now + retry_delay(operation.attempt_count)
        return True

    operation.status = OperationStatus.FAILED.value
    operation.next_attempt_at = now
    return False


def record_operation_success(operation: ComputeOperation, now: datetime) -> None:
    if operation.status != OperationStatus.RUNNING.value:
        raise ValueError("Only running operations can be marked successful.")
    operation.status = OperationStatus.SUCCEEDED.value
    operation.last_error_code = None
    operation.last_error_message = None
    operation.updated_at = now
    operation.next_attempt_at = now


def record_outbox_publish_failure(event: OutboxEvent, now: datetime) -> None:
    event.publish_attempts += 1
    event.last_error_code = "broker_publish_failed"
    event.next_attempt_at = now + retry_delay(event.publish_attempts)
