from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central typed configuration for the backend and RAG pipeline."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: str = "development"
    app_name: str = "Local Intelligent Academic Advisor"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # PostgreSQL / pgvector
    database_url: str = "postgresql+psycopg://advisor:advisor@localhost:5432/advisor"
    postgres_db: str = "advisor"
    postgres_user: str = "advisor"
    postgres_password: str = "advisor"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Academic source data
    documents_path: Path = Path("../data/documents")
    academic_data_foundation_path: Path | None = None

    # Local embeddings
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"
    embedding_dimension: int = 1024
    embedding_batch_size: int = 16
    embedding_cache_dir: Path | None = None

    # Chunking
    chunk_size: int = 1400
    chunk_overlap: int = 180
    chunk_min_chars: int = 80

    # Retrieval
    rag_top_k: int = 5
    rag_max_top_k: int = 20
    rag_min_score: float | None = None

    # Pipeline
    pipeline_version: str = "rag-v0.1.0"
    raw_extract_dir: Path = Path("../data/rag_debug/extracted")
    preserve_raw_extraction: bool = True

    @field_validator(
        "app_port",
        "postgres_port",
        "embedding_dimension",
        "embedding_batch_size",
        "chunk_size",
        "chunk_min_chars",
        "rag_top_k",
        "rag_max_top_k",
    )
    @classmethod
    def positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value

    @field_validator("rag_min_score", mode="before")
    @classmethod
    def blank_score_is_none(cls, value):
        if value is None or value == "":
            return None
        return value

    @field_validator("chunk_overlap")
    @classmethod
    def valid_overlap(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must be >= 0")
        return value

    @field_validator("api_v1_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("/"):
            value = "/" + value
        return value.rstrip("/") or "/api/v1"

    @field_validator("cors_origins")
    @classmethod
    def normalize_cors_origins(cls, value: list[str]) -> list[str]:
        return [origin.strip().rstrip("/") for origin in value if origin.strip()]

    def validate_chunking(self) -> None:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.rag_top_k > self.rag_max_top_k:
            raise ValueError("RAG_TOP_K must be <= RAG_MAX_TOP_K")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_chunking()
    return settings
