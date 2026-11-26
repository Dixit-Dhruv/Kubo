import re
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

_IMAGE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_DIGEST_IMAGE_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[._:/-][a-z0-9]+)*@sha256:[a-f0-9]{64}$"
)


class ImageCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    images: dict[str, str] = Field(min_length=1)

    @field_validator("images")
    @classmethod
    def validate_images(cls, images: dict[str, str]) -> dict[str, str]:
        for key, reference in images.items():
            if not _IMAGE_KEY_PATTERN.fullmatch(key):
                raise ValueError(f"Invalid image catalog key: {key!r}.")
            if not _DIGEST_IMAGE_PATTERN.fullmatch(reference):
                raise ValueError(f"Image {key!r} must use a pinned sha256 digest.")
        return images

    @classmethod
    def load(cls, path: Path) -> Self:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def resolve(self, key: str) -> str | None:
        return self.images.get(key)


class ComputeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_millicores: int = Field(gt=0)
    memory_bytes: int = Field(gt=0)
    ephemeral_storage_bytes: int = Field(gt=0)


class ProfileCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profiles: dict[str, ComputeProfile] = Field(min_length=1)

    @field_validator("profiles")
    @classmethod
    def validate_profiles(cls, profiles: dict[str, ComputeProfile]) -> dict[str, ComputeProfile]:
        for key in profiles:
            if not _IMAGE_KEY_PATTERN.fullmatch(key):
                raise ValueError(f"Invalid profile catalog key: {key!r}.")
        return profiles

    @classmethod
    def load(cls, path: Path) -> Self:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def resolve(self, key: str) -> ComputeProfile | None:
        return self.profiles.get(key)
