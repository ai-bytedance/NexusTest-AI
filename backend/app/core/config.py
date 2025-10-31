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
    token_rotation_grace_seconds: int = 300
    sso_state_ttl_seconds: int = 600
    feishu_client_id: str | None = None
    feishu_client_secret: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_scopes: List[str] = ["openid", "profile", "email"]
    database_url: str
    redis_url: str
    uvicorn_workers: int = 2
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    provider: str = "mock"
    ai_chat_rate_limit_per_minute: int = 30
    ai_chat_message_max_bytes: int = 16000
    algorithm: str = "HS256"
    request_timeout_seconds: int = 30
    max_response_size_bytes: int = 512_000
    report_export_max_bytes: int = 5_242_880
    pdf_engine: str = "weasyprint"
    report_export_font_path: str | None = None
    report_export_branding_logo: str | None = None
    report_export_branding_title: str = "Test Execution Report"
    report_export_branding_footer: str | None = None
    report_export_branding_company: str | None = None
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
    analytics_window: int = 50
    cluster_min_count: int = 2
    notify_max_retries: int = 3
    notify_backoff_seconds: int = 5
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_from_name: str | None = None
    smtp_tls: bool = True
    sendgrid_api_key: str | None = None
    mailgun_api_key: str | None = None
    feishu_signing_secret: str | None = None
    slack_default_channel: str | None = None
    redact_fields: List[str] = ["authorization", "password", "token", "secret"]
    redaction_placeholder: str = "***"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str | None = None
    anthropic_base_url: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-20240620"
    google_api_key: str | None = None
    google_base_url: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    qwen_api_key: str | None = None
    qwen_base_url: str | None = None
    qwen_model: str = "qwen-plus"
    zhipu_api_key: str | None = None
    zhipu_base_url: str | None = None
    glm_model: str = "glm-4-airx"
    doubao_api_key: str | None = None
    doubao_base_url: str | None = None
    doubao_model: str = "doubao-pro-4k"
    metrics_enabled: bool = False
    metrics_namespace: str = "nexustest"
    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9464
    celery_metrics_port: int = 9540
    celery_metrics_poll_interval_seconds: int = 15
    agent_health_check_seconds: int = 60
    agent_heartbeat_rate_limit_per_minute: int = 60
    agent_offline_threshold_seconds: int = 120
    agent_backlog_threshold: int = 25
    agent_latency_threshold_ms: int = 1000
    otel_trace_propagation_enabled: bool = False
    health_check_timeout_seconds: float = 2.0
    celery_worker_concurrency: int = 4
    celery_worker_prefetch_multiplier: int = 1
    celery_visibility_timeout_seconds: int = 3600
    celery_task_acks_late: bool = True
    celery_task_reject_on_worker_lost: bool = True
    backup_base_dir: str = "./storage/backups"
    backup_keep_daily: int = 7
    backup_keep_weekly: int = 4
    backup_keep_monthly: int = 12
    backup_s3_bucket: str | None = None
    backup_s3_prefix: str = ""
    backup_s3_region: str | None = None
    backup_s3_endpoint_url: str | None = None
    backup_s3_access_key: str | None = None
    backup_s3_secret_key: str | None = None
    backup_s3_use_ssl: bool = True
    backup_encrypt: bool = False
    backup_gpg_recipient: str | None = None
    backup_gpg_public_key_path: str | None = None
    backup_verify_every_n_days: int = 7
    backup_verify_target_url: str | None = None
    backup_job_cron: str = "0 2 * * *"
    retention_job_cron: str = "0 3 * * *"
    report_retention_days: int = 30
    ai_task_retention_days: int = 30
    audit_log_retention_days: int = 90
    report_archive_dir: str | None = None
    report_archive_s3_bucket: str | None = None
    report_archive_s3_prefix: str = ""
    report_archive_min_bytes: int = 262144
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

    @field_validator(
        "plan_refresh_seconds",
        "notify_backoff_seconds",
        "celery_visibility_timeout_seconds",
        "celery_metrics_poll_interval_seconds",
        "agent_health_check_seconds",
        "agent_offline_threshold_seconds",
        "sso_state_ttl_seconds",
        mode="before",
    )
    @classmethod
    def validate_positive_seconds(cls, value: int | str) -> int:
        int_value = int(value) if isinstance(value, str) else value
        if int_value <= 0:
            raise ValueError("Value must be greater than zero")
        return int_value

    @field_validator(
        "celery_worker_prefetch_multiplier",
        "celery_worker_concurrency",
        "httpx_retry_attempts",
        "ai_chat_rate_limit_per_minute",
        "ai_chat_message_max_bytes",
        "report_export_max_bytes",
        "metrics_port",
        "celery_metrics_port",
        "analytics_window",
        "cluster_min_count",
        "backup_keep_daily",
        "backup_keep_weekly",
        "backup_keep_monthly",
        "backup_verify_every_n_days",
        "report_retention_days",
        "ai_task_retention_days",
        "audit_log_retention_days",
        "agent_backlog_threshold",
        "agent_latency_threshold_ms",
        "agent_heartbeat_rate_limit_per_minute",
        "report_archive_min_bytes",
        "smtp_port",
        mode="before",
    )
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

    @field_validator("oidc_scopes", mode="before")
    @classmethod
    def parse_oidc_scopes(cls, value: List[str] | str | None) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [scope.strip() for scope in value if isinstance(scope, str) and scope.strip()]
        if isinstance(value, str):
            return [scope.strip() for scope in value.split(",") if scope.strip()]
        raise ValueError("Invalid format for OIDC_SCOPES")

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

    @field_validator(
        "report_export_font_path",
        "report_export_branding_logo",
        "report_export_branding_footer",
        "report_export_branding_company",
        mode="before",
    )
    @classmethod
    def normalize_optional_branding(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("report_export_branding_title", mode="before")
    @classmethod
    def normalize_branding_title(cls, value: str | None) -> str:
        if value is None:
            return "Test Execution Report"
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("REPORT_EXPORT_BRANDING_TITLE cannot be empty")
        return normalized

    @field_validator("pdf_engine", mode="before")
    @classmethod
    def normalize_pdf_engine(cls, value: str | None) -> str:
        engine = str(value or "weasyprint").strip().lower()
        if engine not in {"weasyprint", "wkhtml"}:
            raise ValueError("PDF_ENGINE must be either 'weasyprint' or 'wkhtml'")
        return engine

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

    @field_validator("metrics_host", mode="before")
    @classmethod
    def normalize_metrics_host(cls, value: str | None) -> str:
        if value is None:
            return "0.0.0.0"
        host = value.strip()
        if not host:
            raise ValueError("METRICS_HOST cannot be empty")
        return host

    @field_validator("backup_base_dir", mode="before")
    @classmethod
    def normalize_backup_base_dir(cls, value: str | None) -> str:
        base_dir = str(value or "").strip()
        if not base_dir:
            raise ValueError("BACKUP_BASE_DIR cannot be empty")
        return base_dir

    @field_validator("report_archive_dir", mode="before")
    @classmethod
    def normalize_report_archive_dir(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("backup_s3_prefix", "report_archive_s3_prefix", mode="before")
    @classmethod
    def normalize_storage_prefix(cls, value: str | None) -> str:
        if value is None:
            return ""
        prefix = str(value).strip().replace("\\", "/")
        prefix = prefix.lstrip("/")
        if not prefix:
            return ""
        if not prefix.endswith("/"):
            prefix = f"{prefix}/"
        return prefix


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]
