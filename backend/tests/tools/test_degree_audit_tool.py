from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import pytest

from app.planning.audit.service import DegreeAuditService
from app.planning.domain.audit import DegreeAuditRequest, DegreeAuditResult, DegreeAuditStatus
from app.planning.domain.program_progress import ProgramProgress, RequirementCountProgress
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
from app.planning.domain.requirements import (
    ProgramRequirementSet,
    RequirementSetStatus,
    RequirementStage,
)
from app.planning.domain.version import DatasetVersion
from app.planning.eligibility.service import EligibilityService
from app.planning.engine import PlanningEngine
from app.planning.policy import ExecutionMode, ExecutionPolicy
from app.planning.repositories.adapters.student_json_repository import (
    JsonStudentRepository,
)
from app.planning.rules.evaluator import RuleEvaluator
from app.services.planning_service import PlanningService
from app.tools.context import ToolExecutionContext
from app.tools.degree_audit import DegreeAuditTool
from app.tools.errors import (
    ToolContextRequiredError,
    ToolDataUnavailableError,
    ToolExecutionError,
)
from app.tools.registry import ToolRegistry


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
class FakePlanningService:
    result: DegreeAuditResult
    requests: list[DegreeAuditRequest] = field(default_factory=list)

    def audit(self, request: DegreeAuditRequest) -> DegreeAuditResult:
        self.requests.append(request)
        return self.result


class RaisingAuditPlanningService(FakePlanningService):
    def __init__(self, error: Exception) -> None:
        super().__init__(_audit_result())
        self.error = error

    def audit(self, request: DegreeAuditRequest) -> DegreeAuditResult:
        self.requests.append(request)
        raise self.error


def _audit_result() -> DegreeAuditResult:
    trace = DecisionTrace(
        DecisionTraceNode(
            node_id="audit",
            code=TraceCode.DEGREE_AUDIT,
            node_type=TraceNodeType.ROOT,
            status=DecisionStatus.ADVISOR_REVIEW,
        )
    )
    metadata = ResultMetadata(
        dataset_version=DatasetVersion("audit-tool-test"),
        execution_mode=ExecutionMode.DEVELOPMENT,
        authoritative=False,
        reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
        provenance=(Provenance(source_id="SRC-AUDIT", source_page=11),),
        decision_trace=trace,
        requires_human_review=True,
    )
    progress = ProgramProgress(
        earned_credit_hours=0,
        required_program_credits=144,
        remaining_known_credits=144,
        core_requirements=RequirementCountProgress(0, 0),
        zero_credit_requirements=RequirementCountProgress(0, 0),
    )
    return DegreeAuditResult(
        status=DegreeAuditStatus.HUMAN_REVIEW_REQUIRED,
        requirement_set_status=RequirementSetStatus.INCOMPLETE,
        metadata=metadata,
        requirement_results=(),
        progress=progress,
    )


def _tool(
    tmp_path,
    *,
    requirement_status=RequirementSetStatus.INCOMPLETE,
    academic_data=None,
    planning_service=None,
):
    academic_data = academic_data or FakeAcademicData(_requirement_set(requirement_status))
    planning_service = planning_service or FakePlanningService(_audit_result())
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
    for field_name in (
        "student_id",
        "regulation",
        "program",
        "gpa",
        "earned_credit_hours",
        "course_history",
        "requirement_sets",
        "elective_pools",
    ):
        assert field_name not in schema.get("properties", {})


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
    assert result["status"] == "HUMAN_REVIEW_REQUIRED"
    assert result["requirement_set_status"] == "INCOMPLETE"
    assert result["credits"] == {
        "completed": 0,
        "required": 144,
        "remaining": 144,
    }
    assert result["requires_human_review"] is True
    assert "decision_trace" not in result


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


@pytest.mark.parametrize("error_type", [AttributeError, TypeError])
def test_unexpected_degree_audit_errors_use_safe_registry_path(
    tmp_path,
    caplog,
    error_type: type[Exception],
) -> None:
    tool, _, _ = _tool(
        tmp_path,
        planning_service=RaisingAuditPlanningService(
            error_type("synthetic programming bug")
        ),
    )
    registry = ToolRegistry([tool])

    with caplog.at_level(logging.ERROR, logger="app.tools.registry"):
        with pytest.raises(ToolExecutionError) as raised:
            registry.execute(
                "degree_audit",
                {},
                ToolExecutionContext(student_id="student-001"),
            )

    assert str(raised.value) == "Tool 'degree_audit' failed to produce a valid result"
    assert "synthetic programming bug" not in str(raised.value)
    assert "tool execution failed" in caplog.text
    assert any(
        record.exc_info and isinstance(record.exc_info[1], error_type)
        for record in caplog.records
    )
