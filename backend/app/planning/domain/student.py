"""Canonical immutable student state for Planning Engine services."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .course import CourseIdentity, Program, Regulation
from .student_history import CourseAttempt, CurrentRegistration


@dataclass(frozen=True, slots=True)
class StudentState:
    """Stable canonical student context derived from trusted typed records.

    ``completed_courses`` and ``passed_courses`` are intentionally separate.
    A state built from the current Academic Data Foundation derives both from
    explicit passing facts, while preserving the distinction for future data
    contracts that may represent successful completion independently.

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
