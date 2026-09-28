from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from app.planning.domain.course import Course, CourseIdentity
from app.planning.domain.eligibility import CourseEligibilityRuleSet, RuleSetStatus
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.repositories.adapters.academic_data_types import (
    AcademicDataLookup,
    AcademicDataSourceMode,
)
from app.planning.repositories.adapters.student_json_repository import (
    JsonStudentRepository,
)
from app.tools.context import ToolExecutionContext
from app.tools.eligibility import CheckCourseEligibilityTool
from app.tools.errors import (
    ToolArgumentValidationError,
    ToolContextRequiredError,
    ToolDataUnavailableError,
)


def _write_student(tmp_path, student_id: str = "student-001") -> JsonStudentRepository:
    path = tmp_path / "students.json"
    path.write_text(
        json.dumps(
            {
                "students": [
                    {
                        "student_id": student_id,
                        "regulation": 2023,
                        "program": "CAIE",
                        "course_attempts": [],
                        "current_registrations": [],
                        "academic_snapshot": {
                            "student_id": student_id,
                            "regulation": 2023,
                            "program": "CAIE",
                            "gpa": 3.0,
                            "earned_credit_hours": 0,
                        },
                        "history_coverage": "COMPLETE",
                        "registration_coverage": "COMPLETE",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return JsonStudentRepository(path)


@dataclass
class FakeAcademicData:
    course: Course
    rule_set: CourseEligibilityRuleSet
    source_mode: AcademicDataSourceMode = AcademicDataSourceMode.NORMALIZED_DEVELOPMENT
    dataset_version: object | None = None

    def get_course(self, course_id: CourseIdentity) -> AcademicDataLookup[Course]:
        return AcademicDataLookup(
            value=self.course if course_id == self.course.identity else None,
            dataset_version=None,
        )

    def get_eligibility_rules(
        self, course_id: CourseIdentity
    ) -> AcademicDataLookup[CourseEligibilityRuleSet]:
        return AcademicDataLookup(
            value=self.rule_set if course_id == self.rule_set.target_course else None,
            dataset_version=None,
        )


class FakePlanningService:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.requests = []

    def check_eligibility(self, request):
        self.requests.append(request)
        return _Result(self.result)


class _Result:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def to_dict(self) -> dict[str, object]:
        return self.payload


def _tool(tmp_path, *, student_id: str = "student-001"):
    identity = CourseIdentity.parse("R23:CAIE:CSE221")
    course = Course(
        identity=identity,
        course_name="Algorithms",
        credit_hours=3,
        approval_status=ApprovalStatus.SOURCE_VERIFIED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    rule_set = CourseEligibilityRuleSet(
        target_course=identity,
        status=RuleSetStatus.COMPLETE,
    )
    planning = FakePlanningService(
        {"target_course": identity.course_id, "status": "ELIGIBLE"}
    )
    tool = CheckCourseEligibilityTool(
        student_repository=_write_student(tmp_path, student_id),
        academic_data=FakeAcademicData(course, rule_set),
        planning_service=planning,
    )
    return tool, planning


def test_eligibility_schema_contains_only_course_code(tmp_path) -> None:
    tool, _ = _tool(tmp_path)

    properties = tool.definition.input_schema["properties"]

    assert set(properties) == {"course_code"}
    assert "student_id" not in properties
    assert "gpa" not in properties
    assert "regulation" not in properties
    assert "program" not in properties
    assert "attempts" not in properties
    assert "history" not in properties


def test_eligibility_tool_loads_trusted_state_and_academic_data(tmp_path) -> None:
    tool, planning = _tool(tmp_path)

    result = tool.execute(
        {"course_code": "CSE221"},
        ToolExecutionContext(student_id="student-001"),
    )

    request = planning.requests[0]
    assert request.student.student_id == "student-001"
    assert request.student.regulation.value == "R23"
    assert request.student.program.value == "CAIE"
    assert request.course.identity.course_id == "R23:CAIE:CSE221"
    assert request.rule_set.target_course == request.course.identity
    assert result == {
        "target_course": "R23:CAIE:CSE221",
        "status": "ELIGIBLE",
    }


def test_eligibility_tool_requires_trusted_student_context(tmp_path) -> None:
    tool, planning = _tool(tmp_path)

    with pytest.raises(ToolContextRequiredError):
        tool.execute({"course_code": "CSE221"}, ToolExecutionContext())

    assert planning.requests == []


def test_eligibility_tool_fails_closed_for_missing_student(tmp_path) -> None:
    tool, planning = _tool(tmp_path, student_id="different-student")

    with pytest.raises(ToolDataUnavailableError):
        tool.execute(
            {"course_code": "CSE221"},
            ToolExecutionContext(student_id="missing-student"),
        )

    assert planning.requests == []


def test_eligibility_tool_rejects_academic_overrides(tmp_path) -> None:
    tool, planning = _tool(tmp_path)

    with pytest.raises(ToolArgumentValidationError):
        tool.execute(
            {
                "course_code": "CSE221",
                "student_id": "forged-student",
                "gpa": 4.0,
                "regulation": 2018,
            },
            ToolExecutionContext(student_id="student-001"),
        )

    assert planning.requests == []
