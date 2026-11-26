from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KUBO_COMPUTE_", extra="ignore")

    database_url: str = "sqlite:///./compute.db"
    iam_url: str = "http://localhost:8001"
    service_token: str = ""
    image_catalog_path: Path = Path("config/images.json")
    profile_catalog_path: Path = Path("config/profiles.json")


@lru_cache
def get_settings() -> Settings:
    return Settings()
