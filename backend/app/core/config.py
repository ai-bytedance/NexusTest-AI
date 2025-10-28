from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    secret_key: str = "replace_me"
    access_token_expire_minutes: int = 60
    database_url: str
    redis_url: str
    uvicorn_workers: int = 2
    cors_origins: List[str] = ["*"]
    provider: str = "mock"
    algorithm: str = "HS256"
    request_timeout_seconds: int = 30
    max_response_size_bytes: int = 512_000
    redact_fields: List[str] = ["authorization", "password", "token", "secret"]
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    anthropic_api_key: str | None = None
    anthropic_base_url: str | None = None
    google_api_key: str | None = None
    google_base_url: str | None = None
    qwen_api_key: str | None = None
    qwen_base_url: str | None = None
    zhipu_api_key: str | None = None
    zhipu_base_url: str | None = None
    doubao_api_key: str | None = None
    doubao_base_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=(".env", "/app/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: List[str] | str) -> List[str]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        raise ValueError("Invalid format for CORS_ORIGINS")

    @field_validator("redact_fields", mode="before")
    @classmethod
    def split_redact_fields(cls, value: List[str] | str | None) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [item.strip().lower() for item in value if isinstance(item, str) and item.strip()]
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        raise ValueError("Invalid format for REDACT_FIELDS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]
