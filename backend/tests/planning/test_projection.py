from __future__ import annotations

from app.planning.domain.academic_state import (
    AcademicHistoryCoverage,
    RegistrationCoverage,
)
from app.planning.domain.context import RegistrationIntent
from app.planning.domain.course import CourseIdentity, Program, Regulation
from app.planning.domain.student import StudentState
from app.planning.domain.student_history import AttemptOutcome, AttemptPurpose
from app.planning.projection.service import HypotheticalStateTransitionService
from app.planning.domain.projection import (
    AcademicStateLayer,
    HypotheticalAcademicOutcome,
    ProjectionPolicy,
)


R23 = Regulation.R23
CAIE = Program("CAIE")


def cid(code: str) -> CourseIdentity:
    return CourseIdentity(R23, CAIE, code)


def state(
    *, earned: int | float | None = 90, passed: tuple[CourseIdentity, ...] = ()
) -> StudentState:
    return StudentState(
        "projection-student",
        R23,
        CAIE,
        earned_credit_hours=earned,
        passed_courses=frozenset(passed),
        completed_courses=frozenset(passed),
        history_coverage=AcademicHistoryCoverage.COMPLETE,
        registration_coverage=RegistrationCoverage.COMPLETE,
    )


def outcome(
    course: CourseIdentity,
    result: AttemptOutcome,
    *,
    sequence: int = 1,
    credits: int | float | None = 3,
    purpose: AttemptPurpose = AttemptPurpose.INITIAL,
) -> HypotheticalAcademicOutcome:
    return HypotheticalAcademicOutcome(
        course=course,
        outcome=result,
        purpose=purpose,
        sequence=sequence,
        earned_credit_hours=credits,
        intent=RegistrationIntent.NORMAL,
        layer=AcademicStateLayer.PROJECTED,
    )


def test_transition_is_immutable_and_projected_pass_is_visible() -> None:
    original = state()
    projected = HypotheticalStateTransitionService().apply(
        original,
        (outcome(cid("CSE392"), AttemptOutcome.PASSED),),
        policy=ProjectionPolicy.ASSUME_SELECTED_COURSES_PASSED,
    )

    assert original.pass_status(cid("CSE392")).value == "KNOWN_FALSE"
    assert projected.student_state.pass_status(cid("CSE392")).value == "KNOWN_TRUE"
    assert projected.student_state is not original
    assert projected.layer is AcademicStateLayer.PROJECTED
    assert projected.student_state.fact_layer is AcademicStateLayer.PROJECTED


def test_projected_failure_does_not_become_a_pass() -> None:
    projected = HypotheticalStateTransitionService().apply(
        state(),
        (outcome(cid("CSE392"), AttemptOutcome.FAILED),),
    )

    assert projected.student_state.pass_status(cid("CSE392")).value == "KNOWN_FALSE"


def test_known_projected_course_credits_advance_once() -> None:
    projected = HypotheticalStateTransitionService().apply(
        state(earned=90),
        (
            outcome(cid("CSE392"), AttemptOutcome.PASSED, credits=3),
            outcome(cid("CSE493"), AttemptOutcome.PASSED, credits=6, sequence=2),
        ),
    )

    assert projected.earned_credit_hours == 99
    assert projected.student_state.earned_credit_hours == 99


def test_zero_credit_projection_does_not_inflate_earned_credits() -> None:
    projected = HypotheticalStateTransitionService().apply(
        state(earned=90),
        (outcome(cid("ASUx11"), AttemptOutcome.PASSED, credits=0),),
    )

    assert projected.earned_credit_hours == 90
    assert projected.student_state.pass_status(cid("ASUx11")).value == "KNOWN_TRUE"


def test_unknown_projected_credit_makes_total_unknown() -> None:
    projected = HypotheticalStateTransitionService().apply(
        state(earned=90),
        (outcome(cid("CSE392"), AttemptOutcome.PASSED, credits=None),),
    )

    assert projected.earned_credit_hours is None
    assert projected.credits_known is False


def test_projected_repeat_does_not_double_count_course_credits() -> None:
    service = HypotheticalStateTransitionService()
    first = service.apply(
        state(earned=90),
        (outcome(cid("CSE392"), AttemptOutcome.PASSED, sequence=1),),
    )
    second = service.apply(
        first.student_state,
        (outcome(cid("CSE392"), AttemptOutcome.PASSED, sequence=2),),
    )

    assert second.earned_credit_hours == 93


def test_explicit_improvement_failure_can_replace_an_observed_pass() -> None:
    projected = HypotheticalStateTransitionService().apply(
        state(passed=(cid("CSE392"),)),
        (
            outcome(
                cid("CSE392"),
                AttemptOutcome.FAILED,
                purpose=AttemptPurpose.IMPROVEMENT,
            ),
        ),
    )

    assert projected.student_state.pass_status(cid("CSE392")).value == "KNOWN_FALSE"


def test_improvement_failure_does_not_add_projected_earned_credits() -> None:
    projected = HypotheticalStateTransitionService().apply(
        state(earned=90),
        (
            outcome(cid("CSE392"), AttemptOutcome.PASSED, sequence=1),
            outcome(
                cid("CSE392"),
                AttemptOutcome.FAILED,
                purpose=AttemptPurpose.IMPROVEMENT,
                sequence=2,
            ),
        ),
    )

    assert projected.student_state.pass_status(cid("CSE392")).value == "KNOWN_FALSE"
    assert projected.earned_credit_hours == 90
