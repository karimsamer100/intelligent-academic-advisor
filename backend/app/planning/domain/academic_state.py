"""Typed per-course facts used by the version-two student state."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .course import CourseIdentity
from .student_history import (
    AttemptOutcome,
    AttemptPurpose,
    CourseAttempt,
    CurrentRegistration,
)

if TYPE_CHECKING:
    from .student_diagnostics import StudentStateDiagnostic


class FactStatus(StrEnum):
    """Three-valued status for a course-scoped academic fact."""

    KNOWN_TRUE = "KNOWN_TRUE"
    KNOWN_FALSE = "KNOWN_FALSE"
    UNKNOWN = "UNKNOWN"


class AcademicHistoryCoverage(StrEnum):
    """Whether absence from the supplied attempt history is meaningful."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class RegistrationCoverage(StrEnum):
    """Whether absence from supplied current registrations is meaningful."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class EffectiveCourseStatus(StrEnum):
    """Deterministic effective course view, separate from individual facts."""

    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    WITHDRAWN = "WITHDRAWN"
    INCOMPLETE = "INCOMPLETE"
    IN_PROGRESS = "IN_PROGRESS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class CourseAcademicRecord:
    """Immutable canonical facts for one regulation/program-scoped course.

    Attempts and current registrations remain visible.  ``pass_status`` and
    ``registration_status`` are independent facts; ``effective_status`` is a
    derived view and is not a replacement for either one.
    """

    course: CourseIdentity
    attempts: tuple[CourseAttempt, ...]
    current_registrations: tuple[CurrentRegistration, ...]
    effective_status: EffectiveCourseStatus
    pass_status: FactStatus
    registration_status: FactStatus
    earned_credits: int | float | None = None
    diagnostics: tuple["StudentStateDiagnostic", ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")
        attempts = tuple(self.attempts)
        registrations = tuple(self.current_registrations)
        if not all(isinstance(attempt, CourseAttempt) for attempt in attempts):
            raise TypeError("attempts must contain CourseAttempt values")
        if not all(attempt.course == self.course for attempt in attempts):
            raise ValueError("all attempts must belong to the record course")
        if not all(
            isinstance(registration, CurrentRegistration)
            for registration in registrations
        ):
            raise TypeError(
                "current_registrations must contain CurrentRegistration values"
            )
        if not all(
            registration.course == self.course for registration in registrations
        ):
            raise ValueError(
                "all current registrations must belong to the record course"
            )
        if not isinstance(self.effective_status, EffectiveCourseStatus):
            raise TypeError("effective_status must be an EffectiveCourseStatus")
        if not isinstance(self.pass_status, FactStatus):
            raise TypeError("pass_status must be a FactStatus")
        if not isinstance(self.registration_status, FactStatus):
            raise TypeError("registration_status must be a FactStatus")
        _validate_optional_number(self.earned_credits, "earned_credits")
        from .student_diagnostics import StudentStateDiagnostic

        diagnostics = tuple(self.diagnostics)
        if not all(
            isinstance(diagnostic, StudentStateDiagnostic) for diagnostic in diagnostics
        ):
            raise TypeError(
                "diagnostics must contain only StudentStateDiagnostic values"
            )
        object.__setattr__(
            self,
            "attempts",
            tuple(sorted(attempts, key=_attempt_sort_key)),
        )
        object.__setattr__(
            self,
            "current_registrations",
            tuple(sorted(registrations, key=_registration_sort_key)),
        )
        object.__setattr__(self, "diagnostics", diagnostics)

    @property
    def has_passed_attempt(self) -> bool:
        return any(
            attempt.outcome is AttemptOutcome.PASSED for attempt in self.attempts
        )

    @property
    def has_failed_attempt(self) -> bool:
        return any(
            attempt.outcome is AttemptOutcome.FAILED for attempt in self.attempts
        )

    @property
    def has_withdrawn_attempt(self) -> bool:
        return any(
            attempt.outcome is AttemptOutcome.WITHDRAWN for attempt in self.attempts
        )

    @property
    def has_incomplete_attempt(self) -> bool:
        return any(
            attempt.outcome is AttemptOutcome.INCOMPLETE for attempt in self.attempts
        )

    @property
    def has_repeat_or_improvement_attempt(self) -> bool:
        return any(
            attempt.repeated is True
            or attempt.purpose in (AttemptPurpose.REPEAT, AttemptPurpose.IMPROVEMENT)
            for attempt in self.attempts
        )


def _attempt_sort_key(attempt: CourseAttempt) -> tuple[int, int, str, str]:
    return (
        attempt.attempt_number,
        attempt.academic_year,
        attempt.term,
        attempt.outcome.value,
    )


def _registration_sort_key(
    registration: CurrentRegistration,
) -> tuple[int, str, str]:
    return (
        registration.academic_year,
        registration.term,
        registration.registration_status or "",
    )


def _validate_optional_number(value: int | float | None, name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric or None")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")
