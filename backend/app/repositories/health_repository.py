"""Infrastructure queries used by the readiness check."""

from sqlalchemy import text
from sqlalchemy.orm import Session


class HealthRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def ping(self) -> None:
        """Raises a SQLAlchemyError if PostgreSQL cannot be reached."""
        self._db.execute(text("SELECT 1"))

    def get_pgvector_version(self) -> str | None:
        """Installed pgvector version, or None if the extension is not enabled."""
        result = self._db.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
        return result.scalar_one_or_none()
