from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PortRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    container_port: int = Field(ge=1, le=65535)
    protocol: Literal["tcp", "udp"]


class ComputeCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    image: str = Field(min_length=1, max_length=64)
    profile: str = Field(min_length=1, max_length=64)
    ports: list[PortRequest] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Compute name cannot be blank.")
        return value


class ComputeResourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    image: str
    profile: str
    desired_state: str
    observed_state: str
    ports: list[dict[str, int | str]]
    created_at: datetime
    updated_at: datetime


class ComputeOperationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    compute_id: UUID
    action: str
    status: str
    last_error_code: str | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime


class ComputeAcceptanceResponse(BaseModel):
    resource: ComputeResourceResponse
    operation: ComputeOperationResponse


class ComputeListResponse(BaseModel):
    items: list[ComputeResourceResponse]
    next_cursor: str | None
