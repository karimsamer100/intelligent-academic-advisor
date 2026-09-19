from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_health_service
from app.core.config import Settings, get_settings
from app.schemas.common import ErrorResponse, HealthResponse, ReadinessResponse
from app.services.health_service import HealthService, build_liveness

# Mounted at the application root:  GET /health
root_router = APIRouter(tags=["health"])
# Mounted under the API prefix:     GET /api/v1/health, GET /api/v1/ready
router = APIRouter(tags=["health"])


@root_router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def root_health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return build_liveness(settings)


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return build_liveness(settings)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe (PostgreSQL + pgvector)",
    responses={503: {"model": ErrorResponse, "description": "A required dependency is unavailable"}},
)
def ready(service: Annotated[HealthService, Depends(get_health_service)]) -> ReadinessResponse:
    return service.check_readiness()
