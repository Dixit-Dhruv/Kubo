from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


class ServiceAuthorizationRequest(BaseModel):
    scope: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9]*(?::[a-z][a-z0-9_-]*)*$",
    )


class ServiceAuthorizationResponse(BaseModel):
    service_id: str


class ComputeAuthorizationRequest(BaseModel):
    organization_id: UUID
    user_id: UUID
    action: Literal[
        "compute:read",
        "compute:create",
        "compute:start",
        "compute:stop",
        "compute:delete",
    ]


class ComputeAuthorizationResponse(BaseModel):
    authorized: Literal[True] = True


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    is_platform_admin: bool
    created_at: datetime


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Organization name cannot be blank.")
        return value


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    role: str
    created_at: datetime


class MembershipUpsert(BaseModel):
    user_id: UUID
    role: Literal["admin", "member"]


class MemberResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    role: str
    created_at: datetime
