"""FastAPI dependency wiring: route -> service -> retriever -> database."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.llm.interface import LLMProvider
from app.llm.providers.ollama import OllamaProvider
from app.rag import provider as rag_provider
from app.rag.interface import Retriever
from app.repositories.health_repository import HealthRepository
from app.services.health_service import HealthService
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService

DbSession = Annotated[Session, Depends(get_db)]


def get_health_service(db: DbSession) -> HealthService:
    return HealthService(HealthRepository(db))


def get_llm_provider(request: Request) -> LLMProvider:
    return OllamaProvider(
        settings=get_settings(),
        client=request.app.state.llm_http_client,
    )


LLMProviderDependency = Annotated[LLMProvider, Depends(get_llm_provider)]


def get_llm_service(provider: LLMProviderDependency) -> LLMService:
    return LLMService(provider)


def get_retriever(db: DbSession) -> Retriever:
    return rag_provider.get_retriever(db)


RetrieverDependency = Annotated[Retriever, Depends(get_retriever)]


def get_rag_service(retriever: RetrieverDependency) -> RAGService:
    return RAGService(retriever=retriever)
