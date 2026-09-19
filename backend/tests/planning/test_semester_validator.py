from __future__ import annotations

import pytest

from backend.app.planning.domain.academic_state import (
    AcademicHistoryCoverage,
    RegistrationCoverage,
)
from backend.app.planning.domain.context import EvaluationHorizon, RegistrationIntent
from backend.app.planning.domain.course import (
    Course,
    CourseIdentity,
    Program,
    Regulation,
)
from backend.app.planning.domain.eligibility import (
    CourseEligibilityRuleSet,
    EligibilityDecision,
    RuleSetStatus,
)
from backend.app.planning.domain.expressions import (
    CourseConcurrentExpression,
    CoursePassedExpression,
    OrExpression,
)
from backend.app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from backend.app.planning.domain.rules import AcademicRule
from backend.app.planning.domain.student import StudentState
from backend.app.planning.domain.version import DatasetVersion
from backend.app.planning.policy import ExecutionPolicy
from backend.app.planning.eligibility.service import EligibilityService
from backend.app.planning.rules.evaluator import RuleEvaluator
from backend.app.planning.semester.service import SemesterValidator
from backend.app.planning.domain.semester import (
    LoadBand,
    ProposedCourse,
    ProposedSemester,
    SemesterLoadPolicy,
    SemesterValidationRequest,
    SemesterValidationStatus,
    TermType,
)


R23 = Regulation.R23
CAIE = Program("CAIE")
VERSION = DatasetVersion("semester-test")


def identity(code: str) -> CourseIdentity:
    return CourseIdentity(R23, CAIE, code)


def course(code: str, credits: int | float = 3) -> Course:
    return Course(
        identity(code),
        f"Course {code}",
        credits,
        ApprovalStatus.APPROVED,
        VerificationStatus.SOURCE_VERIFIED,
    )


def student(
    *,
    passed: tuple[CourseIdentity, ...] = (),
    current: tuple[CourseIdentity, ...] = (),
    failed: tuple[CourseIdentity, ...] = (),
    gpa: float | None = 3.0,
) -> StudentState:
    return StudentState(
        student_id="semester-student",
        regulation=R23,
        program=CAIE,
        passed_courses=frozenset(passed),
        current_courses=frozenset(current),
        failed_courses=frozenset(failed),
        gpa=gpa,
        history_coverage=AcademicHistoryCoverage.COMPLETE,
        registration_coverage=RegistrationCoverage.COMPLETE,
    )


def rule_set(
    target: CourseIdentity,
    expression=None,
    *,
    status: RuleSetStatus = RuleSetStatus.COMPLETE,
) -> CourseEligibilityRuleSet:
    rules = ()
    if expression is not None:
        rules = (
            AcademicRule(
                rule_id=f"PR-{target.course_code}",
                regulation=R23,
                program=CAIE,
                approval_status=ApprovalStatus.APPROVED,
                verification_status=VerificationStatus.SOURCE_VERIFIED,
                critical_for_planner=True,
                expression=expression,
            ),
        )
    return CourseEligibilityRuleSet(target, status, rules)


def validator() -> SemesterValidator:
    evaluator = RuleEvaluator(ExecutionPolicy.development(), VERSION)
    return SemesterValidator(EligibilityService(evaluator))


def request(
    entries: tuple[ProposedCourse, ...],
    rule_sets: tuple[CourseEligibilityRuleSet, ...] = (),
    *,
    gpa: float | None = 3.0,
    term_type: TermType = TermType.MAIN,
    horizon: EvaluationHorizon = EvaluationHorizon.PROJECTED,
    load_policy: SemesterLoadPolicy | None = None,
) -> SemesterValidationRequest:
    return SemesterValidationRequest(
        student=student(gpa=gpa),
        semester=ProposedSemester(term_type, entries),
        rule_sets=rule_sets,
        load_policy=load_policy or SemesterLoadPolicy.regulation_23(),
        horizon=horizon,
    )


def test_one_valid_course_produces_valid_semester() -> None:
    target = course("CSE341")

    result = validator().validate(
        request((ProposedCourse(target),), (rule_set(target.identity),))
    )

    assert result.status is SemesterValidationStatus.VALID
    assert result.course_results[0].eligibility.decision is EligibilityDecision.ELIGIBLE
    assert result.load_result.total_credit_hours == 3


def test_empty_proposed_semester_is_valid_when_zero_load_is_allowed() -> None:
    result = validator().validate(request((), ()))

    assert result.status is SemesterValidationStatus.VALID
    assert result.load_result.course_count == 0
    assert result.load_result.total_credit_hours == 0


def test_definitely_ineligible_course_invalidates_semester() -> None:
    target = course("CSE341")
    prerequisite = identity("CSE241")

    result = validator().validate(
        request(
            (ProposedCourse(target),),
            (rule_set(target.identity, CoursePassedExpression(prerequisite)),),
        )
    )

    assert result.status is SemesterValidationStatus.INVALID
    assert (
        result.course_results[0].eligibility.decision is EligibilityDecision.INELIGIBLE
    )


def test_projected_in_progress_prerequisite_is_conditional() -> None:
    target = course("CSE342")
    prerequisite = identity("CSE241")
    request_value = SemesterValidationRequest(
        student=student(current=(prerequisite,)),
        semester=ProposedSemester(TermType.MAIN, (ProposedCourse(target),)),
        rule_sets=(rule_set(target.identity, CoursePassedExpression(prerequisite)),),
        load_policy=SemesterLoadPolicy.regulation_23(),
        horizon=EvaluationHorizon.PROJECTED,
    )

    result = validator().validate(request_value)

    assert result.status is SemesterValidationStatus.CONDITIONAL
    assert result.conditions


def test_same_term_concurrent_prerequisite_is_evaluated_through_eligibility() -> None:
    target = course("CSE493")
    prerequisite = course("CSE392")
    expression = OrExpression(
        (
            CoursePassedExpression(prerequisite.identity),
            CourseConcurrentExpression(prerequisite.identity),
        )
    )

    result = validator().validate(
        request(
            (ProposedCourse(prerequisite), ProposedCourse(target)),
            (
                rule_set(prerequisite.identity),
                rule_set(target.identity, expression),
            ),
        )
    )

    assert result.status is SemesterValidationStatus.VALID


def test_current_registration_is_not_same_term_concurrency() -> None:
    target = course("CSE493")
    prerequisite = course("CSE392")
    expression = CourseConcurrentExpression(prerequisite.identity)

    result = validator().validate(
        SemesterValidationRequest(
            student=student(current=(prerequisite.identity,)),
            semester=ProposedSemester(TermType.MAIN, (ProposedCourse(target),)),
            rule_sets=(rule_set(target.identity, expression),),
            load_policy=SemesterLoadPolicy.regulation_23(),
            horizon=EvaluationHorizon.PROJECTED,
        )
    )

    assert result.status is SemesterValidationStatus.INVALID


def test_duplicate_courses_are_detected_without_inflating_load() -> None:
    target = course("CSE341")

    result = validator().validate(
        request(
            (ProposedCourse(target), ProposedCourse(target)),
            (rule_set(target.identity),),
        )
    )

    assert result.status is SemesterValidationStatus.INVALID
    assert result.load_result.course_count == 1
    assert result.load_result.total_credit_hours == 3


def test_duplicate_payload_order_does_not_change_validation_result() -> None:
    target = course("CSE341")
    lower_credit = ProposedCourse(target, credit_hours=3)
    higher_credit = ProposedCourse(target, credit_hours=9)
    rules = (rule_set(target.identity),)

    forward = validator().validate(request((higher_credit, lower_credit), rules))
    reverse = validator().validate(request((lower_credit, higher_credit), rules))

    assert forward.to_dict() == reverse.to_dict()
    assert forward.load_result.total_credit_hours == 3


def test_improvement_retake_remains_advisor_review() -> None:
    target = course("CSE341")

    result = validator().validate(
        SemesterValidationRequest(
            student=student(passed=(target.identity,)),
            semester=ProposedSemester(
                TermType.MAIN,
                (
                    ProposedCourse(
                        target,
                        registration_intent=RegistrationIntent.RETAKE_FOR_IMPROVEMENT,
                    ),
                ),
            ),
            rule_sets=(rule_set(target.identity),),
            load_policy=SemesterLoadPolicy.regulation_23(),
        )
    )

    assert result.status is SemesterValidationStatus.HUMAN_REVIEW_REQUIRED


def test_retake_after_failure_is_evaluated_as_a_distinct_intent() -> None:
    target = course("CSE341")

    result = validator().validate(
        SemesterValidationRequest(
            student=student(failed=(target.identity,)),
            semester=ProposedSemester(
                TermType.MAIN,
                (
                    ProposedCourse(
                        target,
                        registration_intent=RegistrationIntent.RETAKE_AFTER_FAILURE,
                    ),
                ),
            ),
            rule_sets=(rule_set(target.identity),),
            load_policy=SemesterLoadPolicy.regulation_23(),
        )
    )

    assert result.status is SemesterValidationStatus.VALID
    assert (
        result.course_results[0].proposed_course.registration_intent
        is RegistrationIntent.RETAKE_AFTER_FAILURE
    )


def test_unknown_gpa_makes_load_validation_unresolved() -> None:
    target = course("CSE341")

    result = validator().validate(
        request(
            (ProposedCourse(target),),
            (rule_set(target.identity),),
            gpa=None,
        )
    )

    assert result.status is SemesterValidationStatus.HUMAN_REVIEW_REQUIRED
    assert result.load_result.status is SemesterValidationStatus.HUMAN_REVIEW_REQUIRED


def test_unknown_course_credits_make_load_validation_unresolved() -> None:
    target = course("CSE341")

    result = validator().validate(
        request(
            (ProposedCourse(target, credit_hours_known=False),),
            (rule_set(target.identity),),
        )
    )

    assert result.status is SemesterValidationStatus.HUMAN_REVIEW_REQUIRED
    assert result.load_result.total_credit_hours is None


def test_blocked_course_does_not_produce_authoritative_valid_semester() -> None:
    target = Course(
        identity("CSE341"),
        "Course CSE341",
        3,
        ApprovalStatus.BLOCKED,
        VerificationStatus.SOURCE_VERIFIED,
    )

    result = validator().validate(
        request((ProposedCourse(target),), (rule_set(target.identity),))
    )

    assert result.status is SemesterValidationStatus.HUMAN_REVIEW_REQUIRED
    assert result.metadata.authoritative is False


def test_mismatched_load_policy_scope_requires_review() -> None:
    target = course("CSE341")
    policy = SemesterLoadPolicy(
        policy_id="REG18_LOAD_POLICY",
        regulation=Regulation.R18,
        program=Program("CESS"),
        main_bands=(LoadBand("MAIN", None, None, 21, 8),),
        summer_bands=(LoadBand("SUMMER", None, None, 9, 3),),
        approval_status=ApprovalStatus.SOURCE_VERIFIED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )

    result = validator().validate(
        request(
            (ProposedCourse(target),), (rule_set(target.identity),), load_policy=policy
        )
    )

    assert result.status is SemesterValidationStatus.HUMAN_REVIEW_REQUIRED
    assert result.load_result.status is SemesterValidationStatus.HUMAN_REVIEW_REQUIRED
    assert result.metadata.authoritative is False


@pytest.mark.parametrize(
    ("course_count", "expected"),
    [(8, SemesterValidationStatus.VALID), (9, SemesterValidationStatus.INVALID)],
)
def test_regulation_23_main_load_uses_alternative_caps(
    course_count: int,
    expected: SemesterValidationStatus,
) -> None:
    entries = tuple(
        ProposedCourse(course(f"CSE{400 + index}")) for index in range(course_count)
    )
    rules = tuple(rule_set(entry.course.identity) for entry in entries)

    result = validator().validate(request(entries, rules))

    assert result.status is expected


@pytest.mark.parametrize(
    ("gpa", "course_count", "term_type", "expected"),
    [
        (2.999, 7, TermType.MAIN, SemesterValidationStatus.VALID),
        (2.999, 8, TermType.MAIN, SemesterValidationStatus.INVALID),
        (2.0, 7, TermType.MAIN, SemesterValidationStatus.VALID),
        (1.999, 5, TermType.MAIN, SemesterValidationStatus.VALID),
        (1.999, 6, TermType.MAIN, SemesterValidationStatus.INVALID),
        (3.0, 3, TermType.SUMMER, SemesterValidationStatus.VALID),
        (3.0, 4, TermType.SUMMER, SemesterValidationStatus.INVALID),
        (2.999, 2, TermType.SUMMER, SemesterValidationStatus.VALID),
        (2.999, 3, TermType.SUMMER, SemesterValidationStatus.INVALID),
    ],
)
def test_regulation_23_load_bands_are_selected_at_boundaries(
    gpa: float,
    course_count: int,
    term_type: TermType,
    expected: SemesterValidationStatus,
) -> None:
    entries = tuple(
        ProposedCourse(course(f"CSE{500 + index}")) for index in range(course_count)
    )
    rules = tuple(rule_set(entry.identity) for entry in entries)

    result = validator().validate(request(entries, rules, gpa=gpa, term_type=term_type))

    assert result.status is expected


def test_credit_alternative_can_allow_more_than_credit_cap() -> None:
    entries = tuple(ProposedCourse(course(f"CSE{600 + index}")) for index in range(7))
    rules = tuple(rule_set(entry.identity) for entry in entries)

    result = validator().validate(request(entries, rules, gpa=3.0))

    assert result.status is SemesterValidationStatus.VALID
    assert result.load_result.total_credit_hours == 21
