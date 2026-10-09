"""FastAPI dependency wiring: route -> service -> retriever -> database."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.llm.interface import LLMProvider
from app.llm.providers.ollama import OllamaProvider
from app.orchestration.composition import (
    AdvisorApplication,
    AdvisorStaticDependencies,
    build_advisor_application,
    build_advisor_static_dependencies,
)
from app.orchestration.orchestrator import AdvisorOrchestrator
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


LLMServiceDependency = Annotated[LLMService, Depends(get_llm_service)]


def get_retriever(db: DbSession) -> Retriever:
    return rag_provider.get_retriever(db)


RetrieverDependency = Annotated[Retriever, Depends(get_retriever)]


def get_rag_service(retriever: RetrieverDependency) -> RAGService:
    return RAGService(retriever=retriever)


RAGServiceDependency = Annotated[RAGService, Depends(get_rag_service)]


def get_advisor_static_dependencies(request: Request) -> AdvisorStaticDependencies:
    """Return app-owned Planning/academic dependencies, building them once."""

    dependencies = getattr(request.app.state, "advisor_static_dependencies", None)
    if dependencies is None:
        dependencies = build_advisor_static_dependencies(get_settings())
        request.app.state.advisor_static_dependencies = dependencies
    return dependencies


AdvisorStaticDependenciesDependency = Annotated[
    AdvisorStaticDependencies,
    Depends(get_advisor_static_dependencies),
]


def get_advisor_application(
    llm_service: LLMServiceDependency,
    rag_service: RAGServiceDependency,
    static_dependencies: AdvisorStaticDependenciesDependency,
) -> AdvisorApplication:
    """Compose one request boundary around static and request-scoped services."""

    return build_advisor_application(
        llm_service=llm_service,
        planning_service=static_dependencies.planning_service,
        rag_service=rag_service,
        student_repository=static_dependencies.student_repository,
        academic_data=static_dependencies.academic_data,
    )


AdvisorApplicationDependency = Annotated[
    AdvisorApplication,
    Depends(get_advisor_application),
]


def get_advisor_orchestrator(
    application: AdvisorApplicationDependency,
) -> AdvisorOrchestrator:
    """Expose the composed orchestrator for a future chat route."""

    return application.orchestrator


AdvisorOrchestratorDependency = Annotated[
    AdvisorOrchestrator,
    Depends(get_advisor_orchestrator),
]
