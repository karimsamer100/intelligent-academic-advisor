from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.health import database_readiness
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    try:
        state = database_readiness(db)
    except Exception as exc:
        raise AppError(
            code="DATABASE_UNAVAILABLE",
            message="Database connection is unavailable",
            status_code=503,
        ) from exc
    if state["pgvector"] != "ok":
        raise AppError(
            code="PGVECTOR_UNAVAILABLE",
            message="pgvector extension is not available",
            status_code=503,
            details=state,
        )
    return {"status": "ready", **state}
