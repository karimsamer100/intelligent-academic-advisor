from __future__ import annotations

import pytest

from backend.app.planning.domain.course import CourseIdentity, Program, Regulation
from backend.app.planning.domain.student_history import (
    AcademicSnapshot,
    CourseAttempt,
    CurrentRegistration,
)


def _course() -> CourseIdentity:
    return CourseIdentity.parse("R23:CAIE:CSE111")


def test_course_attempt_is_immutable_and_preserves_optional_outcome_facts() -> None:
    attempt = CourseAttempt(
        student_id="student-001",
        course=_course(),
        attempt_number=1,
        term="Fall",
        academic_year=2024,
        status="completed",
        passed=True,
        failed=False,
        withdrawn=False,
        repeated=False,
        credits_attempted=3,
        credits_earned=3,
    )

    assert attempt.passed is True
    assert attempt.credits_earned == 3
    with pytest.raises((AttributeError, TypeError)):
        attempt.passed = False  # type: ignore[misc]


def test_course_attempt_keeps_missing_pass_fact_as_unknown() -> None:
    attempt = CourseAttempt(
        student_id="student-001",
        course=_course(),
        attempt_number=1,
        term="Fall",
        academic_year=2024,
        status="withdrawn",
        withdrawn=True,
    )

    assert attempt.passed is None


def test_current_registration_is_typed_and_opaque_status_is_preserved() -> None:
    registration = CurrentRegistration(
        student_id="student-001",
        course=_course(),
        term="Spring",
        academic_year=2025,
        registration_status="registered",
    )

    assert registration.course == _course()
    assert registration.registration_status == "registered"


def test_academic_snapshot_carries_authoritative_passthrough_facts() -> None:
    snapshot = AcademicSnapshot(
        student_id="student-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        gpa=2.75,
        earned_credit_hours=54,
        registered_credit_hours=12,
        academic_level="junior",
        academic_standing="good",
        track="AI",
    )

    assert snapshot.gpa == 2.75
    assert snapshot.earned_credit_hours == 54
    assert snapshot.academic_level == "junior"
