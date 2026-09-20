import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture()
def app() -> FastAPI:
    get_settings.cache_clear()
    return create_app()


@pytest.fixture()
def client(app: FastAPI):
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def db_engine():
    """Engine for a real PostgreSQL. Integration tests skip when it is unreachable.

    Set REQUIRE_DB_TESTS=1 (e.g. in CI) to turn the skip into a failure.
    """
    get_settings.cache_clear()
    engine = create_engine(get_settings().sqlalchemy_url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        message = f"PostgreSQL is not reachable ({type(exc).__name__}); start it with `docker compose up -d postgres`"
        if os.getenv("REQUIRE_DB_TESTS") == "1":
            pytest.fail(message)
        pytest.skip(message)
    yield engine
    engine.dispose()
