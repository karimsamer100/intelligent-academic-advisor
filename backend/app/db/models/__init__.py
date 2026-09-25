"""Import ORM models so Alembic can register them on ``Base.metadata``."""

from app.rag.models.orm import RagChunk, RagSource  # noqa: F401

__all__ = ["RagChunk", "RagSource"]
