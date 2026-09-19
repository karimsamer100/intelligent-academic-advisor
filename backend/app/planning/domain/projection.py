"""Typed boundaries for ephemeral projected and what-if academic state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .academic_state import AcademicStateLayer, HypotheticalAcademicOutcome
from .student import StudentState


class ProjectionPolicy(StrEnum):
    """Explicit assumptions used when advancing a planning projection."""

    EXPLICIT_OUTCOMES_ONLY = "EXPLICIT_OUTCOMES_ONLY"
    ASSUME_SELECTED_COURSES_PASSED = "ASSUME_SELECTED_COURSES_PASSED"


@dataclass(frozen=True, slots=True)
class ProjectedStudentState:
    """An immutable state view that never becomes observed transcript truth."""

    base_student: StudentState
    student_state: StudentState
    applied_outcomes: tuple[HypotheticalAcademicOutcome, ...]
    layer: AcademicStateLayer
    policy: ProjectionPolicy
    earned_credit_hours: int | float | None
    credits_known: bool
    assumptions: tuple[ProjectionPolicy, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.base_student, StudentState):
            raise TypeError("base_student must be a StudentState")
        if not isinstance(self.student_state, StudentState):
            raise TypeError("student_state must be a StudentState")
        outcomes = tuple(self.applied_outcomes)
        if not all(isinstance(item, HypotheticalAcademicOutcome) for item in outcomes):
            raise TypeError(
                "applied_outcomes must contain HypotheticalAcademicOutcome values"
            )
        if not isinstance(self.layer, AcademicStateLayer):
            raise TypeError("layer must be an AcademicStateLayer")
        if self.layer is AcademicStateLayer.OBSERVED:
            raise ValueError("projected state cannot have OBSERVED layer")
        if not isinstance(self.policy, ProjectionPolicy):
            raise TypeError("policy must be a ProjectionPolicy")
        if self.earned_credit_hours is not None and (
            isinstance(self.earned_credit_hours, bool)
            or not isinstance(self.earned_credit_hours, (int, float))
            or self.earned_credit_hours < 0
        ):
            raise ValueError("earned_credit_hours must be non-negative numeric or None")
        if not isinstance(self.credits_known, bool):
            raise TypeError("credits_known must be a bool")
        normalized_assumptions = tuple(dict.fromkeys(self.assumptions))
        if not all(
            isinstance(item, ProjectionPolicy) for item in normalized_assumptions
        ):
            raise TypeError("assumptions must contain ProjectionPolicy values")
        object.__setattr__(
            self,
            "applied_outcomes",
            tuple(
                sorted(
                    outcomes,
                    key=lambda item: (
                        item.sequence,
                        item.course.course_id,
                        item.outcome.value,
                    ),
                )
            ),
        )
        object.__setattr__(self, "assumptions", normalized_assumptions)

    def to_dict(self) -> dict[str, object]:
        return {
            "layer": self.layer.value,
            "policy": self.policy.value,
            "applied_outcomes": [item.to_dict() for item in self.applied_outcomes],
            "earned_credit_hours": self.earned_credit_hours,
            "credits_known": self.credits_known,
            "assumptions": [item.value for item in self.assumptions],
            "student": {
                "student_id": self.student_state.student_id,
                "fact_layer": self.student_state.fact_layer.value,
            },
        }


__all__ = [
    "AcademicStateLayer",
    "HypotheticalAcademicOutcome",
    "ProjectedStudentState",
    "ProjectionPolicy",
]
