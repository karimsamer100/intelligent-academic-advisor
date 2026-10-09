"""Explicit application composition for the grounded advisor."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.planning.audit.service import DegreeAuditService
from app.planning.domain.version import DatasetVersion
from app.planning.eligibility.service import EligibilityService
from app.planning.engine import PlanningEngine
from app.planning.policy import ExecutionMode, ExecutionPolicy
from app.planning.repositories.adapters.academic_data_adapter import (
    JsonAcademicDataAdapter,
)
from app.planning.repositories.adapters.academic_data_types import (
    AcademicDataConfig,
    AcademicDataSourceMode,
)
from app.planning.repositories.adapters.student_json_repository import (
    JsonStudentRepository,
)
from app.planning.repositories.student_repository import StudentRepository
from app.planning.rules.evaluator import RuleEvaluator
from app.services.llm_service import LLMService
from app.services.planning_service import PlanningService
from app.services.rag_service import RAGService
from app.tools.degree_audit import AcademicAuditDataSource
from app.tools.errors import ToolCompositionError
from app.tools.factory import build_academic_tool_registry
from app.tools.registry import ToolRegistry

from app.orchestration.orchestrator import AdvisorOrchestrator


@dataclass(frozen=True, slots=True)
class AdvisorStaticDependencies:
    """Application-owned dependencies that are safe to reuse across requests."""

    planning_service: PlanningService
    student_repository: StudentRepository
    academic_data: JsonAcademicDataAdapter


@dataclass(frozen=True, slots=True)
class AdvisorApplication:
    """One explicitly composed advisor boundary for a request."""

    llm_service: LLMService
    planning_service: PlanningService
    rag_service: RAGService
    student_repository: StudentRepository
    academic_data: AcademicAuditDataSource
    tool_registry: ToolRegistry
    orchestrator: AdvisorOrchestrator


def build_advisor_static_dependencies(
    settings: Settings,
) -> AdvisorStaticDependencies:
    """Build the reusable Planning and academic-data dependencies once.

    The adapter is deliberately loaded in normalized development mode.  A
    missing dataset version receives an explicit development-only identity;
    this preserves the adapter's incomplete/unapproved semantics and never
    upgrades the data to an authoritative source.
    """

    if not isinstance(settings, Settings):
        raise TypeError("settings must be a Settings instance")
    if settings.academic_data_foundation_path is None:
        raise ToolCompositionError()

    try:
        load_result = JsonAcademicDataAdapter.load(
            AcademicDataConfig(
                package_root=settings.academic_data_foundation_path,
                source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
                requested_execution_mode=ExecutionMode.DEVELOPMENT,
            )
        )
    except (OSError, TypeError, ValueError):
        raise ToolCompositionError() from None

    academic_data = load_result.value
    if academic_data is None:
        raise ToolCompositionError()

    dataset_version = load_result.dataset_version or DatasetVersion(
        "academic-data-normalized-development",
        source="normalized",
    )
    policy = ExecutionPolicy.development()
    planning_engine = PlanningEngine(
        eligibility_service=EligibilityService(
            RuleEvaluator(policy, dataset_version)
        ),
        degree_audit_service=DegreeAuditService(policy, dataset_version),
    )

    return AdvisorStaticDependencies(
        planning_service=PlanningService(planning_engine),
        student_repository=JsonStudentRepository(settings.student_data_path),
        academic_data=academic_data,
    )


def build_advisor_application(
    *,
    llm_service: LLMService,
    planning_service: PlanningService,
    rag_service: RAGService,
    student_repository: StudentRepository,
    academic_data: AcademicAuditDataSource,
) -> AdvisorApplication:
    """Compose the existing services into one grounded advisor boundary.

    ``rag_service`` is supplied by the request-scoped dependency graph.  The
    function therefore creates no retriever, database session, or RAG service;
    it only wires the already-owned objects into the frozen tool registry.
    """

    if not isinstance(llm_service, LLMService):
        raise TypeError("llm_service must be an LLMService")
    if not isinstance(planning_service, PlanningService):
        raise TypeError("planning_service must be a PlanningService")
    if not isinstance(rag_service, RAGService):
        raise TypeError("rag_service must be an RAGService")
    if not isinstance(student_repository, StudentRepository):
        raise ToolCompositionError()
    if not isinstance(academic_data, AcademicAuditDataSource):
        raise ToolCompositionError()

    tool_registry = build_academic_tool_registry(
        planning_service=planning_service,
        rag_service=rag_service,
        student_repository=student_repository,
        academic_data=academic_data,
    )
    orchestrator = AdvisorOrchestrator(llm_service, tool_registry)
    return AdvisorApplication(
        llm_service=llm_service,
        planning_service=planning_service,
        rag_service=rag_service,
        student_repository=student_repository,
        academic_data=academic_data,
        tool_registry=tool_registry,
        orchestrator=orchestrator,
    )


__all__ = [
    "AdvisorApplication",
    "AdvisorStaticDependencies",
    "build_advisor_application",
    "build_advisor_static_dependencies",
]
