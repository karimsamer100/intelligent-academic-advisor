"""Machine-readable program-progress projections for Degree Audit results."""

from __future__ import annotations

from dataclasses import dataclass

from .electives import ConcentrationId, ElectivePoolId
from .evaluation import EvaluationOutcome


@dataclass(frozen=True, slots=True)
class RequirementCountProgress:
    satisfied_count: int
    total_known_count: int
    in_progress_count: int = 0
    unknown_count: int = 0

    def __post_init__(self) -> None:
        for name in (
            "satisfied_count",
            "total_known_count",
            "in_progress_count",
            "unknown_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.satisfied_count > self.total_known_count:
            raise ValueError("satisfied_count cannot exceed total_known_count")

    @property
    def outstanding_count(self) -> int:
        """Count of requirements known not to be satisfied."""

        return max(
            self.total_known_count - self.satisfied_count - self.unknown_count, 0
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "satisfied_count": self.satisfied_count,
            "total_known_count": self.total_known_count,
            "in_progress_count": self.in_progress_count,
            "unknown_count": self.unknown_count,
            "outstanding_count": self.outstanding_count,
        }


@dataclass(frozen=True, slots=True)
class NumericProgress:
    observed: int | float | None
    required: int | float
    outcome: EvaluationOutcome

    def __post_init__(self) -> None:
        if self.observed is not None and (
            isinstance(self.observed, bool)
            or not isinstance(self.observed, (int, float))
        ):
            raise TypeError("observed must be numeric or None")
        if isinstance(self.required, bool) or not isinstance(
            self.required, (int, float)
        ):
            raise TypeError("required must be numeric")
        if not isinstance(self.outcome, EvaluationOutcome):
            raise TypeError("outcome must be an EvaluationOutcome")

    def to_dict(self) -> dict[str, object]:
        return {
            "observed": self.observed,
            "required": self.required,
            "remaining": (
                max(self.required - self.observed, 0)
                if self.observed is not None
                else None
            ),
            "outcome": self.outcome.value,
        }


@dataclass(frozen=True, slots=True)
class PoolProgress:
    pool_id: ElectivePoolId
    known_passed_count: int
    required_count: int
    unknown_count: int
    maximum_possible_count: int | None
    outcome: EvaluationOutcome
    remaining_count: int | None = None
    known_passed_courses: tuple[str, ...] = ()
    unknown_courses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.pool_id, ElectivePoolId):
            raise TypeError("pool_id must be an ElectivePoolId")
        for name in (
            "known_passed_count",
            "required_count",
            "unknown_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.maximum_possible_count is not None and (
            isinstance(self.maximum_possible_count, bool)
            or not isinstance(self.maximum_possible_count, int)
            or self.maximum_possible_count < 0
        ):
            raise ValueError("maximum_possible_count must be a non-negative integer")
        if self.remaining_count is not None and (
            isinstance(self.remaining_count, bool)
            or not isinstance(self.remaining_count, int)
            or self.remaining_count < 0
        ):
            raise ValueError("remaining_count must be a non-negative integer")
        if not isinstance(self.outcome, EvaluationOutcome):
            raise TypeError("outcome must be an EvaluationOutcome")
        object.__setattr__(
            self,
            "known_passed_courses",
            tuple(sorted(self.known_passed_courses)),
        )
        object.__setattr__(
            self,
            "unknown_courses",
            tuple(sorted(self.unknown_courses)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "pool_id": self.pool_id.identifier,
            "known_passed_count": self.known_passed_count,
            "required_count": self.required_count,
            "unknown_count": self.unknown_count,
            "maximum_possible_count": self.maximum_possible_count,
            "remaining_count": self.remaining_count,
            "outcome": self.outcome.value,
            "known_passed_courses": list(self.known_passed_courses),
            "unknown_courses": list(self.unknown_courses),
        }


@dataclass(frozen=True, slots=True)
class ConcentrationProgress:
    concentration_id: ConcentrationId
    known_passed_count: int
    required_minimum: int
    unknown_count: int
    maximum_possible_count: int | None
    outcome: EvaluationOutcome
    remaining_count: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.concentration_id, ConcentrationId):
            raise TypeError("concentration_id must be a ConcentrationId")
        for name in (
            "known_passed_count",
            "required_minimum",
            "unknown_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.maximum_possible_count is not None and (
            isinstance(self.maximum_possible_count, bool)
            or not isinstance(self.maximum_possible_count, int)
            or self.maximum_possible_count < 0
        ):
            raise ValueError("maximum_possible_count must be a non-negative integer")
        if self.remaining_count is not None and (
            isinstance(self.remaining_count, bool)
            or not isinstance(self.remaining_count, int)
            or self.remaining_count < 0
        ):
            raise ValueError("remaining_count must be a non-negative integer")
        if not isinstance(self.outcome, EvaluationOutcome):
            raise TypeError("outcome must be an EvaluationOutcome")

    def to_dict(self) -> dict[str, object]:
        return {
            "concentration_id": self.concentration_id.identifier,
            "known_passed_count": self.known_passed_count,
            "required_minimum": self.required_minimum,
            "unknown_count": self.unknown_count,
            "maximum_possible_count": self.maximum_possible_count,
            "remaining_count": self.remaining_count,
            "outcome": self.outcome.value,
        }


@dataclass(frozen=True, slots=True)
class FieldTrainingProgress:
    passed: bool | None
    completed_weeks: int | None
    required_weeks: int
    outcome: EvaluationOutcome

    def __post_init__(self) -> None:
        if self.passed is not None and not isinstance(self.passed, bool):
            raise TypeError("passed must be a bool or None")
        if self.completed_weeks is not None and (
            isinstance(self.completed_weeks, bool)
            or not isinstance(self.completed_weeks, int)
            or self.completed_weeks < 0
        ):
            raise ValueError("completed_weeks must be a non-negative integer or None")
        if (
            isinstance(self.required_weeks, bool)
            or not isinstance(self.required_weeks, int)
            or self.required_weeks < 0
        ):
            raise ValueError("required_weeks must be a non-negative integer")
        if not isinstance(self.outcome, EvaluationOutcome):
            raise TypeError("outcome must be an EvaluationOutcome")

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "completed_weeks": self.completed_weeks,
            "required_weeks": self.required_weeks,
            "remaining_weeks": (
                max(self.required_weeks - self.completed_weeks, 0)
                if self.completed_weeks is not None
                else None
            ),
            "outcome": self.outcome.value,
        }


@dataclass(frozen=True, slots=True)
class ProgramProgress:
    """Structured progress facts; intentionally contains no percentage."""

    earned_credit_hours: int | float | None
    required_program_credits: int | float | None
    remaining_known_credits: int | float | None
    core_requirements: RequirementCountProgress
    zero_credit_requirements: RequirementCountProgress
    technical_electives: tuple[PoolProgress, ...] = ()
    concentrations: tuple[ConcentrationProgress, ...] = ()
    gpa: NumericProgress | None = None
    field_training: FieldTrainingProgress | None = None
    satisfied_requirement_ids: tuple[str, ...] = ()
    outstanding_requirement_ids: tuple[str, ...] = ()
    in_progress_requirement_ids: tuple[str, ...] = ()
    unknown_requirement_ids: tuple[str, ...] = ()
    review_requirement_ids: tuple[str, ...] = ()
    blocking_requirement_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "earned_credit_hours",
            "required_program_credits",
            "remaining_known_credits",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise TypeError(f"{name} must be numeric or None")
        if not isinstance(self.core_requirements, RequirementCountProgress):
            raise TypeError("core_requirements must be RequirementCountProgress")
        if not isinstance(self.zero_credit_requirements, RequirementCountProgress):
            raise TypeError("zero_credit_requirements must be RequirementCountProgress")
        if not all(isinstance(item, PoolProgress) for item in self.technical_electives):
            raise TypeError("technical_electives must contain PoolProgress values")
        if not all(
            isinstance(item, ConcentrationProgress) for item in self.concentrations
        ):
            raise TypeError("concentrations must contain ConcentrationProgress values")
        if self.gpa is not None and not isinstance(self.gpa, NumericProgress):
            raise TypeError("gpa must be NumericProgress or None")
        if self.field_training is not None and not isinstance(
            self.field_training, FieldTrainingProgress
        ):
            raise TypeError("field_training must be FieldTrainingProgress or None")
        for name in (
            "satisfied_requirement_ids",
            "outstanding_requirement_ids",
            "in_progress_requirement_ids",
            "unknown_requirement_ids",
            "review_requirement_ids",
            "blocking_requirement_ids",
        ):
            values = tuple(getattr(self, name))
            if not all(isinstance(value, str) and value.strip() for value in values):
                raise TypeError(f"{name} must contain non-empty strings")
            object.__setattr__(self, name, tuple(sorted(values)))
        object.__setattr__(
            self,
            "technical_electives",
            tuple(
                sorted(
                    self.technical_electives, key=lambda item: item.pool_id.identifier
                )
            ),
        )
        object.__setattr__(
            self,
            "concentrations",
            tuple(
                sorted(
                    self.concentrations,
                    key=lambda item: item.concentration_id.identifier,
                )
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "earned_credit_hours": self.earned_credit_hours,
            "required_program_credits": self.required_program_credits,
            "remaining_known_credits": self.remaining_known_credits,
            "core_requirements": self.core_requirements.to_dict(),
            "zero_credit_requirements": self.zero_credit_requirements.to_dict(),
            "technical_electives": [
                item.to_dict() for item in self.technical_electives
            ],
            "concentrations": [item.to_dict() for item in self.concentrations],
            "gpa": self.gpa.to_dict() if self.gpa else None,
            "field_training": (
                self.field_training.to_dict() if self.field_training else None
            ),
            "satisfied_requirement_ids": list(self.satisfied_requirement_ids),
            "outstanding_requirement_ids": list(self.outstanding_requirement_ids),
            "in_progress_requirement_ids": list(self.in_progress_requirement_ids),
            "unknown_requirement_ids": list(self.unknown_requirement_ids),
            "review_requirement_ids": list(self.review_requirement_ids),
            "blocking_requirement_ids": list(self.blocking_requirement_ids),
        }
