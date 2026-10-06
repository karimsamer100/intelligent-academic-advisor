from __future__ import annotations

import json

from app.planning.domain.academic_state import FactStatus
from app.planning.domain.audit import (
    CourseRequirementEvidence,
    DegreeAuditResult,
    DegreeAuditStatus,
    RequirementEvaluation,
)
from app.planning.domain.conditions import CourseMustBePassedCondition
from app.planning.domain.course import CourseIdentity
from app.planning.domain.eligibility import (
    EligibilityResult,
    EligibilityStatus,
    RuleSetStatus,
)
from app.planning.domain.evaluation import EvaluationOutcome, RuleEvaluationResult
from app.planning.domain.program_progress import (
    ProgramProgress,
    RequirementCountProgress,
)
from app.planning.domain.provenance import Provenance
from app.planning.domain.reasons import ReasonCode
from app.planning.domain.requirements import RequirementSetStatus
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
from app.tools.projections import (
    DEGREE_AUDIT_PROJECTION_MAX_CHARS,
    project_degree_audit,
    project_eligibility,
)


TARGET = CourseIdentity.parse("R23:CAIE:CSE221")
PREREQUISITE = CourseIdentity.parse("R23:CAIE:CSE121")


def _trace(
    *,
    node_id: str,
    code: TraceCode,
    status: DecisionStatus,
    subject: CourseIdentity | None = None,
    children: tuple[DecisionTraceNode, ...] = (),
    provenance: tuple[Provenance, ...] = (),
) -> DecisionTrace:
    return DecisionTrace(
        DecisionTraceNode(
            node_id=node_id,
            code=code,
            node_type=(
                TraceNodeType.ROOT
                if not children
                else TraceNodeType.LOGICAL
            ),
            status=status,
            subject=subject,
            children=children,
            provenance=provenance,
        )
    )


def _metadata(
    trace: DecisionTrace,
    *,
    provenance: tuple[Provenance, ...] = (),
    reasons: tuple[ReasonCode, ...] = (),
    requires_human_review: bool = False,
) -> ResultMetadata:
    return ResultMetadata(
        dataset_version=DatasetVersion("projection-test"),
        execution_mode=ExecutionMode.DEVELOPMENT,
        authoritative=False,
        reason_codes=reasons,
        provenance=provenance,
        decision_trace=trace,
        requires_human_review=requires_human_review,
    )


def _eligibility_result() -> EligibilityResult:
    provenance = Provenance(
        rule_id="R23-PR-CSE221",
        source_id="SRC-BYLAW",
        source_page=161,
    )
    missing = DecisionTraceNode(
        node_id="prerequisite",
        code=TraceCode.COURSE_PASSED,
        node_type=TraceNodeType.COURSE_CHECK,
        status=DecisionStatus.FAILED,
        subject=PREREQUISITE,
        reason_codes=(ReasonCode.MISSING_PREREQUISITE,),
        provenance=(provenance,),
    )
    trace = _trace(
        node_id="eligibility",
        code=TraceCode.ELIGIBILITY,
        status=DecisionStatus.FAILED,
        subject=TARGET,
        children=(missing,),
        provenance=(provenance,),
    )
    metadata = _metadata(
        trace,
        provenance=(provenance,),
        reasons=(ReasonCode.MISSING_PREREQUISITE,),
    )
    rule = RuleEvaluationResult(
        rule_id="R23-PR-CSE221",
        outcome=EvaluationOutcome.UNSATISFIED,
        metadata=_metadata(
            trace,
            provenance=(provenance,),
            reasons=(ReasonCode.MISSING_PREREQUISITE,),
        ),
    )
    return EligibilityResult(
        target_course=TARGET,
        status=EligibilityStatus.NOT_ELIGIBLE,
        eligible=False,
        rule_set_status=RuleSetStatus.COMPLETE,
        metadata=metadata,
        rule_results=(rule,),
        conditions=(CourseMustBePassedCondition(PREREQUISITE, "R23-PR-CSE221"),),
    )


def _audit_result(requirement_count: int = 30) -> DegreeAuditResult:
    provenance = Provenance(source_id="SRC-AUDIT", source_page=84)
    root_children = []
    requirements = []
    for index in range(requirement_count):
        course = CourseIdentity.parse(f"R23:CAIE:CSE{100 + index}")
        node = DecisionTraceNode(
            node_id=f"requirement-{index}",
            code=TraceCode.REQUIREMENT,
            node_type=TraceNodeType.REQUIREMENT_CHECK,
            status=DecisionStatus.INDETERMINATE,
            subject=course,
            provenance=(provenance,),
        )
        root_children.append(node)
        requirement_trace = DecisionTrace(node)
        requirement_metadata = _metadata(
            requirement_trace,
            provenance=(provenance,),
            reasons=(ReasonCode.MISSING_REQUIRED_DATA,),
            requires_human_review=True,
        )
        requirements.append(
            RequirementEvaluation(
                requirement_id=f"REQ-{index:03d}",
                definition_type="COURSE_COMPLETION",
                outcome=EvaluationOutcome.INDETERMINATE,
                metadata=requirement_metadata,
                evidence=CourseRequirementEvidence(
                    course=course,
                    pass_status=FactStatus.UNKNOWN,
                    registration_status=FactStatus.UNKNOWN,
                ),
            )
        )

    audit_trace = _trace(
        node_id="degree-audit",
        code=TraceCode.DEGREE_AUDIT,
        status=DecisionStatus.ADVISOR_REVIEW,
        children=tuple(root_children),
        provenance=(provenance,),
    )
    metadata = _metadata(
        audit_trace,
        provenance=(provenance,),
        reasons=(ReasonCode.MISSING_REQUIRED_DATA,),
        requires_human_review=True,
    )
    progress = ProgramProgress(
        earned_credit_hours=60,
        required_program_credits=144,
        remaining_known_credits=84,
        core_requirements=RequirementCountProgress(
            satisfied_count=5,
            total_known_count=10,
            unknown_count=2,
        ),
        zero_credit_requirements=RequirementCountProgress(0, 0),
        outstanding_requirement_ids=tuple(
            f"REQ-{index:03d}" for index in range(requirement_count)
        ),
        unknown_requirement_ids=tuple(
            f"REQ-{index:03d}" for index in range(requirement_count)
        ),
        review_requirement_ids=tuple(
            f"REQ-{index:03d}" for index in range(requirement_count)
        ),
    )
    return DegreeAuditResult(
        status=DegreeAuditStatus.HUMAN_REVIEW_REQUIRED,
        requirement_set_status=RequirementSetStatus.INCOMPLETE,
        metadata=metadata,
        requirement_results=tuple(requirements),
        progress=progress,
    )


def test_eligibility_projection_preserves_decision_requirements_and_citations() -> None:
    result = _eligibility_result()
    projection = project_eligibility(result)

    assert projection["decision"] == result.to_dict()["decision"]
    assert projection["eligible"] == result.eligible
    assert projection["authoritative"] is False
    assert projection["requires_human_review"] is False
    assert projection["missing_requirements"] == [
        {"type": "COURSE_PASSED", "course_code": "CSE121"},
    ]
    assert projection["conditions"] == [
        {"type": "COURSE_MUST_BE_PASSED", "course_code": "CSE121"}
    ]
    assert projection["citations"] == [
        {"source_id": "SRC-BYLAW", "page": 161, "rule_id": "R23-PR-CSE221"}
    ]
    assert "decision_trace" not in projection
    assert "metadata" not in projection
    assert "decision_trace" in result.to_dict()["metadata"]
    assert len(json.dumps(projection, separators=(",", ":"))) < 2500


def test_degree_audit_projection_preserves_progress_and_is_bounded() -> None:
    result = _audit_result()
    full_size = len(json.dumps(result.to_dict(), separators=(",", ":")))
    projection = project_degree_audit(result)
    projection_size = len(json.dumps(projection, separators=(",", ":")))

    assert full_size > DEGREE_AUDIT_PROJECTION_MAX_CHARS
    assert projection_size <= DEGREE_AUDIT_PROJECTION_MAX_CHARS
    assert projection["status"] == result.status.value
    assert projection["authoritative"] == result.authoritative
    assert projection["requires_human_review"] is True
    assert projection["credits"] == {
        "completed": 60,
        "required": 144,
        "remaining": 84,
    }
    assert projection["mandatory_missing_courses"][:2] == ["CSE100", "CSE101"]
    assert projection["requirements"]["total_count"] == 30
    assert projection["requirements"]["review_ids"]
    assert projection["citations"] == [
        {"source_id": "SRC-AUDIT", "page": 84}
    ]
    assert "decision_trace" not in projection
    assert "metadata" not in projection
    assert "decision_trace" in result.to_dict()["metadata"]
    assert projection["status"] == result.to_dict()["status"]
