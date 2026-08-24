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
    groq_api_key: str = Field(default="")
    groq_model: str = Field(default="openai/gpt-oss-120b")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1")
    groq_temperature: float = Field(default=0.0)
    semantic_resolution_enabled: bool = True
    semantic_resolution_min_confidence: float = Field(default=0.85, ge=0, le=1)
    semantic_resolution_timeout: float = Field(default=10.0, gt=0, le=30)
    semantic_intent_enabled: bool = True
    semantic_intent_min_confidence: float = Field(default=0.85, ge=0, le=1)
    semantic_intent_timeout: float = Field(default=10.0, gt=0, le=30)
    mcp_token: str = ""
    mcp_server_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
