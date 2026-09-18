"""Safe fact and earned-credit derivation for canonical student state."""

from __future__ import annotations

from collections import defaultdict

from ..domain.course import CourseIdentity
from ..domain.reasons import ReasonCode
from ..domain.student_diagnostics import (
    DiagnosticSeverity,
    StudentRecordType,
    StudentStateDiagnostic,
    StudentStateDiagnosticCode,
)
from ..domain.student_history import CourseAttempt


def derive_attempt_credits(
    attempts: tuple[CourseAttempt, ...],
    passed_courses: frozenset[CourseIdentity],
) -> tuple[int | float | None, tuple[StudentStateDiagnostic, ...]]:
    """Return distinct-course credits only when attempt facts are complete."""

    diagnostics: list[StudentStateDiagnostic] = []
    passed_attempts_by_course: dict[CourseIdentity, list[CourseAttempt]] = defaultdict(
        list
    )
    for attempt in attempts:
        if attempt.passed is True:
            passed_attempts_by_course[attempt.course].append(attempt)
        elif attempt.credits_earned is not None and attempt.credits_earned > 0:
            diagnostics.append(
                StudentStateDiagnostic(
                    code=StudentStateDiagnosticCode.CREDIT_DATA_CONFLICT,
                    severity=DiagnosticSeverity.WARNING,
                    record_type=StudentRecordType.COURSE_ATTEMPT,
                    course=attempt.course,
                    attempt_number=attempt.attempt_number,
                    field="credits_earned",
                    requires_human_review=True,
                )
            )

    derived_available = not any(attempt.passed is None for attempt in attempts)
    total: int | float = 0
    for course in sorted(passed_courses, key=str):
        passed_attempts = tuple(passed_attempts_by_course[course])
        credits = {attempt.credits_earned for attempt in passed_attempts}
        if None in credits:
            derived_available = False
            for attempt in passed_attempts:
                if attempt.credits_earned is None:
                    diagnostics.append(
                        StudentStateDiagnostic(
                            code=StudentStateDiagnosticCode.INCOMPLETE_RECORD,
                            severity=DiagnosticSeverity.WARNING,
                            record_type=StudentRecordType.COURSE_ATTEMPT,
                            reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                            course=course,
                            attempt_number=attempt.attempt_number,
                            field="credits_earned",
                            requires_human_review=True,
                        )
                    )
        elif len(credits) > 1:
            derived_available = False
            diagnostics.append(
                StudentStateDiagnostic(
                    code=StudentStateDiagnosticCode.CREDIT_DATA_CONFLICT,
                    severity=DiagnosticSeverity.WARNING,
                    record_type=StudentRecordType.COURSE_ATTEMPT,
                    course=course,
                    field="credits_earned",
                    requires_human_review=True,
                )
            )
        else:
            total += next(iter(credits))
    if not derived_available:
        return None, tuple(diagnostics)
    return total, tuple(diagnostics)


def missing_pass_diagnostics(
    courses: frozenset[CourseIdentity],
) -> tuple[StudentStateDiagnostic, ...]:
    """Describe course-scoped missing pass facts."""

    return tuple(
        StudentStateDiagnostic(
            code=StudentStateDiagnosticCode.INCOMPLETE_RECORD,
            severity=DiagnosticSeverity.WARNING,
            record_type=StudentRecordType.COURSE_ATTEMPT,
            reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
            course=course,
            field="passed",
            requires_human_review=True,
        )
        for course in sorted(courses, key=str)
    )
