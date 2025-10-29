from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    secret_key: str = "replace_me"
    secret_enc_key: str = ""
    dataset_storage_dir: str = "./storage/datasets"
    access_token_expire_minutes: int = 60
    token_clock_skew_seconds: int = 0
    database_url: str
    redis_url: str
    uvicorn_workers: int = 2
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    provider: str = "mock"
    algorithm: str = "HS256"
    request_timeout_seconds: int = 30
    max_response_size_bytes: int = 512_000
    httpx_connect_timeout: float = 5.0
    httpx_read_timeout: float = 30.0
    httpx_write_timeout: float = 30.0
    httpx_pool_timeout: float = 5.0
    httpx_keepalive_expiry: float = 30.0
    httpx_max_connections: int = 100
    httpx_max_keepalive_connections: int = 20
    httpx_retry_attempts: int = 3
    httpx_retry_backoff_factor: float = 0.5
    httpx_retry_statuses: List[int] = [429, 500, 502, 503, 504]
    httpx_retry_methods: List[str] = ["GET", "HEAD", "OPTIONS", "PUT", "DELETE", "POST", "PATCH"]
    plan_refresh_seconds: int = 30
    notify_max_retries: int = 3
    notify_backoff_seconds: int = 5
    feishu_signing_secret: str | None = None
    slack_default_channel: str | None = None
    redact_fields: List[str] = ["authorization", "password", "token", "secret"]
    redaction_placeholder: str = "***"
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
    metrics_enabled: bool = False
    metrics_namespace: str = "nexustest"
    health_check_timeout_seconds: float = 2.0
    celery_worker_concurrency: int = 4
    celery_worker_prefetch_multiplier: int = 1
    celery_visibility_timeout_seconds: int = 3600
    celery_task_acks_late: bool = True
    celery_task_reject_on_worker_lost: bool = True
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

    @field_validator("plan_refresh_seconds", "notify_backoff_seconds", "celery_visibility_timeout_seconds", mode="before")
    @classmethod
    def validate_positive_seconds(cls, value: int | str) -> int:
        int_value = int(value) if isinstance(value, str) else value
        if int_value <= 0:
            raise ValueError("Value must be greater than zero")
        return int_value

    @field_validator("celery_worker_prefetch_multiplier", "celery_worker_concurrency", "httpx_retry_attempts", mode="before")
    @classmethod
    def validate_positive_integers(cls, value: int | str) -> int:
        int_value = int(value) if isinstance(value, str) else value
        if int_value <= 0:
            raise ValueError("Value must be greater than zero")
        return int_value

    @field_validator("notify_max_retries", mode="before")
    @classmethod
    def validate_notify_retries(cls, value: int | str) -> int:
        int_value = int(value) if isinstance(value, str) else value
        if int_value < 0:
            raise ValueError("NOTIFY_MAX_RETRIES must be zero or a positive integer")
        return int_value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: List[str] | str | None) -> List[str]:
        if isinstance(value, list):
            origins = [origin.strip() for origin in value if isinstance(origin, str) and origin.strip()]
        elif isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        elif value is None:
            return []
        else:
            raise ValueError("Invalid format for CORS_ORIGINS")
        if "*" in origins and len(origins) > 1:
            raise ValueError("CORS_ORIGINS cannot include '*' alongside specific origins")
        return origins

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

    @field_validator("redaction_placeholder", mode="before")
    @classmethod
    def validate_redaction_placeholder(cls, value: str | None) -> str:
        if value is None:
            return "***"
        placeholder = value.strip()
        if not placeholder:
            raise ValueError("REDACTION_PLACEHOLDER cannot be empty")
        return placeholder

    @field_validator("httpx_retry_statuses", mode="before")
    @classmethod
    def parse_retry_statuses(cls, value: List[int] | List[str] | str | None) -> List[int]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, list):
            items = value
        else:
            raise ValueError("Invalid format for HTTPX_RETRY_STATUSES")
        statuses: list[int] = []
        seen: set[int] = set()
        for item in items:
            status = int(item)
            if status not in seen:
                seen.add(status)
                statuses.append(status)
        return statuses

    @field_validator("httpx_retry_methods", mode="before")
    @classmethod
    def parse_retry_methods(cls, value: List[str] | str | None) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
        elif isinstance(value, list):
            items = value
        else:
            raise ValueError("Invalid format for HTTPX_RETRY_METHODS")
        seen: set[str] = set()
        methods: list[str] = []
        for item in items:
            method = str(item).strip().upper()
            if not method or method in seen:
                continue
            seen.add(method)
            methods.append(method)
        return methods

    @field_validator("httpx_max_connections", "httpx_max_keepalive_connections", mode="before")
    @classmethod
    def validate_connection_limits(cls, value: int | str) -> int:
        int_value = int(value) if isinstance(value, str) else value
        if int_value <= 0:
            raise ValueError("HTTPX connection limits must be greater than zero")
        return int_value

    @field_validator(
        "httpx_connect_timeout",
        "httpx_read_timeout",
        "httpx_write_timeout",
        "httpx_pool_timeout",
        "httpx_keepalive_expiry",
        "httpx_retry_backoff_factor",
        "health_check_timeout_seconds",
        mode="before",
    )
    @classmethod
    def validate_positive_float(cls, value: float | str) -> float:
        float_value = float(value) if isinstance(value, str) else value
        if float_value <= 0:
            raise ValueError("Value must be greater than zero")
        return float_value

    @field_validator("metrics_namespace", mode="before")
    @classmethod
    def normalize_metrics_namespace(cls, value: str | None) -> str:
        if value is None:
            return "nexustest"
        namespace = value.strip()
        if not namespace:
            raise ValueError("METRICS_NAMESPACE cannot be empty")
        return namespace


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]
