"""Readiness endpoint: real-DB tests are marked `integration`."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_health_service
from app.db.session import get_db
from app.services.health_service import HealthService


class _FakeRepository:
    """Stand-in for the DB layer, used only to exercise service branches."""

    def __init__(self, pgvector_version):
        self._version = pgvector_version

    def ping(self):
        return None

    def get_pgvector_version(self):
        return self._version


def test_ready_returns_503_when_database_is_unreachable(app, client):
    # Nothing listens on port 1, so the real repository hits a real connection error.
    engine = create_engine(
        "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none",
        connect_args={"connect_timeout": 1},
    )
    factory = sessionmaker(bind=engine)

    def _unreachable_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _unreachable_db
    response = client.get("/api/v1/ready")
    engine.dispose()

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "DATABASE_UNAVAILABLE",
            "message": "Database connection is unavailable",
            "details": None,
        }
    }
    assert "Traceback" not in response.text
    assert "nothing" not in response.text  # credentials never leak


def test_ready_returns_503_when_pgvector_is_missing(app, client):
    app.dependency_overrides[get_health_service] = lambda: HealthService(_FakeRepository(None))
    response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PGVECTOR_UNAVAILABLE"


def test_ready_returns_200_when_everything_is_available(app, client):
    app.dependency_overrides[get_health_service] = lambda: HealthService(_FakeRepository("0.8.0"))
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "pgvector": "ok"},
        "pgvector_version": "0.8.0",
    }


@pytest.mark.integration
def test_ready_against_real_postgres(client, db_engine):
    response = client.get("/api/v1/ready")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["checks"] == {"database": "ok", "pgvector": "ok"}
    assert body["pgvector_version"]
