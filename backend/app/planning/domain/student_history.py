"""Typed input records used to construct the canonical student state.

These records describe supplied academic facts.  They deliberately do not
interpret opaque statuses or calculate regulation-specific academic results.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .course import CourseIdentity, Program, Regulation


@dataclass(frozen=True, slots=True)
class CourseAttempt:
    """One supplied attempt for a regulation- and program-scoped course.

    Outcome flags are optional because the current Academic Data Foundation
    schema permits them to be absent.  A missing flag is not treated as
    ``False`` by the state builder.
    """

    student_id: str
    course: CourseIdentity
    attempt_number: int
    term: str
    academic_year: int
    status: str
    grade: str | None = None
    grade_points: int | float | None = None
    credits_attempted: int | float | None = None
    credits_earned: int | float | None = None
    passed: bool | None = None
    failed: bool | None = None
    withdrawn: bool | None = None
    repeated: bool | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        _validate_student_id(self.student_id)
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")
        if isinstance(self.attempt_number, bool) or not isinstance(
            self.attempt_number, int
        ):
            raise TypeError("attempt_number must be an integer")
        if self.attempt_number < 1:
            raise ValueError("attempt_number must be at least 1")
        if not isinstance(self.term, str) or not self.term.strip():
            raise ValueError("term must be a non-empty string")
        if isinstance(self.academic_year, bool) or not isinstance(
            self.academic_year, int
        ):
            raise TypeError("academic_year must be an integer")
        if not isinstance(self.status, str) or not self.status.strip():
            raise ValueError("status must be a non-empty string")
        _validate_optional_text(self.grade, "grade")
        _validate_optional_text(self.source, "source")
        _validate_optional_number(self.grade_points, "grade_points")
        _validate_optional_number(
            self.credits_attempted, "credits_attempted", nonnegative=True
        )
        _validate_optional_number(
            self.credits_earned, "credits_earned", nonnegative=True
        )
        for field_name in ("passed", "failed", "withdrawn", "repeated"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"{field_name} must be a bool or None")


@dataclass(frozen=True, slots=True)
class CurrentRegistration:
    """One current registration fact with an uninterpreted status."""

    student_id: str
    course: CourseIdentity
    term: str
    academic_year: int
    registration_status: str | None = None

    def __post_init__(self) -> None:
        _validate_student_id(self.student_id)
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")
        if not isinstance(self.term, str) or not self.term.strip():
            raise ValueError("term must be a non-empty string")
        if isinstance(self.academic_year, bool) or not isinstance(
            self.academic_year, int
        ):
            raise TypeError("academic_year must be an integer")
        _validate_optional_text(self.registration_status, "registration_status")


@dataclass(frozen=True, slots=True)
class AcademicSnapshot:
    """Selected authoritative aggregate facts for one student and scope."""

    student_id: str
    regulation: Regulation
    program: Program
    gpa: int | float
    earned_credit_hours: int | float
    registered_credit_hours: int | float | None = None
    academic_level: str | int | None = None
    academic_standing: str | None = None
    track: str | None = None

    def __post_init__(self) -> None:
        _validate_student_id(self.student_id)
        if not isinstance(self.regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(self.program, Program):
            raise TypeError("program must be a Program")
        _validate_number(self.gpa, "gpa")
        _validate_number(
            self.earned_credit_hours,
            "earned_credit_hours",
            nonnegative=True,
        )
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
        _validate_optional_text(self.academic_standing, "academic_standing")
        _validate_optional_text(self.track, "track")


def _validate_student_id(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("student_id must be a non-empty string")


def _validate_optional_text(value: object, name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{name} must be a non-empty string when provided")


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
