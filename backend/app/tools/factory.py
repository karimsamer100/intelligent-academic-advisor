"""Assembly boundary for the Checkpoint 1 academic tool set."""

from __future__ import annotations

from app.planning.repositories.student_repository import StudentRepository
from app.services.planning_service import PlanningService
from app.services.rag_service import RAGService
from app.tools.degree_audit import AcademicAuditDataSource, DegreeAuditTool
from app.tools.eligibility import CheckCourseEligibilityTool
from app.tools.course_information import GetCourseInformationTool
from app.tools.rag import SearchOfficialDocumentsTool
from app.tools.registry import ToolRegistry


def build_academic_tool_registry(
    *,
    planning_service: PlanningService,
    rag_service: RAGService,
    student_repository: StudentRepository,
    academic_data: AcademicAuditDataSource,
) -> ToolRegistry:
    """Compose tools from already-created application dependencies."""

    return ToolRegistry(
        (
            CheckCourseEligibilityTool(
                student_repository=student_repository,
                academic_data=academic_data,
                planning_service=planning_service,
            ),
            GetCourseInformationTool(
                student_repository=student_repository,
                academic_data=academic_data,
            ),
            DegreeAuditTool(
                student_repository=student_repository,
                academic_data=academic_data,
                planning_service=planning_service,
            ),
            SearchOfficialDocumentsTool(student_repository, rag_service),
        )
    )


__all__ = ["build_academic_tool_registry"]
