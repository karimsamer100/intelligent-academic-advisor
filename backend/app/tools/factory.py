"""Explicit application composition for the initial academic tool set."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.planning.audit.service import DegreeAuditService
from app.planning.eligibility.service import EligibilityService
from app.planning.engine import PlanningEngine
from app.planning.policy import ExecutionPolicy
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
from app.planning.domain.version import DatasetVersion
from app.planning.rules.evaluator import RuleEvaluator
from app.services.planning_service import PlanningService
from app.services.rag_service import RAGService
from app.tools.degree_audit import DegreeAuditTool
from app.tools.eligibility import CheckCourseEligibilityTool
from app.tools.errors import ToolCompositionError
from app.tools.rag import SearchOfficialDocumentsTool
from app.tools.registry import ToolRegistry


def build_academic_tool_registry(
    rag_service: RAGService,
    *,
    settings: Settings | None = None,
) -> ToolRegistry:
    """Compose the current read-only tools from trusted application services.

    The RAG service is deliberately supplied by the caller because its
    retriever is request/database scoped.  Planning uses the normalized
    development data tier and its real adapter-provided dataset version; no
    fallback version is synthesized here.
    """

    if rag_service is None or not callable(getattr(rag_service, "search", None)):
        raise ToolCompositionError()

    resolved_settings = settings or get_settings()
    if not isinstance(resolved_settings, Settings):
        raise TypeError("settings must be a Settings instance or None")

    academic_data, dataset_version = _load_academic_data(resolved_settings)
    student_repository = JsonStudentRepository(resolved_settings.student_data_path)
    planning_service = _build_planning_service(dataset_version)

    return ToolRegistry(
        (
            CheckCourseEligibilityTool(
                student_repository=student_repository,
                academic_data=academic_data,
                planning_service=planning_service,
            ),
            DegreeAuditTool(
                student_repository=student_repository,
                academic_data=academic_data,
                planning_service=planning_service,
            ),
            SearchOfficialDocumentsTool(student_repository, rag_service),
        )
    )


def _load_academic_data(
    settings: Settings,
) -> tuple[JsonAcademicDataAdapter, DatasetVersion]:
    package_root = settings.academic_data_foundation_path
    if package_root is None:
        raise ToolCompositionError()

    try:
        loaded = JsonAcademicDataAdapter.load(
            AcademicDataConfig(
                package_root=package_root,
                source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
                requested_execution_mode=ExecutionPolicy.development().mode,
            )
        )
    except (OSError, TypeError, ValueError):
        raise ToolCompositionError() from None

    adapter = loaded.value
    dataset_version = loaded.dataset_version
    if adapter is None or dataset_version is None or adapter.dataset_version is None:
        raise ToolCompositionError()
    return adapter, dataset_version


def _build_planning_service(dataset_version: DatasetVersion) -> PlanningService:
    if not isinstance(dataset_version, DatasetVersion):
        raise ToolCompositionError()
    policy = ExecutionPolicy.development()
    evaluator = RuleEvaluator(policy, dataset_version)
    engine = PlanningEngine(
        eligibility_service=EligibilityService(evaluator),
        degree_audit_service=DegreeAuditService(policy, dataset_version),
    )
    return PlanningService(engine)


__all__ = ["build_academic_tool_registry"]
