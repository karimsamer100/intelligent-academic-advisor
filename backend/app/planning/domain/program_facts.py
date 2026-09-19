"""Typed non-course academic facts used by program audits."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProgramFactCoverage(StrEnum):
    """Whether supplied non-course facts cover the requested student scope."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class FieldTrainingRecord:
    """A non-course field-training outcome; it is never a CourseAttempt."""

    passed: bool | None
    completed_weeks: int | None

    def __post_init__(self) -> None:
        if self.passed is not None and not isinstance(self.passed, bool):
            raise TypeError("passed must be a bool or None")
        if self.completed_weeks is not None and (
            isinstance(self.completed_weeks, bool)
            or not isinstance(self.completed_weeks, int)
            or self.completed_weeks < 0
        ):
            raise ValueError("completed_weeks must be a non-negative integer or None")

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "completed_weeks": self.completed_weeks,
        }


@dataclass(frozen=True, slots=True)
class StudentProgramFacts:
    """Canonical non-transcript facts needed by program requirements."""

    coverage: ProgramFactCoverage = ProgramFactCoverage.UNAVAILABLE
    field_training: FieldTrainingRecord | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.coverage, ProgramFactCoverage):
            raise TypeError("coverage must be a ProgramFactCoverage")
        if self.field_training is not None and not isinstance(
            self.field_training, FieldTrainingRecord
        ):
            raise TypeError("field_training must be a FieldTrainingRecord or None")

    def to_dict(self) -> dict[str, object]:
        return {
            "coverage": self.coverage.value,
            "field_training": (
                self.field_training.to_dict() if self.field_training else None
            ),
        }
