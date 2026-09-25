from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_ENV_KEYS = [
    "APP_ENV", "APP_NAME", "APP_HOST", "APP_PORT", "API_V1_PREFIX",
    "DATABASE_URL", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD",
    "POSTGRES_HOST", "POSTGRES_PORT", "RAG_TOP_K", "DOCUMENTS_PATH",
    "ACADEMIC_DATA_FOUNDATION_PATH", "EMBEDDING_MODEL", "EMBEDDING_DEVICE",
    "EMBEDDING_DIMENSION", "EMBEDDING_BATCH_SIZE", "EMBEDDING_CACHE_DIR",
    "CHUNK_SIZE", "CHUNK_OVERLAP", "CHUNK_MIN_CHARS", "RAG_MAX_TOP_K",
    "RAG_MIN_SCORE", "PIPELINE_VERSION", "PRESERVE_RAW_EXTRACTION",
    "RAW_EXTRACT_DIR",
    "LOG_LEVEL", "CORS_ORIGINS",
]  # fmt: skip


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Isolate from the developer's shell / container environment."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_defaults_are_sensible():
    settings = make_settings()
    assert settings.app_env == "development"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.rag_top_k == 5
    assert settings.academic_data_foundation_path is None
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.embedding_device == "cpu"
    assert settings.embedding_dimension == 1024
    assert settings.embedding_batch_size == 16
    assert settings.embedding_cache_dir is None
    assert settings.chunk_size == 1400
    assert settings.chunk_overlap == 180
    assert settings.chunk_min_chars == 80
    assert settings.rag_max_top_k == 20
    assert settings.rag_min_score is None
    assert settings.pipeline_version == "rag-v0.1.0"
    assert settings.preserve_raw_extraction is True
    assert settings.raw_extract_dir == Path("../data/rag_debug/extracted")
    assert settings.log_level == "INFO"
    assert settings.docs_enabled is True


def test_values_are_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("APP_NAME", "Advisor Test")
    monkeypatch.setenv("APP_PORT", "9001")
    monkeypatch.setenv("RAG_TOP_K", "8")
    monkeypatch.setenv("DOCUMENTS_PATH", "/tmp/docs")
    monkeypatch.setenv("LOG_LEVEL", "debug")

    settings = make_settings()
    assert settings.app_env == "staging"
    assert settings.app_name == "Advisor Test"
    assert settings.app_port == 9001
    assert settings.rag_top_k == 8
    assert str(settings.documents_path) == "/tmp/docs"
    assert settings.log_level == "DEBUG"


def test_rag_values_are_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("ACADEMIC_DATA_FOUNDATION_PATH", "../data/academic")
    monkeypatch.setenv("EMBEDDING_MODEL", "test/model")
    monkeypatch.setenv("EMBEDDING_DEVICE", "cpu")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "384")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "4")
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", "../data/model-cache")
    monkeypatch.setenv("CHUNK_SIZE", "900")
    monkeypatch.setenv("CHUNK_OVERLAP", "100")
    monkeypatch.setenv("CHUNK_MIN_CHARS", "40")
    monkeypatch.setenv("RAG_TOP_K", "7")
    monkeypatch.setenv("RAG_MAX_TOP_K", "12")
    monkeypatch.setenv("RAG_MIN_SCORE", "0.3")
    monkeypatch.setenv("PIPELINE_VERSION", "rag-test")
    monkeypatch.setenv("PRESERVE_RAW_EXTRACTION", "false")
    monkeypatch.setenv("RAW_EXTRACT_DIR", "../data/rag-debug")

    settings = make_settings()

    assert settings.academic_data_foundation_path == Path("../data/academic")
    assert settings.embedding_model == "test/model"
    assert settings.embedding_dimension == 384
    assert settings.embedding_batch_size == 4
    assert settings.embedding_cache_dir == Path("../data/model-cache")
    assert (settings.chunk_size, settings.chunk_overlap, settings.chunk_min_chars) == (900, 100, 40)
    assert (settings.rag_top_k, settings.rag_max_top_k) == (7, 12)
    assert settings.rag_min_score == pytest.approx(0.3)
    assert settings.pipeline_version == "rag-test"
    assert settings.preserve_raw_extraction is False
    assert settings.raw_extract_dir == Path("../data/rag-debug")


def test_blank_rag_min_score_becomes_none():
    assert make_settings(rag_min_score="").rag_min_score is None
    assert make_settings(rag_min_score="   ").rag_min_score is None


def test_database_url_is_built_from_postgres_parts_with_escaping(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "advisor_db")
    monkeypatch.setenv("POSTGRES_USER", "advisor_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss/w:rd")
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "5433")

    url = make_settings().sqlalchemy_url
    assert url.drivername == "postgresql+psycopg"
    assert (url.username, url.password) == ("advisor_user", "p@ss/w:rd")
    assert (url.host, url.port, url.database) == ("db.internal", 5433, "advisor_db")


def test_explicit_database_url_wins(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:pw@example.test:5432/other")
    monkeypatch.setenv("POSTGRES_HOST", "ignored")

    url = make_settings().sqlalchemy_url
    assert url.host == "example.test"
    assert url.database == "other"


def test_blank_database_url_falls_back_to_postgres_parts(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("POSTGRES_HOST", "postgres")

    settings = make_settings()
    assert settings.database_url is None
    assert settings.sqlalchemy_url.host == "postgres"


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_plain_postgres_schemes_are_normalised_to_psycopg(monkeypatch, scheme):
    monkeypatch.setenv("DATABASE_URL", f"{scheme}://u:pw@localhost/db")
    assert make_settings().sqlalchemy_url.drivername == "postgresql+psycopg"


def test_redacted_database_url_hides_the_password(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:supersecret@localhost/db")
    redacted = make_settings().redacted_database_url
    assert "supersecret" not in redacted
    assert "***" in redacted


def test_password_is_not_exposed_by_repr(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "supersecret")
    assert "supersecret" not in repr(make_settings())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://a.test,http://b.test", ["http://a.test", "http://b.test"]),
        (" http://a.test , ,http://b.test ", ["http://a.test", "http://b.test"]),
        ('["http://a.test", "http://b.test"]', ["http://a.test", "http://b.test"]),
        ("", []),
    ],
)
def test_cors_origins_parsing(raw, expected):
    assert make_settings(cors_origins=raw).cors_origin_list == expected


@pytest.mark.parametrize(
    "bad",
    [
        {"rag_top_k": 0},
        {"rag_max_top_k": 0},
        {"embedding_dimension": 0},
        {"embedding_batch_size": 0},
        {"chunk_size": 0},
        {"chunk_overlap": -1},
        {"chunk_min_chars": 0},
        {"log_level": "LOUD"},
        {"api_v1_prefix": "api/v1"},
        {"api_v1_prefix": "/api/v1/"},
        {"app_port": 0},
    ],
)
def test_invalid_values_are_rejected(bad):
    with pytest.raises(ValidationError):
        make_settings(**bad)


@pytest.mark.parametrize(
    "bad",
    [
        {"chunk_size": 1400, "chunk_overlap": 1400},
        {"rag_top_k": 21, "rag_max_top_k": 20},
    ],
)
def test_rag_ranges_are_rejected(bad):
    with pytest.raises(ValidationError):
        make_settings(**bad)


def test_docs_are_disabled_in_production():
    assert make_settings(app_env="production").docs_enabled is False
