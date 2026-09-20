import pytest

from app.planning.domain.course import (
    Course,
    CourseIdentity,
    Program,
    Regulation,
)
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.domain.requirements import ProgramRequirement
from app.planning.domain.rules import AcademicRule
from app.planning.domain.student import StudentState
from app.planning.repositories.course_repository import CourseRepository
from app.planning.repositories.requirement_repository import (
    RequirementRepository,
)
from app.planning.repositories.rule_repository import RuleRepository
from app.planning.repositories.student_repository import StudentRepository


def test_domain_records_supply_repository_return_types() -> None:
    identity = CourseIdentity.parse("R23:CAIE:CSE341")
    course = Course(
        identity=identity,
        course_name="Algorithms",
        credit_hours=3,
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    rule = AcademicRule(
        rule_id="R23-PR-CSE341",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    requirement = ProgramRequirement(
        requirement_id="R23-CORE-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    student = StudentState(
        student_id="student-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        completed_courses=frozenset({identity}),
    )

    assert course.identity == identity
    assert rule.program == Program("CAIE")
    assert requirement.regulation is Regulation.R23
    assert identity in student.completed_courses


def test_repository_protocols_expose_only_domain_oriented_contracts() -> None:
    assert callable(CourseRepository.get_course)
    assert callable(CourseRepository.list_courses)
    assert callable(RuleRepository.get_rule)
    assert callable(RuleRepository.list_rules)
    assert callable(RequirementRepository.list_requirements)
    assert callable(RequirementRepository.get_requirement_set)
    assert callable(StudentRepository.get_student_state)


def test_minimal_domain_records_validate_nested_contract_types() -> None:
    with pytest.raises(TypeError):
        AcademicRule(
            rule_id="R23-PR-CSE341",
            regulation=Regulation.R23,
            program=Program("CAIE"),
            approval_status=ApprovalStatus.APPROVED,
            verification_status=VerificationStatus.SOURCE_VERIFIED,
            provenance=object(),  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError):
        StudentState(
            student_id="student-001",
            regulation=Regulation.R23,
            program=Program("CAIE"),
            completed_courses={"R23:CAIE:CSE341"},  # type: ignore[arg-type]
        )
