"""Schemas shared by all API routes: errors, health and readiness."""

from typing import Any, Literal

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    """The one error format used by every endpoint."""

    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"
    checks: dict[str, str]
    pgvector_version: str | None = None
