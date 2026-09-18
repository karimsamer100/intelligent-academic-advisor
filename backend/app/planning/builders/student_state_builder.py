"""Construction of canonical student state from typed academic facts."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.course import Program, Regulation
from ..domain.student import StudentState
from ..domain.student_diagnostics import (
    DiagnosticSeverity,
    StudentRecordType,
    StudentStateBuildResult,
    StudentStateDiagnostic,
    StudentStateDiagnosticCode,
)
from ..domain.student_history import (
    AcademicSnapshot,
    CourseAttempt,
    CurrentRegistration,
)
from .student_state_derivation import derive_attempt_credits, missing_pass_diagnostics
from .student_state_validation import sort_diagnostics, validate_records


@dataclass(frozen=True, slots=True)
class StudentStateBuildInput:
    """Complete typed input supplied to :class:`StudentStateBuilder`.

    ``course_attempts`` is expected to represent the student's complete
    available academic-attempt history. Loading that history is the
    responsibility of a future repository or adapter, not this builder.
    """

    student_id: str
    regulation: Regulation
    program: Program
    track: str | None = None
    course_attempts: tuple[CourseAttempt, ...] = ()
    current_registrations: tuple[CurrentRegistration, ...] = ()
    academic_snapshot: AcademicSnapshot | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.student_id, str) or not self.student_id.strip():
            raise ValueError("student_id must be a non-empty string")
        if not isinstance(self.regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(self.program, Program):
            raise TypeError("program must be a Program")
        if self.track is not None and (
            not isinstance(self.track, str) or not self.track.strip()
        ):
            raise ValueError("track must be a non-empty string when provided")
        attempts = tuple(self.course_attempts)
        registrations = tuple(self.current_registrations)
        if not all(isinstance(attempt, CourseAttempt) for attempt in attempts):
            raise TypeError("course_attempts must contain CourseAttempt values")
        if not all(
            isinstance(registration, CurrentRegistration)
            for registration in registrations
        ):
            raise TypeError(
                "current_registrations must contain CurrentRegistration values"
            )
        if self.academic_snapshot is not None and not isinstance(
            self.academic_snapshot, AcademicSnapshot
        ):
            raise TypeError("academic_snapshot must be an AcademicSnapshot or None")
        object.__setattr__(self, "course_attempts", attempts)
        object.__setattr__(self, "current_registrations", registrations)


@dataclass(frozen=True, slots=True)
class StudentStateBuilder:
    """Stateless pure builder; repository access belongs outside this class."""

    def build(self, input_data: StudentStateBuildInput) -> StudentStateBuildResult:
        """Build canonical state from typed records.

        An empty input is a complete empty history and therefore produces
        known-empty course facts rather than unavailable course facts.
        """

        if not isinstance(input_data, StudentStateBuildInput):
            raise TypeError("input_data must be a StudentStateBuildInput")
        attempts = tuple(sorted(input_data.course_attempts, key=_attempt_sort_key))
        registrations = tuple(
            sorted(input_data.current_registrations, key=_registration_sort_key)
        )
        diagnostics = list(
            validate_records(
                student_id=input_data.student_id,
                regulation=input_data.regulation,
                program=input_data.program,
                track=input_data.track,
                attempts=attempts,
                registrations=registrations,
                snapshot=input_data.academic_snapshot,
            )
        )
        if any(diagnostic.fatal for diagnostic in diagnostics):
            return StudentStateBuildResult(
                student_state=None,
                diagnostics=tuple(diagnostics),
            )

        passed_courses = frozenset(
            attempt.course for attempt in attempts if attempt.passed is True
        )
        failed_courses = frozenset(
            attempt.course for attempt in attempts if attempt.failed is True
        )
        withdrawn_courses = frozenset(
            attempt.course for attempt in attempts if attempt.withdrawn is True
        )
        repeated_courses = frozenset(
            attempt.course for attempt in attempts if attempt.repeated is True
        )
        unknown_pass_courses = frozenset(
            attempt.course
            for attempt in attempts
            if attempt.passed is None and attempt.course not in passed_courses
        )
        derived_credits, credit_diagnostics = derive_attempt_credits(
            attempts,
            passed_courses,
        )
        diagnostics.extend(credit_diagnostics)
        diagnostics.extend(missing_pass_diagnostics(unknown_pass_courses))

        snapshot = input_data.academic_snapshot
        if snapshot is None:
            earned_credit_hours = derived_credits
            gpa = None
            registered_credit_hours = None
            academic_level = None
            academic_standing = None
            track = input_data.track
        else:
            earned_credit_hours = snapshot.earned_credit_hours
            if derived_credits is not None and derived_credits != earned_credit_hours:
                diagnostics.append(_snapshot_credit_conflict_diagnostic())
            gpa = snapshot.gpa
            registered_credit_hours = snapshot.registered_credit_hours
            academic_level = snapshot.academic_level
            academic_standing = snapshot.academic_standing
            track = input_data.track if input_data.track is not None else snapshot.track

        state = StudentState(
            student_id=input_data.student_id,
            regulation=input_data.regulation,
            program=input_data.program,
            track=track,
            earned_credit_hours=earned_credit_hours,
            completed_courses=passed_courses,
            current_courses=frozenset(
                registration.course for registration in registrations
            ),
            gpa=gpa,
            passed_courses=passed_courses,
            course_attempts=attempts,
            current_registrations=registrations,
            failed_courses=failed_courses,
            withdrawn_courses=withdrawn_courses,
            repeated_courses=repeated_courses,
            registered_credit_hours=registered_credit_hours,
            academic_level=academic_level,
            academic_standing=academic_standing,
            unknown_pass_status_courses=unknown_pass_courses,
            unknown_completion_status_courses=unknown_pass_courses,
        )
        return StudentStateBuildResult(
            student_state=state,
            diagnostics=tuple(sort_diagnostics(diagnostics)),
        )


def _attempt_sort_key(attempt: CourseAttempt) -> tuple[str, int, int, str]:
    return (
        attempt.course.course_id,
        attempt.attempt_number,
        attempt.academic_year,
        attempt.term,
    )


def _registration_sort_key(
    registration: CurrentRegistration,
) -> tuple[str, int, str, str]:
    return (
        registration.course.course_id,
        registration.academic_year,
        registration.term,
        registration.registration_status or "",
    )


def _snapshot_credit_conflict_diagnostic() -> StudentStateDiagnostic:
    return StudentStateDiagnostic(
        code=StudentStateDiagnosticCode.CREDIT_DATA_CONFLICT,
        severity=DiagnosticSeverity.WARNING,
        record_type=StudentRecordType.ACADEMIC_SNAPSHOT,
        field="earned_credit_hours",
        requires_human_review=True,
    )
