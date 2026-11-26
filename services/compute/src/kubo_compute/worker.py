import json
import logging
import time
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

import docker
import pika
from fastapi import HTTPException
from pika.spec import BasicProperties
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from kubo_compute.broker import RabbitMQ
from kubo_compute.catalog import ComputeProfile
from kubo_compute.config import get_settings
from kubo_compute.database import SessionLocal
from kubo_compute.iam_client import IAMClient
from kubo_compute.models import (
    ComputeOperation,
    ComputeResource,
    ObservedState,
    OperationAction,
    OutboxEvent,
    utcnow,
)
from kubo_compute.providers import ComputeProvider, DockerProvider, ProviderError, ProviderFailureCode
from kubo_compute.retries import (
    claim_operation_attempt,
    record_operation_failure,
    record_operation_success,
)

logger = logging.getLogger(__name__)
WORKER_RECONNECT_SECONDS = 5


class OperationExecutionError(RuntimeError):
    def __init__(self, code: str, safe_message: str, retryable: bool) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable


class InvalidWorkMessage(ValueError):
    pass


def process_operation(
    session: Session,
    operation_id: UUID,
    provider: ComputeProvider,
    iam: IAMClient,
    now: datetime | None = None,
) -> bool:
    attempted_at = now or utcnow()
    operation = claim_operation_attempt(session, operation_id, attempted_at)
    if operation is None:
        session.commit()
        return False
    session.commit()

    resource = session.get(ComputeResource, operation.compute_id)
    if resource is None:
        raise RuntimeError("Compute operation references a missing resource.")

    try:
        iam.authorize(
            operation.organization_id,
            operation.initiated_by,
            f"compute:{operation.action}",
        )
        _execute(operation, resource, provider, session)
    except OperationExecutionError as exc:
        _record_failure(session, operation, resource, attempted_at, exc.code, exc.safe_message, exc.retryable)
        return False
    except ProviderError as exc:
        retryable = exc.code in {
            ProviderFailureCode.DOCKER_UNAVAILABLE,
            ProviderFailureCode.IMAGE_PULL_FAILED,
            ProviderFailureCode.CONTAINER_INSPECT_FAILED,
            ProviderFailureCode.CONTAINER_START_FAILED,
            ProviderFailureCode.CONTAINER_STOP_FAILED,
            ProviderFailureCode.CONTAINER_DELETE_FAILED,
        }
        _record_failure(session, operation, resource, attempted_at, exc.code.value, str(exc), retryable)
        return False
    except HTTPException as exc:
        retryable = exc.status_code == 503
        code = "iam_unavailable" if retryable else "actor_not_authorized"
        message = (
            "IAM authorization is unavailable."
            if retryable
            else "The initiating user is no longer authorized for this operation."
        )
        _record_failure(session, operation, resource, attempted_at, code, message, retryable)
        return False

    final_states = {
        OperationAction.CREATE.value: ObservedState.RUNNING.value,
        OperationAction.START.value: ObservedState.RUNNING.value,
        OperationAction.STOP.value: ObservedState.STOPPED.value,
        OperationAction.DELETE.value: ObservedState.TERMINATED.value,
    }
    resource.observed_state = final_states[operation.action]
    resource.updated_at = attempted_at
    record_operation_success(operation, attempted_at)
    session.commit()
    return True


def _execute(
    operation: ComputeOperation,
    resource: ComputeResource,
    provider: ComputeProvider,
    session: Session,
) -> None:
    expected_desired_state = {
        OperationAction.CREATE.value: "running",
        OperationAction.START.value: "running",
        OperationAction.STOP.value: "stopped",
        OperationAction.DELETE.value: "terminated",
    }[operation.action]
    if resource.desired_state != expected_desired_state:
        raise OperationExecutionError(
            "desired_state_changed",
            "The compute's desired state changed before this operation ran.",
            retryable=False,
        )

    if operation.action == OperationAction.CREATE.value and resource.ports:
        raise OperationExecutionError(
            "network_attachment_unavailable",
            "Requested network attachments cannot be provisioned by this worker.",
            retryable=False,
        )

    if operation.action == OperationAction.CREATE.value:
        resource.observed_state = ObservedState.PROVISIONING.value
        resource.updated_at = utcnow()
        session.commit()
        if resource.provider_resource_id is None:
            profile = ComputeProfile(
                cpu_millicores=resource.cpu_millicores,
                memory_bytes=resource.memory_bytes,
                ephemeral_storage_bytes=resource.ephemeral_storage_bytes,
            )
            resource.provider_resource_id = provider.create(
                resource.id,
                resource.image_reference,
                profile,
            )
            session.commit()
        container = provider.inspect(resource.provider_resource_id)
        if container.status != "running":
            provider.start(resource.provider_resource_id)
        return

    if operation.action == OperationAction.DELETE.value:
        if resource.provider_resource_id is not None:
            provider.delete(resource.provider_resource_id)
            resource.provider_resource_id = None
        return

    if resource.provider_resource_id is None:
        raise OperationExecutionError(
            "provider_resource_missing",
            "The compute provider resource is unavailable.",
            retryable=False,
        )
    container = provider.inspect(resource.provider_resource_id)
    if operation.action == OperationAction.START.value:
        if container.status != "running":
            provider.start(resource.provider_resource_id)
        return
    if operation.action == OperationAction.STOP.value:
        if container.status == "running":
            provider.stop(resource.provider_resource_id)
        elif container.status != "exited":
            raise OperationExecutionError(
                "provider_state_unexpected",
                "The compute provider reported an unexpected container state.",
                retryable=False,
            )
        return
    raise OperationExecutionError(
        "operation_action_unsupported",
        "The compute operation is not supported by this worker.",
        retryable=False,
    )


def _record_failure(
    session: Session,
    operation: ComputeOperation,
    resource: ComputeResource,
    now: datetime,
    error_code: str,
    safe_message: str,
    retryable: bool,
) -> None:
    retry_scheduled = record_operation_failure(
        operation,
        now,
        error_code=error_code,
        safe_message=safe_message,
        retryable=retryable,
    )
    if retry_scheduled:
        event = session.scalar(
            select(OutboxEvent).where(OutboxEvent.operation_id == operation.id)
        )
        if event is not None:
            event.published_at = None
            event.next_attempt_at = operation.next_attempt_at
    else:
        resource.observed_state = ObservedState.FAILED.value
        resource.updated_at = now
    session.commit()


def parse_operation_message(body: bytes, properties: BasicProperties) -> UUID:
    try:
        value = json.loads(body)
        if (
            not isinstance(value, dict)
            or set(value) != {"operation_id"}
            or properties.type != "compute.operation.requested"
        ):
            raise ValueError("Invalid message envelope.")
        operation_id = UUID(value["operation_id"])
        if properties.message_id and UUID(properties.message_id) != operation_id:
            raise ValueError("Message identifier does not match the operation.")
        return operation_id
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise InvalidWorkMessage("Invalid Compute work message.") from exc


def make_message_handler(
    session_factory: sessionmaker,
    provider: ComputeProvider,
    iam: IAMClient,
) -> Callable:
    def handle(channel, method, properties: BasicProperties, body: bytes) -> None:
        try:
            operation_id = parse_operation_message(body, properties)
        except InvalidWorkMessage:
            logger.error("Rejected malformed Compute work message.")
            channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
            return

        try:
            with session_factory() as session:
                process_operation(session, operation_id, provider, iam)
        except SQLAlchemyError:
            logger.error("Compute database unavailable while processing work; requeuing message.")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return
        channel.basic_ack(delivery_tag=method.delivery_tag)

    return handle


def run() -> None:
    settings = get_settings()
    if not settings.worker_service_token:
        raise RuntimeError("Compute worker IAM service token is not configured.")
    docker_client = docker.from_env()
    provider = DockerProvider(docker_client)
    iam = IAMClient(
        settings.iam_url,
        settings.worker_service_token,
        service_id="compute-worker",
    )
    handler = make_message_handler(SessionLocal, provider, iam)
    try:
        while True:
            try:
                with RabbitMQ(settings.broker_url, settings.broker_queue) as broker:
                    broker.consume(handler)
            except (pika.exceptions.AMQPError, OSError):
                logger.error("RabbitMQ worker unavailable; reconnecting.")
                time.sleep(WORKER_RECONNECT_SECONDS)
    finally:
        iam.close()
        docker_client.close()
