from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from app.planning.audit.service import DegreeAuditService
from app.planning.domain.audit import DegreeAuditRequest
from app.planning.domain.requirements import (
    ProgramRequirementSet,
    RequirementSetStatus,
    RequirementStage,
)
from app.planning.domain.version import DatasetVersion
from app.planning.eligibility.service import EligibilityService
from app.planning.engine import PlanningEngine
from app.planning.policy import ExecutionPolicy
from app.planning.repositories.adapters.student_json_repository import (
    JsonStudentRepository,
)
from app.planning.rules.evaluator import RuleEvaluator
from app.services.planning_service import PlanningService
from app.tools.context import ToolExecutionContext
from app.tools.degree_audit import DegreeAuditTool
from app.tools.errors import ToolContextRequiredError, ToolDataUnavailableError


def _student_repository(tmp_path, student_id: str = "student-001") -> JsonStudentRepository:
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


def _requirement_set(
    status: RequirementSetStatus = RequirementSetStatus.INCOMPLETE,
) -> ProgramRequirementSet:
    from app.planning.domain.course import Program, Regulation

    return ProgramRequirementSet(
        regulation=Regulation.R23,
        program=Program("CAIE"),
        requirements=(),
        status=status,
        dataset_version=DatasetVersion("audit-test"),
    )


@dataclass
class FakeAcademicData:
    requirement_set: ProgramRequirementSet
    pools: tuple = ()
    calls: list[tuple[str, object]] = field(default_factory=list)

    def get_requirement_set(self, *, regulation, program, stage):
        self.calls.append(("requirement_set", (regulation, program, stage)))
        return self.requirement_set

    def list_elective_pools(self, *, regulation, program):
        self.calls.append(("elective_pools", (regulation, program)))
        return self.pools


@dataclass
class FakeAuditResult:
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return self.payload


@dataclass
class FakePlanningService:
    result: FakeAuditResult
    requests: list[DegreeAuditRequest] = field(default_factory=list)

    def audit(self, request: DegreeAuditRequest) -> FakeAuditResult:
        self.requests.append(request)
        return self.result


def _tool(tmp_path, *, requirement_status=RequirementSetStatus.INCOMPLETE):
    academic_data = FakeAcademicData(_requirement_set(requirement_status))
    planning_service = FakePlanningService(FakeAuditResult({"status": "review"}))
    tool = DegreeAuditTool(
        student_repository=_student_repository(tmp_path),
        academic_data=academic_data,
        planning_service=planning_service,
    )
    return tool, academic_data, planning_service


def test_degree_audit_schema_exposes_no_trusted_student_fields(tmp_path) -> None:
    tool, _, _ = _tool(tmp_path)

    schema = tool.definition.input_schema

    assert schema.get("properties", {}) == {}
    assert "required" not in schema
    for field in (
        "student_id",
        "regulation",
        "program",
        "gpa",
        "earned_credit_hours",
        "course_history",
        "requirement_sets",
        "elective_pools",
    ):
        assert field not in schema.get("properties", {})


def test_degree_audit_uses_trusted_scope_and_program_completion_stage(tmp_path) -> None:
    tool, academic_data, planning_service = _tool(tmp_path)

    result = tool.execute({}, ToolExecutionContext(student_id="student-001"))

    request = planning_service.requests[0]
    assert request.student.student_id == "student-001"
    assert request.student.regulation.value == "R23"
    assert request.student.program.value == "CAIE"
    assert request.stage is RequirementStage.PROGRAM_COMPLETION
    assert request.program_facts.coverage.value == "UNAVAILABLE"
    assert [call[0] for call in academic_data.calls] == [
        "requirement_set",
        "elective_pools",
    ]
    assert result == {"status": "review"}


def test_degree_audit_requires_trusted_student_context(tmp_path) -> None:
    tool, _, planning_service = _tool(tmp_path)

    with pytest.raises(ToolContextRequiredError):
        tool.execute({}, ToolExecutionContext())

    assert planning_service.requests == []


def test_degree_audit_fails_closed_for_unavailable_student(tmp_path) -> None:
    tool, _, planning_service = _tool(tmp_path)

    with pytest.raises(ToolDataUnavailableError):
        tool.execute({}, ToolExecutionContext(student_id="missing-student"))

    assert planning_service.requests == []


def test_degree_audit_fails_closed_for_unavailable_requirement_data(tmp_path) -> None:
    tool, _, planning_service = _tool(
        tmp_path,
        requirement_status=RequirementSetStatus.UNAVAILABLE,
    )

    with pytest.raises(ToolDataUnavailableError):
        tool.execute({}, ToolExecutionContext(student_id="student-001"))

    assert planning_service.requests == []


def test_incomplete_requirement_coverage_remains_reviewable(tmp_path) -> None:
    version = DatasetVersion("audit-test")
    policy = ExecutionPolicy.development()
    planning_service = PlanningService(
        PlanningEngine(
            eligibility_service=EligibilityService(
                RuleEvaluator(policy, version)
            ),
            degree_audit_service=DegreeAuditService(policy, version),
        )
    )
    tool = DegreeAuditTool(
        student_repository=_student_repository(tmp_path),
        academic_data=FakeAcademicData(_requirement_set()),
        planning_service=planning_service,
    )

    result = tool.execute({}, ToolExecutionContext(student_id="student-001"))

    assert result["requirement_set_status"] == "INCOMPLETE"
    assert result["status"] == "HUMAN_REVIEW_REQUIRED"
    assert result["requires_human_review"] is True
    assert result["authoritative"] is False
