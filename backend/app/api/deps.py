"""FastAPI dependency wiring: route -> service -> repository / module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rag.provider import get_retriever
from app.repositories.health_repository import HealthRepository
from app.services.health_service import HealthService
from app.services.rag_service import RAGService

DbSession = Annotated[Session, Depends(get_db)]


def get_health_service(db: DbSession) -> HealthService:
    return HealthService(HealthRepository(db))


def get_rag_service() -> RAGService:
    return RAGService(retriever=get_retriever())
