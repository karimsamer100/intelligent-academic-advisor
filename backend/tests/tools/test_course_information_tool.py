from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from app.planning.domain.course import Course, CourseIdentity
from app.planning.domain.eligibility import CourseEligibilityRuleSet, RuleSetStatus
from app.planning.domain.expressions import (
    AndExpression,
    CoursePassedExpression,
    MinGpaExpression,
    NotExpression,
    OrExpression,
    UnsupportedExpression,
)
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.domain.provenance import Provenance
from app.planning.domain.reasons import ReasonCode
from app.planning.domain.version import DatasetVersion
from app.planning.repositories.adapters.academic_data_types import (
    AcademicDataDiagnostic,
    AcademicDataDiagnosticCode,
    AcademicDataLookup,
    AcademicDataSourceMode,
)
from app.planning.repositories.adapters.student_json_repository import (
    JsonStudentRepository,
)
from app.planning.domain.rules import AcademicRule
from app.tools.context import ToolExecutionContext
from app.tools.course_information import GetCourseInformationTool
from app.tools.errors import ToolArgumentValidationError, ToolContextRequiredError
from app.tools.projections import _course_information_is_authoritative


TARGET = CourseIdentity.parse("R23:CAIE:CSE221")
PREREQUISITE_ONE = CourseIdentity.parse("R23:CAIE:CSE141")
PREREQUISITE_TWO = CourseIdentity.parse("R23:CAIE:CSE121")


def _student_repository(
    tmp_path,
    *,
    regulation: int = 2023,
    program: str = "CAIE",
    course_attempts: list[dict[str, object]] | None = None,
) -> JsonStudentRepository:
    path = tmp_path / "students.json"
    path.write_text(
        json.dumps(
            {
                "students": [
                    {
                        "student_id": "student-001",
                        "regulation": regulation,
                        "program": program,
                        "course_attempts": course_attempts or [],
                        "current_registrations": [],
                        "academic_snapshot": {
                            "student_id": "student-001",
                            "regulation": regulation,
                            "program": program,
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


def _course(
    identity: CourseIdentity = TARGET,
    *,
    approval_status: ApprovalStatus = ApprovalStatus.SOURCE_VERIFIED,
    verification_status: VerificationStatus = VerificationStatus.SOURCE_VERIFIED,
) -> Course:
    return Course(
        identity=identity,
        course_name="Logic Design and Computer Organization",
        credit_hours=4,
        approval_status=approval_status,
        verification_status=verification_status,
    )


def _rule_set(
    identity: CourseIdentity = TARGET,
    *,
    expression=None,
    status: RuleSetStatus = RuleSetStatus.COMPLETE,
    reason_codes: tuple[ReasonCode, ...] = (),
    include_rule: bool = True,
    approval_status: ApprovalStatus = ApprovalStatus.SOURCE_VERIFIED,
    verification_status: VerificationStatus = VerificationStatus.SOURCE_VERIFIED,
) -> CourseEligibilityRuleSet:
    if expression is None:
        expression = AndExpression(
            (
                CoursePassedExpression(PREREQUISITE_ONE),
                CoursePassedExpression(PREREQUISITE_TWO),
            )
        )
    rule = AcademicRule(
        rule_id=f"PRE-{identity.course_id}",
        regulation=identity.regulation,
        program=identity.program,
        approval_status=approval_status,
        verification_status=verification_status,
        critical_for_planner=True,
        provenance=Provenance(
            rule_id=f"PRE-{identity.course_id}",
            source_id="SRC-BYLAW_2023_PDF",
            source_page=161,
            approval_status=ApprovalStatus.SOURCE_VERIFIED,
            verification_status=VerificationStatus.SOURCE_VERIFIED,
        ),
        expression=expression,
    )
    return CourseEligibilityRuleSet(
        target_course=identity,
        status=status,
        rules=(rule,) if include_rule else (),
        reason_codes=reason_codes,
    )


@dataclass
class FakeAcademicData:
    courses: tuple[Course, ...]
    rule_set: CourseEligibilityRuleSet | None
    rule_diagnostics: tuple[AcademicDataDiagnostic, ...] = ()
    source_mode: AcademicDataSourceMode = AcademicDataSourceMode.NORMALIZED_DEVELOPMENT
    dataset_version: DatasetVersion | None = DatasetVersion(
        "course-information-test",
        source="tests",
    )

    def list_courses(self, *, regulation, program) -> tuple[Course, ...]:
        return tuple(
            course
            for course in self.courses
            if course.identity.regulation is regulation
            and course.identity.program == program
        )

    def get_course(self, course_id: CourseIdentity) -> AcademicDataLookup[Course]:
        course = next(
            (item for item in self.courses if item.identity == course_id),
            None,
        )
        provenance = (
            (
                Provenance(
                    source_id="SRC-BYLAW_2023_PDF",
                    source_page=161,
                    approval_status=course.approval_status,
                    verification_status=course.verification_status,
                ),
            )
            if course is not None
            else ()
        )
        return AcademicDataLookup(
            value=course,
            dataset_version=self.dataset_version,
            provenance=provenance,
        )

    def get_eligibility_rules(
        self,
        course_id: CourseIdentity,
    ) -> AcademicDataLookup[CourseEligibilityRuleSet]:
        value = (
            self.rule_set
            if self.rule_set is not None and self.rule_set.target_course == course_id
            else None
        )
        provenance = (
            (self.rule_set.rules[0].provenance,)
            if value is not None
            and value.rules
            and value.rules[0].provenance is not None
            else ()
        )
        return AcademicDataLookup(
            value=value,
            dataset_version=self.dataset_version,
            provenance=provenance,
            diagnostics=self.rule_diagnostics,
        )


def _tool(
    tmp_path,
    *,
    academic_data: FakeAcademicData | None = None,
    regulation: int = 2023,
    program: str = "CAIE",
    course_attempts: list[dict[str, object]] | None = None,
) -> GetCourseInformationTool:
    return GetCourseInformationTool(
        student_repository=_student_repository(
            tmp_path,
            regulation=regulation,
            program=program,
            course_attempts=course_attempts,
        ),
        academic_data=academic_data
        or FakeAcademicData((_course(),), _rule_set()),
    )


def test_cse221_returns_scoped_static_course_information(tmp_path) -> None:
    result = _tool(tmp_path).execute(
        {"course_code": "CSE221"},
        ToolExecutionContext(student_id="student-001"),
    )

    assert result["course"] == {
        "identity": "R23:CAIE:CSE221",
        "code": "CSE221",
        "name": "Logic Design and Computer Organization",
        "credit_hours": 4,
        "regulation": "R23",
        "program": "CAIE",
        "approval_status": "SOURCE_VERIFIED",
        "verification_status": "SOURCE_VERIFIED",
    }
    assert result["coverage"]["prerequisites"] == "COMPLETE"
    assert result["prerequisites"]["expression"] == {
        "type": "AND",
        "children": [
            {
                "type": "COURSE_PASSED",
                "course_id": "R23:CAIE:CSE141",
                "course_code": "CSE141",
            },
            {
                "type": "COURSE_PASSED",
                "course_id": "R23:CAIE:CSE121",
                "course_code": "CSE121",
            },
        ],
    }
    assert result["prerequisites"]["rules"][0]["rule_id"] == "PRE-R23:CAIE:CSE221"
    assert result["prerequisites"]["rules"][0]["provenance"] == {
        "rule_id": "PRE-R23:CAIE:CSE221",
        "source_id": "SRC-BYLAW_2023_PDF",
        "page": 161,
        "approval_status": "SOURCE_VERIFIED",
        "verification_status": "SOURCE_VERIFIED",
    }
    assert result["data_source"] == {
        "source_mode": "NORMALIZED_DEVELOPMENT",
        "dataset_version": {"version": "course-information-test", "source": "tests"},
    }
    assert result["authoritative"] is False
    assert "decision" not in result
    assert "requires_human_review" not in result


def test_complete_empty_rule_set_is_not_complete_course_information(
    tmp_path,
) -> None:
    data = FakeAcademicData(
        (
            _course(
                approval_status=ApprovalStatus.APPROVED,
                verification_status=VerificationStatus.SOURCE_VERIFIED,
            ),
        ),
        _rule_set(
            status=RuleSetStatus.COMPLETE,
            include_rule=False,
        ),
        source_mode=AcademicDataSourceMode.VERIFIED_AUTHORITATIVE,
    )

    result = _tool(tmp_path, academic_data=data).execute(
        {"course_code": "CSE221"},
        ToolExecutionContext(student_id="student-001"),
    )

    assert result["coverage"]["prerequisites"] == "INCOMPLETE"
    assert result["prerequisites"]["rules"] == []
    assert result["authoritative"] is False


def test_authority_requires_verified_nonempty_rules_and_complete_corequisites(
    tmp_path,
) -> None:
    course = _course(
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    complete_rule_set = _rule_set(
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    assert (
        _course_information_is_authoritative(
            course,
            complete_rule_set,
            source_mode=AcademicDataSourceMode.VERIFIED_AUTHORITATIVE,
            corequisite_status="AVAILABLE",
        )
        is True
    )
    assert (
        _course_information_is_authoritative(
            course,
            complete_rule_set,
            source_mode=AcademicDataSourceMode.VERIFIED_AUTHORITATIVE,
            corequisite_status="UNAVAILABLE",
        )
        is False
    )
    assert (
        _course_information_is_authoritative(
            course,
            _rule_set(status=RuleSetStatus.COMPLETE, include_rule=False),
            source_mode=AcademicDataSourceMode.VERIFIED_AUTHORITATIVE,
            corequisite_status="AVAILABLE",
        )
        is False
    )
    assert (
        _course_information_is_authoritative(
            course,
            _rule_set(
                approval_status=ApprovalStatus.APPROVED,
                verification_status=VerificationStatus.NEEDS_VERIFICATION,
            ),
            source_mode=AcademicDataSourceMode.VERIFIED_AUTHORITATIVE,
            corequisite_status="AVAILABLE",
        )
        is False
    )
    assert (
        _course_information_is_authoritative(
            _course(
                approval_status=ApprovalStatus.SOURCE_VERIFIED,
                verification_status=VerificationStatus.SOURCE_VERIFIED,
            ),
            complete_rule_set,
            source_mode=AcademicDataSourceMode.VERIFIED_AUTHORITATIVE,
            corequisite_status="AVAILABLE",
        )
        is False
    )
    assert (
        _course_information_is_authoritative(
            course,
            _rule_set(
                approval_status=ApprovalStatus.SOURCE_VERIFIED,
                verification_status=VerificationStatus.SOURCE_VERIFIED,
            ),
            source_mode=AcademicDataSourceMode.VERIFIED_AUTHORITATIVE,
            corequisite_status="AVAILABLE",
        )
        is False
    )


def test_nested_and_or_not_and_unsupported_expression_semantics_are_preserved(
    tmp_path,
) -> None:
    expression = AndExpression(
        (
            OrExpression(
                (
                    CoursePassedExpression(PREREQUISITE_ONE),
                    NotExpression(CoursePassedExpression(PREREQUISITE_TWO)),
                )
            ),
            MinGpaExpression(2.5),
            UnsupportedExpression(
                source_type="UNRESOLVED_CONDITION",
                reason="requires academic interpretation",
            ),
        )
    )
    result = _tool(
        tmp_path,
        academic_data=FakeAcademicData(
            (_course(),),
            _rule_set(expression=expression),
        ),
    ).execute(
        {"course_code": "CSE221"},
        ToolExecutionContext(student_id="student-001"),
    )

    tree = result["prerequisites"]["expression"]
    assert tree["type"] == "AND"
    assert tree["children"][0]["type"] == "OR"
    assert tree["children"][0]["children"][1] == {
        "type": "NOT",
        "operand": {
            "type": "COURSE_PASSED",
            "course_id": "R23:CAIE:CSE121",
            "course_code": "CSE121",
        },
    }
    assert tree["children"][1] == {"type": "MIN_GPA", "minimum": 2.5}
    assert tree["children"][2]["type"] == "UNSUPPORTED"
    assert tree["children"][2]["source_type"] == "UNRESOLVED_CONDITION"
    assert tree["children"][2]["supported"] is False
    assert result["coverage"]["prerequisites"] == "UNSUPPORTED"


@pytest.mark.parametrize(
    "course_attempts",
    [
        [],
        [
            {
                "student_id": "student-001",
                "course_id": "R23:CAIE:CSE141",
                "attempt_number": 1,
                "term": "Fall",
                "academic_year": 2024,
                "status": "recorded",
                "passed": True,
                "failed": False,
                "withdrawn": False,
                "repeated": False,
                "credits_earned": 3,
            }
        ],
        [
            {
                "student_id": "student-001",
                "course_id": "R23:CAIE:CSE221",
                "attempt_number": 1,
                "term": "Fall",
                "academic_year": 2024,
                "status": "recorded",
                "passed": False,
                "failed": True,
                "withdrawn": False,
                "repeated": False,
                "credits_earned": 0,
            }
        ],
    ],
)
def test_static_course_information_does_not_depend_on_student_history(
    tmp_path,
    course_attempts: list[dict[str, object]],
) -> None:
    result = _tool(tmp_path, course_attempts=course_attempts).execute(
        {"course_code": "CSE221"},
        ToolExecutionContext(student_id="student-001"),
    )

    assert result["course"]["identity"] == "R23:CAIE:CSE221"
    assert result["prerequisites"]["expression"]["type"] == "AND"


def test_incomplete_prerequisite_row_is_not_presented_as_no_prerequisites(
    tmp_path,
) -> None:
    diagnostic = AcademicDataDiagnostic(
        code=AcademicDataDiagnosticCode.ELIGIBILITY_COVERAGE_GAP,
        reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
        course_id=TARGET,
        field="prerequisites",
        detail="No formal no-prerequisite signal is available",
        requires_human_review=True,
    )
    data = FakeAcademicData(
        (_course(),),
        _rule_set(
            status=RuleSetStatus.INCOMPLETE,
            reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
            include_rule=False,
        ),
        rule_diagnostics=(diagnostic,),
    )

    result = _tool(tmp_path, academic_data=data).execute(
        {"course_code": "CSE221"},
        ToolExecutionContext(student_id="student-001"),
    )

    assert result["coverage"]["prerequisites"] == "INCOMPLETE"
    assert result["prerequisites"]["rules"] == []
    assert result["prerequisites"]["expression"] is None
    assert result["prerequisites"]["reason_codes"] == ["MISSING_REQUIRED_DATA"]
    assert result["corequisites"]["status"] == "UNAVAILABLE"
    assert "no prerequisites" not in json.dumps(result).lower()


def test_empty_corequisite_artifact_is_explicitly_unavailable_not_absent(
    tmp_path,
) -> None:
    result = _tool(tmp_path).execute(
        {"course_code": "CSE221"},
        ToolExecutionContext(student_id="student-001"),
    )

    assert result["coverage"]["corequisites"] == "UNAVAILABLE"
    assert result["corequisites"]["rules"] == []
    assert result["corequisites"]["reason"] == (
        "Complete typed corequisite information is not available "
        "through the Academic Data adapter."
    )


@pytest.mark.parametrize(
    ("regulation", "program", "identity"),
    [
        (2023, "CAIE", "R23:CAIE:CSE221"),
        (2018, "CESS", "R18:CESS:CSE221"),
    ],
)
def test_trusted_regulation_and_program_scope_is_preserved(
    tmp_path,
    regulation: int,
    program: str,
    identity: str,
) -> None:
    scoped_identity = CourseIdentity.parse(identity)
    result = _tool(
        tmp_path,
        regulation=regulation,
        program=program,
        academic_data=FakeAcademicData(
            (_course(scoped_identity),),
            _rule_set(scoped_identity),
        ),
    ).execute(
        {"course_code": "CSE221"},
        ToolExecutionContext(student_id="student-001"),
    )

    assert result["course"]["identity"] == identity
    assert result["course"]["regulation"] == (
        "R23" if regulation == 2023 else "R18"
    )


def test_missing_context_and_argument_overrides_are_rejected(tmp_path) -> None:
    tool = _tool(tmp_path)

    with pytest.raises(ToolContextRequiredError):
        tool.execute({"course_code": "CSE221"}, ToolExecutionContext())

    with pytest.raises(ToolArgumentValidationError):
        tool.execute(
            {
                "course_code": "CSE221",
                "student_id": "forged",
                "regulation": 2018,
                "program": "FORGED",
                "gpa": 4.0,
                "credits": 200,
            },
            ToolExecutionContext(student_id="student-001"),
        )


def test_invalid_course_code_is_rejected_without_cross_scope_lookup(tmp_path) -> None:
    tool = _tool(tmp_path)

    with pytest.raises(ToolArgumentValidationError):
        tool.execute(
            {"course_code": "!!!"},
            ToolExecutionContext(student_id="student-001"),
        )
