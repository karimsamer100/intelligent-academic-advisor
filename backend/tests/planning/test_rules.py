from app.planning.domain.course import CourseIdentity, Program, Regulation
from app.planning.domain.expressions import CoursePassedExpression
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.domain.provenance import Provenance
from app.planning.domain.rules import AcademicRule


def test_academic_rule_keeps_expression_separate_from_governance_metadata() -> None:
    expression = CoursePassedExpression(CourseIdentity.parse("R23:CAIE:CSE241"))
    provenance = Provenance(source_id="SRC-2023", source_page=12)

    rule = AcademicRule(
        rule_id="R23-PR-CSE341",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        critical_for_planner=True,
        provenance=provenance,
        expression=expression,
    )

    assert rule.expression is expression
    assert rule.provenance is provenance
    assert rule.critical_for_planner is True
