from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://dtu:dtu@localhost:5432/dtu_courses"
    migration_database_url: str | None = None
    dtu_base_url: str = "https://kurser.dtu.dk"
    dtu_keyword_search_enabled: bool = True
    dtu_keyword_search_timeout: float = Field(default=3.0, gt=0, le=10)
    dtu_keyword_cache_ttl: int = Field(default=900, ge=0, le=3600)
    dtu_keyword_max_candidates: int = Field(default=2000, ge=1, le=10_000)
    default_academic_year: str = "2026-2027"
    import_request_delay: float = Field(default=0.5, ge=0)
    log_level: str = "INFO"
    embedding_api_key: str = Field(default="")
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dimensions: int = Field(default=1536, ge=1536, le=1536)
    embedding_timeout: float = Field(default=20.0, gt=0, le=60)
    embedding_batch_size: int = Field(default=50, ge=1, le=2048)
    semantic_course_search_enabled: bool = True
    semantic_course_min_similarity: float = Field(default=0.35, ge=-1, le=1)
    mcp_token: str = ""
    mcp_server_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
