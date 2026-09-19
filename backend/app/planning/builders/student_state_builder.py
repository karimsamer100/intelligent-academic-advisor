"""Construction of canonical student state from typed academic facts."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.academic_state import (
    AcademicHistoryCoverage,
    FactStatus,
    RegistrationCoverage,
)
from ..domain.course import Program, Regulation
from ..domain.reasons import ReasonCode
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
from .student_state_derivation import build_course_records, derive_total_credits
from .student_state_validation import sort_diagnostics, validate_records


@dataclass(frozen=True, slots=True)
class StudentStateBuildInput:
    """Typed source records plus explicit coverage declarations.

    The caller must declare whether each supplied collection is complete.  A
    future repository or adapter is responsible for loading the complete
    history; this builder never fetches or infers missing records.
    """

    student_id: str
    regulation: Regulation
    program: Program
    track: str | None = None
    course_attempts: tuple[CourseAttempt, ...] = ()
    current_registrations: tuple[CurrentRegistration, ...] = ()
    academic_snapshot: AcademicSnapshot | None = None
    history_coverage: AcademicHistoryCoverage | None = None
    registration_coverage: RegistrationCoverage | None = None

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
        if self.history_coverage is not None and not isinstance(
            self.history_coverage, AcademicHistoryCoverage
        ):
            raise TypeError(
                "history_coverage must be an AcademicHistoryCoverage or None"
            )
        if self.registration_coverage is not None and not isinstance(
            self.registration_coverage, RegistrationCoverage
        ):
            raise TypeError(
                "registration_coverage must be a RegistrationCoverage or None"
            )
        object.__setattr__(self, "course_attempts", attempts)
        object.__setattr__(self, "current_registrations", registrations)


@dataclass(frozen=True, slots=True)
class StudentStateBuilder:
    """Stateless pure builder; repository access belongs outside this class."""

    def build(self, input_data: StudentStateBuildInput) -> StudentStateBuildResult:
        """Build a deterministic state or return structured diagnostics."""

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
        diagnostics.extend(_coverage_diagnostics(input_data))
        if any(diagnostic.fatal for diagnostic in diagnostics):
            return StudentStateBuildResult(
                student_state=None,
                diagnostics=tuple(sort_diagnostics(diagnostics)),
            )

        records = build_course_records(
            attempts=attempts,
            registrations=registrations,
            history_coverage=input_data.history_coverage,
            registration_coverage=input_data.registration_coverage,
        )
        diagnostics.extend(
            diagnostic for record in records for diagnostic in record.diagnostics
        )

        passed_courses = frozenset(
            record.course
            for record in records
            if record.pass_status is FactStatus.KNOWN_TRUE
        )
        failed_courses = frozenset(
            record.course for record in records if record.has_failed_attempt
        )
        withdrawn_courses = frozenset(
            record.course for record in records if record.has_withdrawn_attempt
        )
        repeated_courses = frozenset(
            record.course
            for record in records
            if record.has_repeat_or_improvement_attempt
        )
        unknown_pass_courses = frozenset(
            record.course
            for record in records
            if record.pass_status is FactStatus.UNKNOWN
        )
        current_courses = frozenset(
            record.course
            for record in records
            if record.registration_status is FactStatus.KNOWN_TRUE
        )
        derived_credits = derive_total_credits(
            records,
            history_coverage=input_data.history_coverage,
        )

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
            current_courses=current_courses,
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
            course_records=records,
            history_coverage=input_data.history_coverage,
            registration_coverage=input_data.registration_coverage,
        )
        return StudentStateBuildResult(
            student_state=state,
            diagnostics=tuple(sort_diagnostics(diagnostics)),
        )


def _attempt_sort_key(attempt: CourseAttempt) -> tuple[str, int, int, str]:
    # ``attempt_number`` is the authoritative chronology for this domain.  The
    # remaining fields only make otherwise-invalid/tied input deterministic;
    # duplicate attempt numbers are rejected before state construction.
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


def _coverage_diagnostics(
    input_data: StudentStateBuildInput,
) -> tuple[StudentStateDiagnostic, ...]:
    diagnostics: list[StudentStateDiagnostic] = []
    if input_data.history_coverage is None:
        diagnostics.append(
            _missing_coverage_diagnostic(
                StudentRecordType.COURSE_ATTEMPT,
                "history_coverage",
            )
        )
    if input_data.registration_coverage is None:
        diagnostics.append(
            _missing_coverage_diagnostic(
                StudentRecordType.CURRENT_REGISTRATION,
                "registration_coverage",
            )
        )
    return tuple(diagnostics)


def _missing_coverage_diagnostic(
    record_type: StudentRecordType,
    field: str,
) -> StudentStateDiagnostic:
    return StudentStateDiagnostic(
        code=StudentStateDiagnosticCode.MISSING_COVERAGE_DECLARATION,
        severity=DiagnosticSeverity.ERROR,
        record_type=record_type,
        reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
        field=field,
        fatal=True,
        requires_human_review=True,
    )


def _snapshot_credit_conflict_diagnostic() -> StudentStateDiagnostic:
    return StudentStateDiagnostic(
        code=StudentStateDiagnosticCode.CREDIT_DATA_CONFLICT,
        severity=DiagnosticSeverity.WARNING,
        record_type=StudentRecordType.ACADEMIC_SNAPSHOT,
        field="earned_credit_hours",
        requires_human_review=True,
    )
