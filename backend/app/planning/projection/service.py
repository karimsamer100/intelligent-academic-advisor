"""Pure deterministic transitions for projected and what-if student state."""

from __future__ import annotations

from dataclasses import replace

from ..domain.academic_state import (
    AcademicStateLayer,
    FactStatus,
    HypotheticalAcademicOutcome,
)
from ..domain.projection import ProjectedStudentState, ProjectionPolicy
from ..domain.course import CourseIdentity
from ..domain.student import StudentState
from ..domain.student_history import AttemptOutcome


class HypotheticalStateTransitionService:
    """Apply ephemeral outcomes without mutating observed state."""

    def apply(
        self,
        student: StudentState,
        outcomes: tuple[HypotheticalAcademicOutcome, ...],
        *,
        policy: ProjectionPolicy = ProjectionPolicy.EXPLICIT_OUTCOMES_ONLY,
    ) -> ProjectedStudentState:
        if not isinstance(student, StudentState):
            raise TypeError("student must be a StudentState")
        if not isinstance(policy, ProjectionPolicy):
            raise TypeError("policy must be a ProjectionPolicy")
        normalized = tuple(outcomes)
        if not all(
            isinstance(item, HypotheticalAcademicOutcome) for item in normalized
        ):
            raise TypeError("outcomes must contain HypotheticalAcademicOutcome values")
        previous = student.projected_outcomes
        combined = (*previous, *normalized)
        layer = _layer_for(student, normalized)
        assumptions = tuple(
            dict.fromkeys(
                (
                    *student.projection_assumptions,
                    policy.value,
                )
            )
        )
        earned, known = _project_credits(student, normalized)
        projected_student = replace(
            student,
            fact_layer=layer,
            projected_outcomes=combined,
            projection_assumptions=assumptions,
            earned_credit_hours=earned,
        )
        return ProjectedStudentState(
            base_student=student,
            student_state=projected_student,
            applied_outcomes=combined,
            layer=layer,
            policy=policy,
            earned_credit_hours=earned,
            credits_known=known,
            assumptions=tuple(
                item
                for item in (policy,)
                if item is not ProjectionPolicy.EXPLICIT_OUTCOMES_ONLY
            ),
        )


def _layer_for(
    student: StudentState,
    outcomes: tuple[HypotheticalAcademicOutcome, ...],
) -> AcademicStateLayer:
    if student.fact_layer is AcademicStateLayer.HYPOTHETICAL or any(
        item.layer is AcademicStateLayer.HYPOTHETICAL for item in outcomes
    ):
        return AcademicStateLayer.HYPOTHETICAL
    return AcademicStateLayer.PROJECTED


def _project_credits(
    student: StudentState,
    outcomes: tuple[HypotheticalAcademicOutcome, ...],
) -> tuple[int | float | None, bool]:
    if not outcomes:
        return student.earned_credit_hours, student.earned_credit_hours is not None
    if student.earned_credit_hours is None:
        return None, False

    total: int | float = student.earned_credit_hours
    by_course: dict[CourseIdentity, list[HypotheticalAcademicOutcome]] = {}
    for item in outcomes:
        by_course.setdefault(item.course, []).append(item)
    for course, course_outcomes in sorted(
        by_course.items(), key=lambda item: item[0].course_id
    ):
        previous = student.projected_outcomes_for(course)
        if previous and any(
            item.outcome in (AttemptOutcome.FAILED, AttemptOutcome.UNKNOWN)
            for item in course_outcomes
        ):
            return None, False
        if student.pass_status(course) is FactStatus.KNOWN_TRUE:
            continue
        ordered = tuple(
            sorted(
                course_outcomes,
                key=lambda value: (value.sequence, value.outcome.value),
            )
        )
        if _projected_status(student, course, ordered) is not FactStatus.KNOWN_TRUE:
            continue
        pass_outcomes = tuple(
            item for item in ordered if item.outcome is AttemptOutcome.PASSED
        )
        if not pass_outcomes:
            continue
        credit_hours = pass_outcomes[-1].earned_credit_hours
        if credit_hours is None:
            return None, False
        total += credit_hours
    return total, True


def _projected_status(
    student: StudentState,
    course: CourseIdentity,
    outcomes: tuple[HypotheticalAcademicOutcome, ...],
) -> FactStatus:
    projected = replace(
        student,
        fact_layer=AcademicStateLayer.PROJECTED,
        projected_outcomes=(*student.projected_outcomes, *outcomes),
    )
    return projected.pass_status(course)


__all__ = ["HypotheticalStateTransitionService"]
