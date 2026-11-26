from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KUBO_COMPUTE_", extra="ignore")

    database_url: str = "sqlite:///./compute.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
