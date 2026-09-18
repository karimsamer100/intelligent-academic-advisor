from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def database_readiness(session: Session) -> dict:
    session.execute(text("SELECT 1"))
    vector_version = session.scalar(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    )
    return {
        "database": "ok",
        "pgvector": "ok" if vector_version else "missing",
        "pgvector_version": vector_version,
    }
