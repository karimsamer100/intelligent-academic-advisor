"""Single typed configuration layer.

Every setting is read here, once. The rest of the codebase must call
``get_settings()`` instead of touching ``os.getenv`` / ``os.environ``.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

# backend/app/core/config.py -> parents[3] is the repository root.
# Real environment variables always win over values in a .env file.
_REPO_ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

_VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT_ENV_FILE, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- application -------------------------------------------------------
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_name: str = "Local Intelligent Academic Advisor"
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, ge=1, le=65535)
    api_v1_prefix: str = "/api/v1"

    # --- database ----------------------------------------------------------
    # DATABASE_URL wins when set. Otherwise the URL is built from POSTGRES_*.
    database_url: str | None = None
    postgres_db: str = "advisor"
    postgres_user: str = "advisor"
    postgres_password: SecretStr | None = None
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)

    # --- RAG ---------------------------------------------------------------
    rag_top_k: int = Field(default=5, gt=0)
    documents_path: Path = Path("./data/documents")

    # --- logging / http ----------------------------------------------------
    log_level: str = "INFO"
    # Comma-separated list (or a JSON list) of allowed origins.
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # --- validators --------------------------------------------------------
    @field_validator("database_url", mode="before")
    @classmethod
    def _blank_database_url_is_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("api_v1_prefix")
    @classmethod
    def _validate_prefix(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("/") or (len(value) > 1 and value.endswith("/")):
            raise ValueError("API_V1_PREFIX must start with '/' and must not end with '/'")
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in _VALID_LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(_VALID_LOG_LEVELS)}")
        return level

    # --- derived values ----------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def docs_enabled(self) -> bool:
        """OpenAPI docs are on everywhere except production."""
        return not self.is_production

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(o).strip() for o in parsed if str(o).strip()]
            except json.JSONDecodeError:
                pass
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> URL:
        """SQLAlchemy URL (psycopg 3 driver) for the main PostgreSQL database."""
        if self.database_url:
            url = make_url(self.database_url)
            if url.drivername in {"postgres", "postgresql"}:
                url = url.set(drivername="postgresql+psycopg")
            return url
        password = self.postgres_password.get_secret_value() if self.postgres_password else None
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=password or None,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def redacted_database_url(self) -> str:
        """Database URL that is safe to log (password masked)."""
        return self.sqlalchemy_url.render_as_string(hide_password=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
