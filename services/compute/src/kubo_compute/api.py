import base64
import binascii
import json
from collections.abc import Callable, Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from kubo_compute.catalog import ImageCatalog, ProfileCatalog
from kubo_compute.config import Settings, get_settings
from kubo_compute.database import get_db
from kubo_compute.iam_client import IAMClient
from kubo_compute.models import ComputeOperation, ComputeResource, OperationAction
from kubo_compute.operations import (
    ComputeNotFound,
    IdempotencyConflict,
    LifecycleConflict,
    accept_create,
    accept_lifecycle,
)
from kubo_compute.schemas import (
    ComputeAcceptanceResponse,
    ComputeCreateRequest,
    ComputeListResponse,
    ComputeOperationResponse,
    ComputeResourceResponse,
)

router = APIRouter(prefix="/api/v1")
bearer_scheme = HTTPBearer(auto_error=False)
CatalogT = TypeVar("CatalogT")


def get_iam_client(settings: Settings = Depends(get_settings)) -> Generator[IAMClient, None, None]:
    client = IAMClient(settings.iam_url, settings.service_token)
    try:
        yield client
    finally:
        client.close()


def get_current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    iam: IAMClient = Depends(get_iam_client),
) -> UUID:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return iam.authenticate(credentials.credentials)


def get_image_catalog(settings: Settings = Depends(get_settings)) -> ImageCatalog:
    return _load_catalog(ImageCatalog.load, settings.image_catalog_path)


def get_profile_catalog(settings: Settings = Depends(get_settings)) -> ProfileCatalog:
    return _load_catalog(ProfileCatalog.load, settings.profile_catalog_path)


def _load_catalog(loader: Callable[[Path], CatalogT], path: Path) -> CatalogT:
    try:
        return loader(path)
    except (OSError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Compute catalog is unavailable.",
        ) from exc


def _resource_response(resource: ComputeResource) -> ComputeResourceResponse:
    return ComputeResourceResponse.model_validate(
        {
            "id": resource.id,
            "organization_id": resource.organization_id,
            "name": resource.name,
            "image": resource.image_key,
            "profile": resource.profile_key,
            "desired_state": resource.desired_state,
            "observed_state": resource.observed_state,
            "ports": resource.ports,
            "created_at": resource.created_at,
            "updated_at": resource.updated_at,
        }
    )


def _acceptance_response(resource: ComputeResource, operation: ComputeOperation) -> ComputeAcceptanceResponse:
    return ComputeAcceptanceResponse(
        resource=_resource_response(resource),
        operation=ComputeOperationResponse.model_validate(operation),
    )


def _validate_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        encoded = cursor.encode("ascii")
        payload = base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4))
        value = json.loads(payload)
        timestamp = datetime.fromisoformat(value["created_at"])
        resource_id = UUID(value["id"])
        if timestamp.tzinfo is None:
            raise ValueError("Cursor timestamp must include a timezone.")
        return timestamp, resource_id
    except (UnicodeEncodeError, binascii.Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid compute cursor.") from exc


def _encode_cursor(resource: ComputeResource) -> str:
    created_at = resource.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    payload = json.dumps(
        {"created_at": created_at.isoformat(), "id": str(resource.id)},
        separators=(",", ":"),
    ).encode("ascii")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


@router.post(
    "/organizations/{organization_id}/computes",
    response_model=ComputeAcceptanceResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_compute(
    organization_id: UUID,
    payload: ComputeCreateRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    session: Session = Depends(get_db),
    actor_id: UUID = Depends(get_current_actor),
    iam: IAMClient = Depends(get_iam_client),
    image_catalog: ImageCatalog = Depends(get_image_catalog),
    profile_catalog: ProfileCatalog = Depends(get_profile_catalog),
) -> ComputeAcceptanceResponse:
    iam.authorize(organization_id, actor_id, "compute:create")
    image_reference = image_catalog.resolve(payload.image)
    profile = profile_catalog.resolve(payload.profile)
    try:
        accepted = accept_create(
            session=session,
            organization_id=organization_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            request=payload,
            image_reference=image_reference,
            profile=profile,
        )
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable() from exc
    return _acceptance_response(accepted.resource, accepted.operation)


@router.get(
    "/organizations/{organization_id}/computes",
    response_model=ComputeListResponse,
)
def list_computes(
    organization_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    session: Session = Depends(get_db),
    actor_id: UUID = Depends(get_current_actor),
    iam: IAMClient = Depends(get_iam_client),
) -> ComputeListResponse:
    iam.authorize(organization_id, actor_id, "compute:read")
    statement = select(ComputeResource).where(
        ComputeResource.organization_id == organization_id,
    )
    if cursor:
        created_at, resource_id = _validate_cursor(cursor)
        statement = statement.where(
            or_(
                ComputeResource.created_at > created_at,
                (ComputeResource.created_at == created_at) & (ComputeResource.id > resource_id),
            )
        )
    statement = statement.order_by(ComputeResource.created_at, ComputeResource.id).limit(limit + 1)
    try:
        rows = list(session.scalars(statement))
    except SQLAlchemyError as exc:
        raise _database_unavailable() from exc
    has_more = len(rows) > limit
    items = rows[:limit]
    return ComputeListResponse(
        items=[_resource_response(resource) for resource in items],
        next_cursor=_encode_cursor(items[-1]) if has_more and items else None,
    )


@router.get(
    "/organizations/{organization_id}/computes/{compute_id}",
    response_model=ComputeResourceResponse,
)
def get_compute(
    organization_id: UUID,
    compute_id: UUID,
    session: Session = Depends(get_db),
    actor_id: UUID = Depends(get_current_actor),
    iam: IAMClient = Depends(get_iam_client),
) -> ComputeResourceResponse:
    iam.authorize(organization_id, actor_id, "compute:read")
    try:
        resource = session.scalar(
            select(ComputeResource).where(
                ComputeResource.organization_id == organization_id,
                ComputeResource.id == compute_id,
            )
        )
    except SQLAlchemyError as exc:
        raise _database_unavailable() from exc
    if resource is None:
        raise HTTPException(status_code=404, detail="Compute resource not found.")
    return _resource_response(resource)


def _request_lifecycle(
    organization_id: UUID,
    compute_id: UUID,
    action: OperationAction,
    idempotency_key: str,
    actor_id: UUID,
    iam: IAMClient,
    session: Session,
) -> ComputeAcceptanceResponse:
    iam.authorize(organization_id, actor_id, f"compute:{action.value}")
    try:
        accepted = accept_lifecycle(
            session=session,
            organization_id=organization_id,
            compute_id=compute_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            action=action,
        )
    except ComputeNotFound as exc:
        raise HTTPException(status_code=404, detail="Compute resource not found.") from exc
    except LifecycleConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable() from exc
    return _acceptance_response(accepted.resource, accepted.operation)


@router.post(
    "/organizations/{organization_id}/computes/{compute_id}/start",
    response_model=ComputeAcceptanceResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_compute(
    organization_id: UUID,
    compute_id: UUID,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    session: Session = Depends(get_db),
    actor_id: UUID = Depends(get_current_actor),
    iam: IAMClient = Depends(get_iam_client),
) -> ComputeAcceptanceResponse:
    return _request_lifecycle(
        organization_id, compute_id, OperationAction.START, idempotency_key, actor_id, iam, session
    )


@router.post(
    "/organizations/{organization_id}/computes/{compute_id}/stop",
    response_model=ComputeAcceptanceResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def stop_compute(
    organization_id: UUID,
    compute_id: UUID,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    session: Session = Depends(get_db),
    actor_id: UUID = Depends(get_current_actor),
    iam: IAMClient = Depends(get_iam_client),
) -> ComputeAcceptanceResponse:
    return _request_lifecycle(
        organization_id, compute_id, OperationAction.STOP, idempotency_key, actor_id, iam, session
    )


@router.delete(
    "/organizations/{organization_id}/computes/{compute_id}",
    response_model=ComputeAcceptanceResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def delete_compute(
    organization_id: UUID,
    compute_id: UUID,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    session: Session = Depends(get_db),
    actor_id: UUID = Depends(get_current_actor),
    iam: IAMClient = Depends(get_iam_client),
) -> ComputeAcceptanceResponse:
    return _request_lifecycle(
        organization_id, compute_id, OperationAction.DELETE, idempotency_key, actor_id, iam, session
    )


@router.get(
    "/organizations/{organization_id}/operations/{operation_id}",
    response_model=ComputeOperationResponse,
)
def get_operation(
    organization_id: UUID,
    operation_id: UUID,
    session: Session = Depends(get_db),
    actor_id: UUID = Depends(get_current_actor),
    iam: IAMClient = Depends(get_iam_client),
) -> ComputeOperationResponse:
    iam.authorize(organization_id, actor_id, "compute:read")
    try:
        operation = session.scalar(
            select(ComputeOperation).where(
                ComputeOperation.organization_id == organization_id,
                ComputeOperation.id == operation_id,
            )
        )
    except SQLAlchemyError as exc:
        raise _database_unavailable() from exc
    if operation is None:
        raise HTTPException(status_code=404, detail="Compute operation not found.")
    return ComputeOperationResponse.model_validate(operation)


def _database_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Compute database is unavailable.",
    )
