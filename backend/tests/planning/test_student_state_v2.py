from __future__ import annotations

import pytest

from app.planning.builders.student_state_builder import (
    StudentStateBuildInput,
    StudentStateBuilder,
)
from app.planning.domain.course import CourseIdentity, Program, Regulation
from app.planning.domain.evaluation import EvaluationOutcome
from app.planning.domain.expressions import (
    CourseCompletedExpression,
    CourseCurrentlyRegisteredExpression,
    CoursePassedExpression,
)
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.domain.reasons import ReasonCode
from app.planning.domain.rules import AcademicRule
from app.planning.domain.student import (
    AcademicHistoryCoverage,
    EffectiveCourseStatus,
    FactStatus,
    RegistrationCoverage,
)
from app.planning.domain.student_history import (
    AcademicSnapshot,
    AttemptOutcome,
    AttemptPurpose,
    CourseAttempt,
    CurrentRegistration,
)
from app.planning.domain.version import DatasetVersion
from app.planning.policy import ExecutionPolicy
from app.planning.rules.evaluator import RuleEvaluator


def _course(code: str) -> CourseIdentity:
    return CourseIdentity.parse(f"R23:CAIE:{code}")


def _attempt(
    course: CourseIdentity,
    *,
    attempt_number: int = 1,
    outcome: AttemptOutcome | None = None,
    purpose: AttemptPurpose | None = None,
    passed: bool | None = None,
    failed: bool | None = None,
    withdrawn: bool | None = None,
    repeated: bool | None = None,
    credits_earned: int | float | None = None,
) -> CourseAttempt:
    return CourseAttempt(
        student_id="student-001",
        course=course,
        attempt_number=attempt_number,
        term="Fall",
        academic_year=2024 + attempt_number,
        status="recorded",
        outcome=outcome,
        purpose=purpose,
        passed=passed,
        failed=failed,
        withdrawn=withdrawn,
        repeated=repeated,
        credits_earned=credits_earned,
    )


def _registration(course: CourseIdentity) -> CurrentRegistration:
    return CurrentRegistration(
        student_id="student-001",
        course=course,
        term="Fall",
        academic_year=2026,
        registration_status="REGISTERED",
    )


def _build(
    *attempts: CourseAttempt,
    current_registrations: tuple[CurrentRegistration, ...] = (),
    history_coverage: AcademicHistoryCoverage = AcademicHistoryCoverage.COMPLETE,
    registration_coverage: RegistrationCoverage = RegistrationCoverage.COMPLETE,
    academic_snapshot: AcademicSnapshot | None = None,
):
    result = StudentStateBuilder().build(
        StudentStateBuildInput(
            student_id="student-001",
            regulation=Regulation.R23,
            program=Program("CAIE"),
            course_attempts=attempts,
            current_registrations=current_registrations,
            history_coverage=history_coverage,
            registration_coverage=registration_coverage,
            academic_snapshot=academic_snapshot,
        )
    )
    assert result.student_state is not None, result.diagnostics
    return result


def _rule(expression: object) -> AcademicRule:
    return AcademicRule(
        rule_id="R23-TEST-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        expression=expression,  # type: ignore[arg-type]
    )


def _evaluate(expression: object, state: object):
    return RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("test-state-v2")
    ).evaluate(_rule(expression), state)  # type: ignore[arg-type]


def test_complete_empty_history_proves_course_not_passed_and_not_registered() -> None:
    course = _course("CSE141")
    state = _build().student_state

    assert state is not None
    assert state.pass_status(course) is FactStatus.KNOWN_FALSE
    assert state.registration_status(course) is FactStatus.KNOWN_FALSE
    assert state.effective_course_status(course) is EffectiveCourseStatus.NOT_ATTEMPTED


@pytest.mark.parametrize(
    "history_coverage",
    [AcademicHistoryCoverage.PARTIAL, AcademicHistoryCoverage.UNAVAILABLE],
)
def test_missing_attempt_under_noncomplete_history_is_unknown(
    history_coverage: AcademicHistoryCoverage,
) -> None:
    course = _course("CSE141")
    state = _build(history_coverage=history_coverage).student_state

    assert state is not None
    assert state.pass_status(course) is FactStatus.UNKNOWN
    assert state.effective_course_status(course) is EffectiveCourseStatus.UNKNOWN


@pytest.mark.parametrize(
    "registration_coverage",
    [RegistrationCoverage.PARTIAL, RegistrationCoverage.UNAVAILABLE],
)
def test_missing_registration_under_noncomplete_coverage_is_unknown(
    registration_coverage: RegistrationCoverage,
) -> None:
    course = _course("CSE141")
    state = _build(registration_coverage=registration_coverage).student_state

    assert state is not None
    assert state.registration_status(course) is FactStatus.UNKNOWN
    assert state.effective_course_status(course) is EffectiveCourseStatus.UNKNOWN


def test_failed_attempt_does_not_establish_effective_failure_under_partial_history() -> (
    None
):
    course = _course("CSE141")
    state = _build(
        _attempt(course, outcome=AttemptOutcome.FAILED),
        history_coverage=AcademicHistoryCoverage.PARTIAL,
    ).student_state

    assert state is not None
    record = state.course_record(course)
    assert record is not None
    assert record.has_failed_attempt is True
    assert record.pass_status is FactStatus.UNKNOWN
    assert record.effective_status is EffectiveCourseStatus.UNKNOWN


def test_passed_attempt_under_partial_history_is_historical_but_not_effective_truth() -> (
    None
):
    course = _course("CSE141")
    state = _build(
        _attempt(course, outcome=AttemptOutcome.PASSED, credits_earned=3),
        history_coverage=AcademicHistoryCoverage.PARTIAL,
    ).student_state

    assert state is not None
    record = state.course_record(course)
    assert record is not None
    assert record.has_passed_attempt is True
    assert record.pass_status is FactStatus.UNKNOWN
    assert record.effective_status is EffectiveCourseStatus.UNKNOWN


def test_failed_then_passed_derives_effective_pass_and_preserves_attempts() -> None:
    course = _course("CSE141")
    result = _build(
        _attempt(course, outcome=AttemptOutcome.FAILED, credits_earned=0),
        _attempt(
            course,
            attempt_number=2,
            outcome=AttemptOutcome.PASSED,
            purpose=AttemptPurpose.REPEAT,
            credits_earned=3,
        ),
    )
    state = result.student_state

    assert state is not None
    assert state.pass_status(course) is FactStatus.KNOWN_TRUE
    assert state.effective_course_status(course) is EffectiveCourseStatus.PASSED
    assert tuple(attempt.attempt_number for attempt in state.attempts_for(course)) == (
        1,
        2,
    )
    assert state.earned_credit_hours == 3


def test_explicit_improvement_failure_supersedes_previous_pass_for_effective_state() -> (
    None
):
    course = _course("CSE141")
    state = _build(
        _attempt(course, outcome=AttemptOutcome.PASSED, credits_earned=3),
        _attempt(
            course,
            attempt_number=2,
            outcome=AttemptOutcome.FAILED,
            purpose=AttemptPurpose.IMPROVEMENT,
            credits_earned=0,
        ),
    ).student_state

    assert state is not None
    assert state.pass_status(course) is FactStatus.KNOWN_FALSE
    assert state.effective_course_status(course) is EffectiveCourseStatus.FAILED
    assert state.passed_courses == frozenset()


def test_explicit_improvement_pass_preserves_effective_pass() -> None:
    course = _course("CSE141")
    state = _build(
        _attempt(course, outcome=AttemptOutcome.PASSED, credits_earned=3),
        _attempt(
            course,
            attempt_number=2,
            outcome=AttemptOutcome.PASSED,
            purpose=AttemptPurpose.IMPROVEMENT,
            credits_earned=3,
        ),
    ).student_state

    assert state is not None
    assert state.pass_status(course) is FactStatus.KNOWN_TRUE
    assert state.effective_course_status(course) is EffectiveCourseStatus.PASSED


def test_unknown_purpose_after_previous_pass_makes_effective_pass_unknown() -> None:
    course = _course("CSE141")
    result = _build(
        _attempt(course, outcome=AttemptOutcome.PASSED, credits_earned=3),
        _attempt(
            course,
            attempt_number=2,
            outcome=AttemptOutcome.FAILED,
            repeated=True,
            credits_earned=0,
        ),
    )

    assert result.student_state is not None
    assert result.student_state.pass_status(course) is FactStatus.UNKNOWN
    assert any(
        diagnostic.code.value == "REPEAT_SEMANTICS_UNRESOLVED"
        for diagnostic in result.diagnostics
    )


def test_withdrawn_and_incomplete_are_distinct_from_current_registration() -> None:
    withdrawn = _course("CSE141")
    incomplete = _course("CSE142")
    current = _course("CSE143")
    state = _build(
        _attempt(withdrawn, outcome=AttemptOutcome.WITHDRAWN),
        _attempt(incomplete, outcome=AttemptOutcome.INCOMPLETE),
        current_registrations=(_registration(current),),
    ).student_state

    assert state is not None
    assert state.effective_course_status(withdrawn) is EffectiveCourseStatus.WITHDRAWN
    assert state.effective_course_status(incomplete) is EffectiveCourseStatus.INCOMPLETE
    assert state.effective_course_status(current) is EffectiveCourseStatus.IN_PROGRESS
    assert state.pass_status(current) is FactStatus.KNOWN_FALSE


def test_pass_and_current_registration_are_independent_facts() -> None:
    course = _course("CSE141")
    state = _build(
        _attempt(course, outcome=AttemptOutcome.PASSED, credits_earned=3),
        current_registrations=(_registration(course),),
    ).student_state

    assert state is not None
    assert state.pass_status(course) is FactStatus.KNOWN_TRUE
    assert state.registration_status(course) is FactStatus.KNOWN_TRUE
    assert state.effective_course_status(course) is EffectiveCourseStatus.PASSED


def test_authoritative_snapshot_wins_over_derived_attempt_credits() -> None:
    course = _course("CSE141")
    snapshot = AcademicSnapshot(
        student_id="student-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        gpa=2.8,
        earned_credit_hours=60,
    )

    result = _build(
        _attempt(course, outcome=AttemptOutcome.PASSED, credits_earned=3),
        academic_snapshot=snapshot,
    )

    assert result.student_state is not None
    assert result.student_state.earned_credit_hours == 60
    assert any(
        diagnostic.code.value == "CREDIT_DATA_CONFLICT"
        for diagnostic in result.diagnostics
    )


def test_one_unknown_course_does_not_poison_known_course_pass_fact() -> None:
    known = _course("CSE141")
    unknown = _course("CSE999")
    state = _build(
        _attempt(known, outcome=AttemptOutcome.PASSED, credits_earned=3),
        _attempt(unknown, outcome=AttemptOutcome.UNKNOWN),
    ).student_state

    assert state is not None
    assert state.pass_status(known) is FactStatus.KNOWN_TRUE
    assert state.pass_status(unknown) is FactStatus.UNKNOWN


def test_rule_evaluator_uses_v2_pass_and_registration_fact_queries() -> None:
    passed = _course("CSE141")
    current = _course("CSE142")
    state = _build(
        _attempt(passed, outcome=AttemptOutcome.PASSED, credits_earned=3),
        current_registrations=(_registration(current),),
    ).student_state

    assert state is not None
    passed_result = _evaluate(CoursePassedExpression(passed), state)
    completed_result = _evaluate(CourseCompletedExpression(passed), state)
    current_result = _evaluate(CourseCurrentlyRegisteredExpression(current), state)

    assert passed_result.outcome is EvaluationOutcome.SATISFIED
    assert completed_result.outcome is EvaluationOutcome.SATISFIED
    assert current_result.outcome is EvaluationOutcome.SATISFIED


def test_rule_evaluator_maps_v2_unknown_registration_to_indeterminate() -> None:
    course = _course("CSE141")
    state = _build(
        registration_coverage=RegistrationCoverage.PARTIAL,
    ).student_state

    assert state is not None
    result = _evaluate(CourseCurrentlyRegisteredExpression(course), state)

    assert result.outcome is EvaluationOutcome.INDETERMINATE
    assert ReasonCode.MISSING_REQUIRED_DATA in result.reason_codes


def test_rule_evaluator_maps_complete_absence_to_unsatisfied_pass() -> None:
    course = _course("CSE141")
    state = _build().student_state

    assert state is not None
    result = _evaluate(CoursePassedExpression(course), state)

    assert result.outcome is EvaluationOutcome.UNSATISFIED


def test_missing_coverage_declaration_is_not_treated_as_complete_history() -> None:
    result = StudentStateBuilder().build(
        StudentStateBuildInput(
            student_id="student-001",
            regulation=Regulation.R23,
            program=Program("CAIE"),
        )
    )

    assert result.student_state is None
    assert any(
        ReasonCode.MISSING_REQUIRED_DATA in diagnostic.reason_codes
        for diagnostic in result.diagnostics
    )


def test_explicit_outcome_conflicting_with_legacy_flags_is_fatal() -> None:
    course = _course("CSE141")
    result = StudentStateBuilder().build(
        StudentStateBuildInput(
            student_id="student-001",
            regulation=Regulation.R23,
            program=Program("CAIE"),
            course_attempts=(
                _attempt(
                    course,
                    outcome=AttemptOutcome.PASSED,
                    failed=True,
                    credits_earned=3,
                ),
            ),
            history_coverage=AcademicHistoryCoverage.COMPLETE,
            registration_coverage=RegistrationCoverage.COMPLETE,
        )
    )

    assert result.student_state is None
    assert any(
        diagnostic.code.value == "CONTRADICTORY_RECORD" and diagnostic.fatal
        for diagnostic in result.diagnostics
    )


def test_explicit_outcome_conflicting_with_false_legacy_flag_is_fatal() -> None:
    course = _course("CSE141")
    result = StudentStateBuilder().build(
        StudentStateBuildInput(
            student_id="student-001",
            regulation=Regulation.R23,
            program=Program("CAIE"),
            course_attempts=(
                _attempt(
                    course,
                    outcome=AttemptOutcome.PASSED,
                    passed=False,
                    credits_earned=3,
                ),
            ),
            history_coverage=AcademicHistoryCoverage.COMPLETE,
            registration_coverage=RegistrationCoverage.COMPLETE,
        )
    )

    assert result.student_state is None
    assert any(
        diagnostic.code.value == "CONTRADICTORY_RECORD" and diagnostic.fatal
        for diagnostic in result.diagnostics
    )
