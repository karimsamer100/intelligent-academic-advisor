import logging

from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.core.config import Settings
from app.core.exceptions import DatabaseUnavailableError, PgvectorUnavailableError
from app.repositories.health_repository import HealthRepository
from app.schemas.common import HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)


def build_liveness(settings: Settings) -> HealthResponse:
    """The process is up. Deliberately touches no infrastructure."""
    return HealthResponse(service=settings.app_name, version=__version__, environment=settings.app_env)


class HealthService:
    def __init__(self, repository: HealthRepository) -> None:
        self._repository = repository

    def check_readiness(self) -> ReadinessResponse:
        try:
            self._repository.ping()
            pgvector_version = self._repository.get_pgvector_version()
        except SQLAlchemyError as exc:
            logger.error(
                "database readiness check failed",
                extra={"error_type": type(exc).__name__, "detail": str(getattr(exc, "orig", exc))},
            )
            raise DatabaseUnavailableError() from exc

        if pgvector_version is None:
            logger.error("pgvector extension is not enabled; run `alembic upgrade head`")
            raise PgvectorUnavailableError()

        return ReadinessResponse(
            checks={"database": "ok", "pgvector": "ok"},
            pgvector_version=pgvector_version,
        )
