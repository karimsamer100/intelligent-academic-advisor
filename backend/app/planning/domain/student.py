"""Canonical immutable student state for Planning Engine services."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .course import CourseIdentity, Program, Regulation
from .academic_state import (
    AcademicHistoryCoverage,
    CourseAcademicRecord,
    EffectiveCourseStatus,
    FactStatus,
    RegistrationCoverage,
)
from .student_history import CourseAttempt, CurrentRegistration


@dataclass(frozen=True, slots=True)
class StudentState:
    """Stable canonical student context derived from trusted typed records.

    Builder-created v2 states use ``course_records`` as the canonical
    attempt-based source.  ``completed_courses`` and ``passed_courses`` remain
    separate compatibility views during migration, but successful completion
    is currently represented by the same effective pass fact.

    ``unknown_pass_status_courses`` and
    ``unknown_completion_status_courses`` carry uncertainty at course scope.
    They prevent one incomplete course record from making unrelated course
    facts unavailable.  A ``None`` ``passed_courses`` value remains a
    backwards-compatible marker for a state in which pass data is globally
    unavailable.
    """

    student_id: str
    regulation: Regulation
    program: Program
    track: str | None = None
    earned_credit_hours: int | float | None = 0
    completed_courses: frozenset[CourseIdentity] = frozenset()
    current_courses: frozenset[CourseIdentity] = frozenset()
    gpa: int | float | None = None
    passed_courses: frozenset[CourseIdentity] | None = None
    course_attempts: tuple[CourseAttempt, ...] = ()
    current_registrations: tuple[CurrentRegistration, ...] = ()
    failed_courses: frozenset[CourseIdentity] = frozenset()
    withdrawn_courses: frozenset[CourseIdentity] = frozenset()
    repeated_courses: frozenset[CourseIdentity] = frozenset()
    registered_credit_hours: int | float | None = None
    academic_level: str | int | None = None
    academic_standing: str | None = None
    unknown_pass_status_courses: frozenset[CourseIdentity] = frozenset()
    unknown_completion_status_courses: frozenset[CourseIdentity] = frozenset()
    course_records: tuple[CourseAcademicRecord, ...] = ()
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
        _validate_optional_number(
            self.earned_credit_hours,
            "earned_credit_hours",
            nonnegative=True,
        )
        if self.gpa is not None:
            _validate_number(self.gpa, "gpa")
        _validate_optional_number(
            self.registered_credit_hours,
            "registered_credit_hours",
            nonnegative=True,
        )
        if self.academic_level is not None and (
            isinstance(self.academic_level, bool)
            or not isinstance(self.academic_level, (str, int))
        ):
            raise TypeError("academic_level must be a string, integer, or None")
        if isinstance(self.academic_level, str) and not self.academic_level.strip():
            raise ValueError("academic_level must be non-empty when provided")
        if self.academic_standing is not None and (
            not isinstance(self.academic_standing, str)
            or not self.academic_standing.strip()
        ):
            raise ValueError(
                "academic_standing must be a non-empty string when provided"
            )
        completed_courses = _course_set(self.completed_courses, "completed_courses")
        current_courses = _course_set(self.current_courses, "current_courses")
        passed_courses = (
            None if self.passed_courses is None else frozenset(self.passed_courses)
        )
        if passed_courses is not None and not all(
            isinstance(course, CourseIdentity) for course in passed_courses
        ):
            raise TypeError("passed_courses must contain CourseIdentity values")
        course_attempts = tuple(self.course_attempts)
        current_registrations = tuple(self.current_registrations)
        if not all(isinstance(attempt, CourseAttempt) for attempt in course_attempts):
            raise TypeError("course_attempts must contain CourseAttempt values")
        if not all(
            isinstance(registration, CurrentRegistration)
            for registration in current_registrations
        ):
            raise TypeError(
                "current_registrations must contain CurrentRegistration values"
            )
        failed_courses = _course_set(self.failed_courses, "failed_courses")
        withdrawn_courses = _course_set(self.withdrawn_courses, "withdrawn_courses")
        repeated_courses = _course_set(self.repeated_courses, "repeated_courses")
        unknown_pass_courses = _course_set(
            self.unknown_pass_status_courses,
            "unknown_pass_status_courses",
        )
        unknown_completion_courses = _course_set(
            self.unknown_completion_status_courses,
            "unknown_completion_status_courses",
        )
        course_records = tuple(self.course_records)
        if not all(
            isinstance(record, CourseAcademicRecord) for record in course_records
        ):
            raise TypeError("course_records must contain CourseAcademicRecord values")
        if len({record.course for record in course_records}) != len(course_records):
            raise ValueError("course_records cannot contain duplicate courses")
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
        if passed_courses is not None and unknown_pass_courses & passed_courses:
            raise ValueError(
                "unknown_pass_status_courses cannot contain known passed courses"
            )
        if unknown_completion_courses & completed_courses:
            raise ValueError(
                "unknown_completion_status_courses cannot contain known completed courses"
            )
        object.__setattr__(self, "completed_courses", completed_courses)
        object.__setattr__(self, "current_courses", current_courses)
        object.__setattr__(self, "passed_courses", passed_courses)
        object.__setattr__(self, "course_attempts", course_attempts)
        object.__setattr__(self, "current_registrations", current_registrations)
        object.__setattr__(self, "failed_courses", failed_courses)
        object.__setattr__(self, "withdrawn_courses", withdrawn_courses)
        object.__setattr__(self, "repeated_courses", repeated_courses)
        object.__setattr__(self, "unknown_pass_status_courses", unknown_pass_courses)
        object.__setattr__(
            self,
            "unknown_completion_status_courses",
            unknown_completion_courses,
        )
        object.__setattr__(
            self,
            "course_records",
            tuple(sorted(course_records, key=lambda record: str(record.course))),
        )

    def course_record(self, course: CourseIdentity) -> CourseAcademicRecord | None:
        """Return the canonical per-course record when one was supplied."""

        if not isinstance(course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")
        return next(
            (record for record in self.course_records if record.course == course),
            None,
        )

    def attempts_for(self, course: CourseIdentity) -> tuple[CourseAttempt, ...]:
        """Return preserved historical attempts in deterministic order."""

        record = self.course_record(course)
        if record is not None:
            return record.attempts
        return tuple(
            attempt for attempt in self.course_attempts if attempt.course == course
        )

    def pass_status(self, course: CourseIdentity) -> FactStatus:
        """Return course-scoped pass truth without conflating unknown and false."""

        record = self.course_record(course)
        if record is not None:
            return record.pass_status
        if self.passed_courses is not None and course in self.passed_courses:
            return FactStatus.KNOWN_TRUE
        if course in self.unknown_pass_status_courses:
            return FactStatus.UNKNOWN
        if self.history_coverage is AcademicHistoryCoverage.COMPLETE:
            return FactStatus.KNOWN_FALSE
        if self.history_coverage is not None:
            return FactStatus.UNKNOWN
        # Legacy direct StudentState construction retains its old semantics.
        return (
            FactStatus.UNKNOWN
            if self.passed_courses is None
            else FactStatus.KNOWN_FALSE
        )

    def completion_status(self, course: CourseIdentity) -> FactStatus:
        """Compatibility view for successful/pass truth in v2-built state."""

        record = self.course_record(course)
        if record is not None or self.history_coverage is not None:
            return self.pass_status(course)
        if course in self.unknown_completion_status_courses:
            return FactStatus.UNKNOWN
        return (
            FactStatus.KNOWN_TRUE
            if course in self.completed_courses
            else FactStatus.KNOWN_FALSE
        )

    def registration_status(self, course: CourseIdentity) -> FactStatus:
        """Return current-registration truth using explicit coverage."""

        record = self.course_record(course)
        if record is not None:
            return record.registration_status
        if course in self.current_courses:
            return FactStatus.KNOWN_TRUE
        if self.registration_coverage is RegistrationCoverage.COMPLETE:
            return FactStatus.KNOWN_FALSE
        if self.registration_coverage is not None:
            return FactStatus.UNKNOWN
        return FactStatus.KNOWN_FALSE

    def effective_course_status(self, course: CourseIdentity) -> EffectiveCourseStatus:
        """Return a course view without erasing independent pass/registration facts."""

        record = self.course_record(course)
        if record is not None:
            return record.effective_status
        registration_status = self.registration_status(course)
        pass_status = self.pass_status(course)
        if (
            registration_status is FactStatus.KNOWN_TRUE
            and pass_status is not FactStatus.KNOWN_TRUE
        ):
            return EffectiveCourseStatus.IN_PROGRESS
        if pass_status is FactStatus.KNOWN_TRUE:
            return EffectiveCourseStatus.PASSED
        if registration_status is FactStatus.UNKNOWN:
            return EffectiveCourseStatus.UNKNOWN
        if pass_status is FactStatus.UNKNOWN:
            return EffectiveCourseStatus.UNKNOWN
        if course in self.failed_courses:
            return EffectiveCourseStatus.FAILED
        if course in self.withdrawn_courses:
            return EffectiveCourseStatus.WITHDRAWN
        if self.history_coverage is not None:
            return EffectiveCourseStatus.NOT_ATTEMPTED
        return EffectiveCourseStatus.NOT_ATTEMPTED


# Re-export the v2 types from the established student-domain module.
__all__ = [
    "AcademicHistoryCoverage",
    "CourseAcademicRecord",
    "EffectiveCourseStatus",
    "FactStatus",
    "RegistrationCoverage",
    "StudentState",
]


def _course_set(value: object, name: str) -> frozenset[CourseIdentity]:
    result = frozenset(value)  # type: ignore[arg-type]
    if not all(isinstance(course, CourseIdentity) for course in result):
        raise TypeError(f"{name} must contain CourseIdentity values")
    return result


def _validate_number(value: object, name: str, *, nonnegative: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if nonnegative and value < 0:
        raise ValueError(f"{name} cannot be negative")


def _validate_optional_number(
    value: object,
    name: str,
    *,
    nonnegative: bool = False,
) -> None:
    if value is not None:
        _validate_number(value, name, nonnegative=nonnegative)
