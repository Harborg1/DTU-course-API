from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://dtu:dtu@localhost:5432/dtu_courses"
    migration_database_url: str | None = None
    api_key: str = Field(min_length=1)
    dtu_base_url: str = "https://kurser.dtu.dk"
    default_academic_year: str = "2026-2027"
    import_request_delay: float = Field(default=0.5, ge=0)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
