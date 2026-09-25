"""FastAPI dependency wiring: route -> service -> retriever -> database."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rag import provider as rag_provider
from app.rag.interface import Retriever
from app.repositories.health_repository import HealthRepository
from app.services.health_service import HealthService
from app.services.rag_service import RAGService

DbSession = Annotated[Session, Depends(get_db)]


def get_health_service(db: DbSession) -> HealthService:
    return HealthService(HealthRepository(db))


def get_retriever(db: DbSession) -> Retriever:
    return rag_provider.get_retriever(db)


RetrieverDependency = Annotated[Retriever, Depends(get_retriever)]


def get_rag_service(retriever: RetrieverDependency) -> RAGService:
    return RAGService(retriever=retriever)
