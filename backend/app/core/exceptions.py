"""Application errors and the central exception handlers.

All errors leave the API in one shape::

    {"error": {"code": "...", "message": "...", "details": null}}

Raw exception messages and stack traces are logged, never returned.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for expected, client-safe application errors."""

    status_code: int = 500
    code: str = "INTERNAL_SERVER_ERROR"
    message: str = "An unexpected error occurred"

    def __init__(self, message: str | None = None, *, details: Any | None = None) -> None:
        self.message = message or self.message
        self.details = details
        super().__init__(self.message)


class DatabaseUnavailableError(AppError):
    status_code = 503
    code = "DATABASE_UNAVAILABLE"
    message = "Database connection is unavailable"


class PgvectorUnavailableError(AppError):
    status_code = 503
    code = "PGVECTOR_UNAVAILABLE"
    message = "The pgvector extension is not enabled in the database"


class RAGNotConfiguredError(AppError):
    status_code = 501
    code = "RAG_NOT_CONFIGURED"
    message = "No RAG retriever is configured yet"


_HTTP_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
}


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"), headers=headers)


def _request_context(request: Request) -> dict[str, Any]:
    return {
        "request_path": request.url.path,
        "request_id": getattr(request.state, "request_id", None),
    }


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    log = logger.error if exc.status_code >= 500 else logger.warning
    log(exc.message, extra={"error_code": exc.code, **_request_context(request)})
    return _error_response(exc.status_code, exc.code, exc.message, exc.details)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Only location / message / type are returned. The submitted input is
    # deliberately dropped: it may contain student data.
    details = [
        {"loc": list(err.get("loc", ())), "message": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    logger.warning("request validation failed", extra={"error_count": len(details), **_request_context(request)})
    return _error_response(422, "VALIDATION_ERROR", "Request validation failed", details)


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_STATUS_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return _error_response(exc.status_code, code, message, headers=exc.headers)


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Full traceback goes to the log only.
    logger.exception("unhandled exception", extra=_request_context(request))
    headers = {}
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        headers["X-Request-ID"] = request_id
    return _error_response(500, "INTERNAL_SERVER_ERROR", "An unexpected error occurred", headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected_error)
