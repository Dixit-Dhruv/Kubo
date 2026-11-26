import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kubo_compute.catalog import ComputeProfile
from kubo_compute.models import (
    ComputeOperation,
    ComputeResource,
    DesiredState,
    ObservedState,
    OperationAction,
    OperationStatus,
    OutboxEvent,
    utcnow,
)
from kubo_compute.schemas import ComputeCreateRequest


class IdempotencyConflict(ValueError):
    pass


class LifecycleConflict(ValueError):
    pass


class ComputeNotFound(LookupError):
    pass


@dataclass(frozen=True)
class CreateAcceptance:
    resource: ComputeResource
    operation: ComputeOperation
    replayed: bool


def accept_create(
    session: Session,
    organization_id: UUID,
    actor_id: UUID,
    idempotency_key: str,
    request: ComputeCreateRequest,
    image_reference: str | None,
    profile: ComputeProfile | None,
    now: datetime | None = None,
) -> CreateAcceptance:
    _validate_idempotency_key(idempotency_key)
    request_hash = _hash_request(request)
    accepted_at = now or utcnow()
    try:
        with session.begin():
            existing = _find_operation(session, organization_id, actor_id, idempotency_key)
            if existing is not None:
                return _existing_acceptance(session, existing, request_hash)
            if image_reference is None or profile is None:
                raise ValueError("Unsupported image or profile.")

            resource = ComputeResource(
                id=uuid4(),
                organization_id=organization_id,
                name=request.name,
                image_key=request.image,
                image_reference=image_reference,
                profile_key=request.profile,
                cpu_millicores=profile.cpu_millicores,
                memory_bytes=profile.memory_bytes,
                ephemeral_storage_bytes=profile.ephemeral_storage_bytes,
                ports=[port.model_dump(mode="json") for port in request.ports],
                desired_state=DesiredState.RUNNING.value,
                observed_state=ObservedState.REQUESTED.value,
                created_at=accepted_at,
                updated_at=accepted_at,
            )
            operation = ComputeOperation(
                id=uuid4(),
                organization_id=organization_id,
                compute_id=resource.id,
                initiated_by=actor_id,
                action=OperationAction.CREATE.value,
                status=OperationStatus.ACCEPTED.value,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                attempt_count=0,
                next_attempt_at=accepted_at,
                created_at=accepted_at,
                updated_at=accepted_at,
            )
            outbox_event = OutboxEvent(
                id=uuid4(),
                operation_id=operation.id,
                event_type="compute.operation.requested",
                payload={"operation_id": str(operation.id)},
                next_attempt_at=accepted_at,
                created_at=accepted_at,
            )
            session.add_all((resource, operation, outbox_event))
            session.flush()
            return CreateAcceptance(resource=resource, operation=operation, replayed=False)
    except IntegrityError:
        session.rollback()
        existing = _find_operation(session, organization_id, actor_id, idempotency_key)
        if existing is None:
            raise
        return _existing_acceptance(session, existing, request_hash)


def accept_lifecycle(
    session: Session,
    organization_id: UUID,
    compute_id: UUID,
    actor_id: UUID,
    idempotency_key: str,
    action: OperationAction,
    now: datetime | None = None,
) -> CreateAcceptance:
    _validate_idempotency_key(idempotency_key)
    if action not in {OperationAction.START, OperationAction.STOP, OperationAction.DELETE}:
        raise ValueError("Lifecycle action must be start, stop, or delete.")

    request_hash = _hash_action(action.value, {"compute_id": str(compute_id)})
    accepted_at = now or utcnow()
    try:
        with session.begin():
            existing = _find_operation(session, organization_id, actor_id, idempotency_key)
            if existing is not None:
                return _existing_acceptance(session, existing, request_hash)

            resource = session.scalar(
                select(ComputeResource)
                .where(
                    ComputeResource.id == compute_id,
                    ComputeResource.organization_id == organization_id,
                )
                .with_for_update()
            )
            if resource is None:
                raise ComputeNotFound("Compute resource not found.")

            transition = {
                OperationAction.START: (
                    ObservedState.STOPPED.value,
                    DesiredState.RUNNING.value,
                    ObservedState.STARTING.value,
                ),
                OperationAction.STOP: (
                    ObservedState.RUNNING.value,
                    DesiredState.STOPPED.value,
                    ObservedState.STOPPING.value,
                ),
                OperationAction.DELETE: (
                    None,
                    DesiredState.TERMINATED.value,
                    ObservedState.TERMINATING.value,
                ),
            }[action]
            expected_state, desired_state, observed_state = transition
            if expected_state is not None and resource.observed_state != expected_state:
                raise LifecycleConflict(f"Cannot {action.value} a compute in state {resource.observed_state}.")
            if action is OperationAction.DELETE and resource.observed_state == ObservedState.TERMINATED.value:
                raise LifecycleConflict("Cannot delete a terminated compute.")

            resource.desired_state = desired_state
            resource.observed_state = observed_state
            resource.updated_at = accepted_at
            operation = ComputeOperation(
                id=uuid4(),
                organization_id=organization_id,
                compute_id=resource.id,
                initiated_by=actor_id,
                action=action.value,
                status=OperationStatus.ACCEPTED.value,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                attempt_count=0,
                next_attempt_at=accepted_at,
                created_at=accepted_at,
                updated_at=accepted_at,
            )
            outbox_event = OutboxEvent(
                id=uuid4(),
                operation_id=operation.id,
                event_type="compute.operation.requested",
                payload={"operation_id": str(operation.id)},
                next_attempt_at=accepted_at,
                created_at=accepted_at,
            )
            session.add_all((operation, outbox_event))
            session.flush()
            return CreateAcceptance(resource=resource, operation=operation, replayed=False)
    except IntegrityError:
        session.rollback()
        existing = _find_operation(session, organization_id, actor_id, idempotency_key)
        if existing is None:
            raise
        return _existing_acceptance(session, existing, request_hash)


def _find_operation(
    session: Session,
    organization_id: UUID,
    actor_id: UUID,
    idempotency_key: str,
) -> ComputeOperation | None:
    return session.scalar(
        select(ComputeOperation).where(
            ComputeOperation.organization_id == organization_id,
            ComputeOperation.initiated_by == actor_id,
            ComputeOperation.idempotency_key == idempotency_key,
        )
    )


def _existing_acceptance(
    session: Session,
    operation: ComputeOperation,
    request_hash: str,
) -> CreateAcceptance:
    if operation.request_hash != request_hash:
        raise IdempotencyConflict("Idempotency-Key was already used with a different request.")
    resource = session.get(ComputeResource, operation.compute_id)
    if resource is None:
        raise RuntimeError("Compute operation references a missing resource.")
    return CreateAcceptance(resource=resource, operation=operation, replayed=True)


def _hash_request(request: ComputeCreateRequest) -> str:
    return _hash_action("create", request.model_dump(mode="json"))


def _hash_action(action: str, body: dict[str, object]) -> str:
    canonical = json.dumps(
        {"action": f"compute:{action}", "body": body},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _validate_idempotency_key(idempotency_key: str) -> None:
    if not idempotency_key or len(idempotency_key) > 128 or not all(
        0x21 <= ord(character) <= 0x7E for character in idempotency_key
    ):
        raise ValueError("Idempotency-Key must be 1-128 visible ASCII characters.")
