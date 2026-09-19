import json
import logging

from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, RequestContextFilter, request_path_ctx


def _assert_standard_error(body: dict, code: str) -> None:
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code


def test_unknown_route_uses_the_standard_error_format(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    _assert_standard_error(response.json(), "NOT_FOUND")


def test_wrong_method_uses_the_standard_error_format(client):
    response = client.post("/health")
    assert response.status_code == 405
    _assert_standard_error(response.json(), "METHOD_NOT_ALLOWED")


def test_malformed_json_uses_the_standard_error_format(client):
    response = client.post("/api/v1/rag/search", content="{not json", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    _assert_standard_error(response.json(), "VALIDATION_ERROR")


def test_unhandled_exception_never_leaks_details(app):
    def _boom():
        raise RuntimeError("secret internal detail")

    app.add_api_route("/_boom", _boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/_boom")

    assert response.status_code == 500
    _assert_standard_error(response.json(), "INTERNAL_SERVER_ERROR")
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text
    assert response.headers.get("x-request-id")


# ---- logging ---------------------------------------------------------------
def _record(message="hello", **extra) -> logging.LogRecord:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, message, (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_log_line_has_the_required_fields():
    record = _record(extra_field="x")
    RequestContextFilter().filter(record)
    line = json.loads(JsonFormatter().format(record))

    assert line["level"] == "INFO"
    assert line["module"] == "app.test"
    assert line["message"] == "hello"
    assert line["extra_field"] == "x"
    assert line["timestamp"].endswith("+00:00")


def test_json_log_line_includes_the_request_path():
    token = request_path_ctx.set("/api/v1/ready")
    try:
        record = _record()
        RequestContextFilter().filter(record)
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_path_ctx.reset(token)
    assert line["request_path"] == "/api/v1/ready"


def test_json_log_line_includes_exception_traceback_for_the_server_log():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord("app.test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    line = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in line["exception"]
