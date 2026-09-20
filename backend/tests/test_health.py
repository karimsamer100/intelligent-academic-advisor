import pytest

from app import __version__


@pytest.mark.parametrize("path", ["/health", "/api/v1/health"])
def test_health_returns_ok(client, path):
    response = client.get(path)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["service"]


def test_health_does_not_touch_the_database(client):
    # No DB override and no PostgreSQL required: liveness must always work.
    assert client.get("/health").status_code == 200


def test_request_id_header_is_generated(client):
    response = client.get("/health")
    assert len(response.headers["x-request-id"]) > 0


def test_valid_request_id_is_echoed_and_unsafe_one_replaced(client):
    ok = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert ok.headers["x-request-id"] == "abc-123"

    unsafe = client.get("/health", headers={"X-Request-ID": "bad id with spaces!"})
    assert unsafe.headers["x-request-id"] != "bad id with spaces!"


def test_openapi_docs_available_in_development(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_openapi_docs_disabled_in_production(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as prod_client:
            assert prod_client.get("/docs").status_code == 404
            assert prod_client.get("/openapi.json").status_code == 404
            assert prod_client.get("/health").status_code == 200
    finally:
        get_settings.cache_clear()


def test_cors_origins_come_from_environment(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("CORS_ORIGINS", "http://example.test")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as cors_client:
            allowed = cors_client.options(
                "/api/v1/health",
                headers={"Origin": "http://example.test", "Access-Control-Request-Method": "GET"},
            )
            assert allowed.headers.get("access-control-allow-origin") == "http://example.test"

            denied = cors_client.options(
                "/api/v1/health",
                headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "GET"},
            )
            assert "access-control-allow-origin" not in denied.headers
    finally:
        get_settings.cache_clear()
