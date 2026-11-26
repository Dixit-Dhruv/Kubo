from typing import Literal

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
