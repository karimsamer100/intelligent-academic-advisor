from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import pytest

from app.planning.domain.course import Course, CourseIdentity
from app.planning.domain.eligibility import (
    CourseEligibilityRuleSet,
    EligibilityResult,
    EligibilityStatus,
    RuleSetStatus,
)
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.repositories.adapters.academic_data_types import (
    AcademicDataLookup,
    AcademicDataSourceMode,
)
from app.planning.domain.provenance import Provenance
from app.planning.domain.reasons import ReasonCode
from app.planning.domain.results import ResultMetadata
from app.planning.domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceNodeType,
)
from app.planning.domain.version import DatasetVersion
from app.planning.policy import ExecutionMode
from app.planning.repositories.adapters.student_json_repository import (
    JsonStudentRepository,
)
from app.tools.context import ToolExecutionContext
from app.tools.eligibility import CheckCourseEligibilityTool
from app.tools.errors import (
    ToolArgumentValidationError,
    ToolContextRequiredError,
    ToolDataUnavailableError,
    ToolExecutionError,
)
from app.tools.registry import ToolRegistry


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

    def list_courses(self, *, regulation, program) -> tuple[Course, ...]:
        if (
            self.course.identity.regulation is regulation
            and self.course.identity.program == program
        ):
            return (self.course,)
        return ()

    def get_eligibility_rules(
        self, course_id: CourseIdentity
    ) -> AcademicDataLookup[CourseEligibilityRuleSet]:
        return AcademicDataLookup(
            value=self.rule_set if course_id == self.rule_set.target_course else None,
            dataset_version=None,
        )


class RaisingEligibilityAcademicData:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def list_courses(self, *, regulation, program) -> tuple[Course, ...]:
        del regulation, program
        raise self.error


class FakePlanningService:
    def __init__(self, result: EligibilityResult) -> None:
        self.result = result
        self.requests = []

    def check_eligibility(self, request):
        self.requests.append(request)
        return self.result


def _eligibility_result(identity: CourseIdentity) -> EligibilityResult:
    trace = DecisionTrace(
        DecisionTraceNode(
            node_id="eligibility",
            code=TraceCode.ELIGIBILITY,
            node_type=TraceNodeType.ROOT,
            status=DecisionStatus.SATISFIED,
            subject=identity,
        )
    )
    metadata = ResultMetadata(
        dataset_version=DatasetVersion("tool-test"),
        execution_mode=ExecutionMode.DEVELOPMENT,
        authoritative=False,
        reason_codes=(ReasonCode.UNAPPROVED_RULE,),
        provenance=(
            Provenance(
                rule_id="RULE-TOOL",
                source_id="SRC-TOOL",
                source_page=7,
            ),
        ),
        decision_trace=trace,
    )
    return EligibilityResult(
        target_course=identity,
        status=EligibilityStatus.ELIGIBLE,
        eligible=True,
        rule_set_status=RuleSetStatus.COMPLETE,
        metadata=metadata,
    )


def _tool(
    tmp_path,
    *,
    student_id: str = "student-001",
    identity: CourseIdentity | None = None,
    academic_data=None,
    planning_service=None,
):
    identity = identity or CourseIdentity.parse("R23:CAIE:CSE221")
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
    planning = planning_service or FakePlanningService(_eligibility_result(identity))
    tool = CheckCourseEligibilityTool(
        student_repository=_write_student(tmp_path, student_id),
        academic_data=academic_data or FakeAcademicData(course, rule_set),
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
    assert result["course"] == {"code": "CSE221", "name": "Algorithms"}
    assert result["decision"] == "ELIGIBLE"
    assert result["status"] == "ELIGIBLE"
    assert result["authoritative"] is False
    assert result["requires_human_review"] is False
    assert result["citations"] == [
        {"source_id": "SRC-TOOL", "page": 7, "rule_id": "RULE-TOOL"}
    ]
    assert "decision_trace" not in result


@pytest.mark.parametrize("course_code", ["cse221", "Cse221", "CSE 221"])
def test_eligibility_tool_accepts_course_code_formatting_variants(
    tmp_path,
    course_code: str,
) -> None:
    tool, planning = _tool(tmp_path)

    result = tool.execute(
        {"course_code": course_code},
        ToolExecutionContext(student_id="student-001"),
    )

    assert result["course"]["code"] == "CSE221"
    assert result["decision"] == "ELIGIBLE"
    assert planning.requests[0].course.identity == CourseIdentity.parse(
        "R23:CAIE:CSE221"
    )


def test_eligibility_tool_accepts_surrounding_course_code_whitespace(tmp_path) -> None:
    tool, planning = _tool(tmp_path)

    result = tool.execute(
        {"course_code": "  CSE221  "},
        ToolExecutionContext(student_id="student-001"),
    )

    assert result["course"]["code"] == "CSE221"
    assert planning.requests[0].course.identity.course_code == "CSE221"


def test_eligibility_tool_keeps_unknown_course_unknown(tmp_path) -> None:
    tool, planning = _tool(tmp_path)

    with pytest.raises(ToolDataUnavailableError):
        tool.execute(
            {"course_code": "CSE9999"},
            ToolExecutionContext(student_id="student-001"),
        )

    assert planning.requests == []


@pytest.mark.parametrize(
    "out_of_scope_identity",
    ["R18:CAIE:CSE221", "R23:CESS:CSE221"],
)
def test_eligibility_tool_does_not_cross_trusted_regulation_or_program_scope(
    tmp_path,
    out_of_scope_identity: str,
) -> None:
    tool, planning = _tool(
        tmp_path,
        identity=CourseIdentity.parse(out_of_scope_identity),
    )

    with pytest.raises(ToolDataUnavailableError):
        tool.execute(
            {"course_code": "cse221"},
            ToolExecutionContext(student_id="student-001"),
        )

    assert planning.requests == []


def test_eligibility_tool_preserves_asux_canonical_code(tmp_path) -> None:
    tool, planning = _tool(
        tmp_path,
        identity=CourseIdentity.parse("R23:CAIE:ASUx31"),
    )

    result = tool.execute(
        {"course_code": "ASU X31"},
        ToolExecutionContext(student_id="student-001"),
    )

    assert result["course"]["code"] == "ASUx31"
    assert planning.requests[0].course.identity == CourseIdentity.parse(
        "R23:CAIE:ASUx31"
    )


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


@pytest.mark.parametrize("error_type", [AttributeError, TypeError])
def test_unexpected_eligibility_dependency_errors_use_safe_registry_path(
    tmp_path,
    caplog,
    error_type: type[Exception],
) -> None:
    tool, _ = _tool(
        tmp_path,
        academic_data=RaisingEligibilityAcademicData(
            error_type("synthetic programming bug")
        ),
    )
    registry = ToolRegistry([tool])

    with caplog.at_level(logging.ERROR, logger="app.tools.registry"):
        with pytest.raises(ToolExecutionError) as raised:
            registry.execute(
                "check_course_eligibility",
                {"course_code": "CSE221"},
                ToolExecutionContext(student_id="student-001"),
            )

    assert str(raised.value) == "Tool 'check_course_eligibility' failed to produce a valid result"
    assert "synthetic programming bug" not in str(raised.value)
    assert "tool execution failed" in caplog.text
    assert any(
        record.exc_info and isinstance(record.exc_info[1], error_type)
        for record in caplog.records
    )


def test_registry_preserves_known_eligibility_data_unavailable_error(tmp_path) -> None:
    tool, _ = _tool(tmp_path)
    registry = ToolRegistry([tool])

    with pytest.raises(ToolDataUnavailableError):
        registry.execute(
            "check_course_eligibility",
            {"course_code": "CSE9999"},
            ToolExecutionContext(student_id="student-001"),
        )
