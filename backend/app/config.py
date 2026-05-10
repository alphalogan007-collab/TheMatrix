"""
MindAI Backend Configuration
All settings loaded from environment variables via pydantic-settings.
No secrets are hardcoded here. See .env.example for reference.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(str, Enum):
    MOCK = "mock"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------------------------------------------------------------------------
    # Application
    # ---------------------------------------------------------------------------
    app_env: Environment = Environment.DEVELOPMENT
    app_name: str = "MindAI"
    app_version: str = "0.1.0"
    debug: bool = False
    secret_key: str = Field(..., min_length=32)

    # ---------------------------------------------------------------------------
    # API
    # ---------------------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://localhost:8000"
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8081",
        "http://localhost:8082",
        "http://localhost:8083",
        "http://localhost:8084",
        "http://localhost:8085",
        "http://192.168.2.20:8081",
        "http://192.168.2.20:8082",
        "http://192.168.2.20:8083",
        "http://192.168.2.20:8084",
    ]

    # ---------------------------------------------------------------------------
    # Database
    # ---------------------------------------------------------------------------
    database_url: str = Field(default="")

    @field_validator("database_url", mode="before")
    @classmethod
    def fix_database_url(cls, v: str) -> str:
        """Render (and other cloud providers) give postgresql:// but asyncpg needs postgresql+asyncpg://"""
        if not v:
            return v
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    # ---------------------------------------------------------------------------
    # Redis
    # ---------------------------------------------------------------------------
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ---------------------------------------------------------------------------
    # JWT
    # ---------------------------------------------------------------------------
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # ---------------------------------------------------------------------------
    # Password
    # ---------------------------------------------------------------------------
    password_hash_algorithm: str = "argon2id"

    # ---------------------------------------------------------------------------
    # Rate Limiting
    # ---------------------------------------------------------------------------
    rate_limit_login_per_minute: int = 5
    rate_limit_api_per_minute: int = 60
    rate_limit_advisor_per_minute: int = 10
    rate_limit_screen_per_minute: int = 5

    # ---------------------------------------------------------------------------
    # LLM Providers
    # ---------------------------------------------------------------------------
    use_mock_llm: bool = True
    llm_provider: LLMProvider = LLMProvider.MOCK
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""       # Free tier — 14,400 req/day — https://console.groq.com
    gemini_api_key: str = ""     # Free tier — 1,500 req/day  — https://aistudio.google.com
    llm_model: str = "gpt-4o"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.3

    # ---------------------------------------------------------------------------
    # Embedding / Search / OCR / Speech
    # ---------------------------------------------------------------------------
    use_mock_embedding: bool = True
    embedding_provider: str = "mock"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    use_mock_search: bool = True
    search_provider: str = "mock"

    use_mock_ocr: bool = True
    ocr_provider: str = "mock"

    use_mock_speech: bool = True
    speech_provider: str = "mock"

    # ---------------------------------------------------------------------------
    # Encryption
    # ---------------------------------------------------------------------------
    field_encryption_key: str = ""
    use_kms: bool = False
    kms_key_id: str = ""

    # ---------------------------------------------------------------------------
    # Blueprint
    # ---------------------------------------------------------------------------
    blueprint_signing_key: str = ""
    blueprint_signing_algorithm: str = "HS256"  # TODO: use RS256 in production

    # ---------------------------------------------------------------------------
    # Social Media — Facebook Graph API
    # ---------------------------------------------------------------------------
    facebook_app_id: str = ""        # Create at developers.facebook.com → My Apps
    facebook_app_secret: str = ""    # Settings → Basic → App Secret
    # User access token stored encrypted in founder_identity_mind — not here

    # ---------------------------------------------------------------------------
    # Admin seed (DEV ONLY)
    # ---------------------------------------------------------------------------
    dev_admin_email: str = "admin@mindai.local"
    dev_admin_password: str = ""

    # ---------------------------------------------------------------------------
    # Observability
    # ---------------------------------------------------------------------------
    log_level: str = "INFO"
    enable_opentelemetry: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    sentry_dsn: str = ""

    # ---------------------------------------------------------------------------
    # Storage
    # ---------------------------------------------------------------------------
    storage_backend: Literal["local", "s3", "gcs"] = "local"
    storage_local_path: str = "./data/uploads"

    # ---------------------------------------------------------------------------
    # Privacy defaults
    # ---------------------------------------------------------------------------
    default_allow_memory: bool = False
    default_allow_screen_guardian: bool = False
    default_allow_voice_processing: bool = False
    default_allow_anonymized_training: bool = False
    default_allow_sensitive_session_storage: bool = False

    # ---------------------------------------------------------------------------
    # Payload limits
    # ---------------------------------------------------------------------------
    max_text_input_chars: int = 10_000
    max_transcript_chars: int = 50_000
    max_screenshot_bytes: int = 10 * 1024 * 1024  # 10 MB

    @field_validator("debug")
    @classmethod
    def debug_must_be_false_in_production(cls, v: bool, info: object) -> bool:
        # We check at runtime in main.py as well; this is belt-and-suspenders.
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.app_env == Environment.DEVELOPMENT


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance. Use as FastAPI dependency."""
    return Settings()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Runtime overrides — mutable in-memory layer on top of env-based settings.
# Allows updating keys like openai_api_key without restarting the server.
# ---------------------------------------------------------------------------

_runtime_overrides: dict[str, object] = {}


def apply_runtime_override(key: str, value: object) -> None:
    """Set a runtime override. The override takes precedence over env config."""
    _runtime_overrides[key] = value
    # If the key maps to a Settings field, patch the cached instance too
    cached = get_settings()
    if hasattr(cached, key):
        object.__setattr__(cached, key, value)
        # Auto-flip mock flags based on key presence
        if key == "openai_api_key":
            mock_off = bool(value)
            object.__setattr__(cached, "use_mock_llm", not mock_off)
        elif key in ("groq_api_key", "gemini_api_key") and value:
            # Any free-tier key also disables mock mode
            object.__setattr__(cached, "use_mock_llm", False)


def get_runtime_overrides() -> dict[str, object]:
    """Return current runtime overrides (for display in admin UI)."""
    return dict(_runtime_overrides)
