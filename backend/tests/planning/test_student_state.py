import pytest

from app.planning.domain.course import CourseIdentity, Program, Regulation
from app.planning.domain.student import StudentState
from app.planning.domain.student_history import CourseAttempt


def test_student_state_keeps_passed_courses_separate_from_completed_courses() -> None:
    completed = CourseIdentity.parse("R23:CAIE:CSE241")
    passed = CourseIdentity.parse("R23:CAIE:CSE281")

    state = StudentState(
        student_id="student-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        completed_courses=frozenset({completed}),
        passed_courses=frozenset({passed}),
    )

    assert state.completed_courses == frozenset({completed})
    assert state.passed_courses == frozenset({passed})


def test_student_state_accepts_optional_gpa_without_a_fixed_scale() -> None:
    state = StudentState(
        student_id="student-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        gpa=5.5,
    )

    assert state.gpa == 5.5


def test_student_state_can_leave_gpa_and_passed_courses_unavailable() -> None:
    state = StudentState(
        student_id="student-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
    )

    assert state.gpa is None
    assert state.passed_courses is None


def test_student_state_preserves_history_and_course_local_unknown_facts() -> None:
    course = CourseIdentity.parse("R23:CAIE:CSE111")
    unknown_course = CourseIdentity.parse("R23:CAIE:CSE999")
    attempt = CourseAttempt(
        student_id="student-001",
        course=course,
        attempt_number=1,
        term="Fall",
        academic_year=2024,
        status="completed",
        passed=True,
    )

    state = StudentState(
        student_id="student-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        earned_credit_hours=None,
        completed_courses=frozenset({course}),
        passed_courses=frozenset({course}),
        course_attempts=(attempt,),
        failed_courses=frozenset(),
        withdrawn_courses=frozenset(),
        repeated_courses=frozenset(),
        unknown_pass_status_courses=frozenset({unknown_course}),
        unknown_completion_status_courses=frozenset({unknown_course}),
        academic_level="junior",
        academic_standing="good",
    )

    assert state.course_attempts == (attempt,)
    assert state.unknown_pass_status_courses == frozenset({unknown_course})
    assert state.unknown_completion_status_courses == frozenset({unknown_course})
    assert state.earned_credit_hours is None
    assert state.academic_level == "junior"


def test_student_state_rejects_unknown_course_that_is_already_known_passed() -> None:
    course = CourseIdentity.parse("R23:CAIE:CSE111")

    with pytest.raises(ValueError):
        StudentState(
            student_id="student-001",
            regulation=Regulation.R23,
            program=Program("CAIE"),
            passed_courses=frozenset({course}),
            unknown_pass_status_courses=frozenset({course}),
        )
