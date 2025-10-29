from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    secret_key: str = "replace_me"
    access_token_expire_minutes: int = 60
    token_clock_skew_seconds: int = 0
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
    app_version: str = "0.1.0"
    git_commit_sha: str = "unknown"
    build_time: str = ""

    model_config = SettingsConfigDict(
        env_file=(".env", "/app/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("access_token_expire_minutes", mode="before")
    @classmethod
    def validate_access_token_expiry(cls, value: int | str) -> int:
        int_value = int(value) if isinstance(value, str) else value
        if int_value <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be greater than zero")
        return int_value

    @field_validator("token_clock_skew_seconds", mode="before")
    @classmethod
    def validate_clock_skew(cls, value: int | str) -> int:
        int_value = int(value) if isinstance(value, str) else value
        if int_value < 0:
            raise ValueError("TOKEN_CLOCK_SKEW_SECONDS must be zero or a positive integer")
        return int_value

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
