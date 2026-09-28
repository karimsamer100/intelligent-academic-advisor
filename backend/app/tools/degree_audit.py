"""Read-only degree-audit tool adapter."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from app.planning.domain.audit import DegreeAuditRequest
from app.planning.domain.course import Program, Regulation
from app.planning.domain.electives import ElectivePool
from app.planning.domain.requirements import (
    ProgramRequirementSet,
    RequirementSetStatus,
    RequirementStage,
)
from app.planning.repositories.adapters.academic_data_source import (
    AcademicEligibilityDataSource,
)
from app.planning.repositories.student_repository import StudentRepository
from app.services.planning_service import PlanningService
from app.tools.context import ToolExecutionContext, resolve_student_state
from app.tools.errors import ToolDataUnavailableError
from app.tools.interface import AcademicTool


class AcademicAuditDataSource(AcademicEligibilityDataSource, Protocol):
    """Typed slice of the existing academic adapter needed by degree audit."""

    def get_requirement_set(
        self,
        *,
        regulation: Regulation,
        program: Program,
        stage: RequirementStage | None = None,
    ) -> ProgramRequirementSet: ...

    def list_elective_pools(
        self,
        *,
        regulation: Regulation,
        program: Program,
    ) -> tuple[ElectivePool, ...]: ...


class DegreeAuditArguments(BaseModel):
    """The first audit tool has no LLM-controlled academic inputs."""

    model_config = ConfigDict(extra="forbid")


class DegreeAuditTool(AcademicTool[DegreeAuditArguments]):
    name = "degree_audit"
    description = "Audit the trusted student's modeled program requirements."
    arguments_model = DegreeAuditArguments

    def __init__(
        self,
        *,
        student_repository: StudentRepository,
        academic_data: AcademicAuditDataSource,
        planning_service: PlanningService,
    ) -> None:
        self._student_repository = student_repository
        self._academic_data = academic_data
        self._planning_service = planning_service

    def _execute(
        self,
        arguments: DegreeAuditArguments,
        trusted_context: ToolExecutionContext,
    ) -> dict[str, Any]:
        del arguments
        student = resolve_student_state(
            trusted_context,
            self._student_repository,
            self.name,
        )

        try:
            requirement_set = self._academic_data.get_requirement_set(
                regulation=student.regulation,
                program=student.program,
                stage=RequirementStage.PROGRAM_COMPLETION,
            )
            pools = self._academic_data.list_elective_pools(
                regulation=student.regulation,
                program=student.program,
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            raise ToolDataUnavailableError(self.name) from None

        if (
            not isinstance(requirement_set, ProgramRequirementSet)
            or requirement_set.status is RequirementSetStatus.UNAVAILABLE
        ):
            raise ToolDataUnavailableError(self.name)

        try:
            pools = tuple(pools)
            request = DegreeAuditRequest(
                student=student,
                requirement_set=requirement_set,
                stage=RequirementStage.PROGRAM_COMPLETION,
                pools=pools,
            )
            result = self._planning_service.audit(request)
            # Transitional internal Planning payload; future LLM projections
            # should be smaller, so orchestration must not depend on every field.
            return result.to_dict()
        except (AttributeError, TypeError, ValueError, KeyError):
            raise ToolDataUnavailableError(self.name) from None


__all__ = [
    "AcademicAuditDataSource",
    "DegreeAuditArguments",
    "DegreeAuditTool",
]
