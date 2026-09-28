"""Read-only course-eligibility tool adapter."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.planning.domain.course import CourseIdentity
from app.planning.domain.eligibility import (
    EligibilityRequest,
    RuleSetStatus,
)
from app.planning.repositories.adapters.academic_data_source import (
    AcademicEligibilityDataSource,
)
from app.planning.repositories.student_repository import StudentRepository
from app.services.planning_service import PlanningService
from app.tools.context import ToolExecutionContext, resolve_student_state
from app.tools.errors import ToolArgumentValidationError, ToolDataUnavailableError
from app.tools.interface import AcademicTool


class CheckCourseEligibilityArguments(BaseModel):
    """Only the course code is controlled by the LLM."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    course_code: str = Field(min_length=1)


class CheckCourseEligibilityTool(AcademicTool[CheckCourseEligibilityArguments]):
    name = "check_course_eligibility"
    description = "Check whether the trusted student may take one course."
    arguments_model = CheckCourseEligibilityArguments

    def __init__(
        self,
        *,
        student_repository: StudentRepository,
        academic_data: AcademicEligibilityDataSource,
        planning_service: PlanningService,
    ) -> None:
        self._student_repository = student_repository
        self._academic_data = academic_data
        self._planning_service = planning_service

    def _execute(
        self,
        arguments: CheckCourseEligibilityArguments,
        trusted_context: ToolExecutionContext,
    ) -> dict[str, Any]:
        student = resolve_student_state(
            trusted_context,
            self._student_repository,
            self.name,
        )

        try:
            identity = CourseIdentity(
                regulation=student.regulation,
                program=student.program,
                course_code=arguments.course_code,
            )
        except (TypeError, ValueError):
            raise ToolArgumentValidationError(self.name) from None

        try:
            course_lookup = self._academic_data.get_course(identity)
            rule_lookup = self._academic_data.get_eligibility_rules(identity)
        except (TypeError, ValueError, KeyError):
            raise ToolDataUnavailableError(self.name) from None

        course = course_lookup.value
        rule_set = rule_lookup.value
        if (
            course is None
            or rule_set is None
            or rule_set.status is RuleSetStatus.UNAVAILABLE
            or course.identity != identity
            or rule_set.target_course != identity
        ):
            raise ToolDataUnavailableError(self.name)

        try:
            request = EligibilityRequest(
                student=student,
                course=course,
                rule_set=rule_set,
            )
        except (TypeError, ValueError):
            raise ToolDataUnavailableError(self.name) from None

        result = self._planning_service.check_eligibility(request)
        # Transitional internal Planning payload; future LLM projections
        # should be smaller, so orchestration must not depend on every field.
        return result.to_dict()


__all__ = [
    "CheckCourseEligibilityArguments",
    "CheckCourseEligibilityTool",
]
