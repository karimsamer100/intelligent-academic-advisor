"""Read-only structured course-information tool adapter."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.planning.domain.course import CourseIdentity
from app.planning.repositories.adapters.academic_data_source import (
    AcademicEligibilityDataSource,
)
from app.planning.repositories.student_repository import StudentRepository
from app.tools.context import ToolExecutionContext, resolve_student_state
from app.tools.course_codes import normalize_course_code
from app.tools.errors import ToolArgumentValidationError, ToolDataUnavailableError
from app.tools.interface import AcademicTool
from app.tools.projections import project_course_information


class GetCourseInformationArguments(BaseModel):
    """Only the course code is controlled by the LLM."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    course_code: str = Field(min_length=1)


class GetCourseInformationTool(AcademicTool[GetCourseInformationArguments]):
    """Expose static typed course facts without evaluating student history."""

    name = "get_course_information"
    description = (
        "Retrieve structured course facts for the trusted regulation and "
        "program, including direct prerequisites and credit hours. Do not use "
        "this tool for student-specific eligibility."
    )
    arguments_model = GetCourseInformationArguments

    def __init__(
        self,
        *,
        student_repository: StudentRepository,
        academic_data: AcademicEligibilityDataSource,
    ) -> None:
        self._student_repository = student_repository
        self._academic_data = academic_data

    def _execute(
        self,
        arguments: GetCourseInformationArguments,
        trusted_context: ToolExecutionContext,
    ) -> dict[str, Any]:
        student = resolve_student_state(
            trusted_context,
            self._student_repository,
            self.name,
        )

        available_courses = self._academic_data.list_courses(
            regulation=student.regulation,
            program=student.program,
        )
        available_codes = tuple(
            course.identity.course_code for course in available_courses
        )

        try:
            course_code = normalize_course_code(
                arguments.course_code,
                available_codes=available_codes,
            )
            identity = CourseIdentity(
                regulation=student.regulation,
                program=student.program,
                course_code=course_code,
            )
        except (TypeError, ValueError):
            raise ToolArgumentValidationError(self.name) from None

        course_lookup = self._academic_data.get_course(identity)
        course = course_lookup.value
        if course is None or course.identity != identity:
            raise ToolDataUnavailableError(self.name)

        rule_lookup = self._academic_data.get_eligibility_rules(identity)
        rule_set = rule_lookup.value
        if rule_set is not None and rule_set.target_course != identity:
            raise ToolDataUnavailableError(self.name)

        dataset_version = (
            rule_lookup.dataset_version
            or course_lookup.dataset_version
            or self._academic_data.dataset_version
        )
        return project_course_information(
            course_lookup=course_lookup,
            rule_lookup=rule_lookup,
            source_mode=self._academic_data.source_mode,
            dataset_version=dataset_version,
        )


__all__ = [
    "GetCourseInformationArguments",
    "GetCourseInformationTool",
]
