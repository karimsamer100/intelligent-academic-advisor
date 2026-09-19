"""Orthogonal context values for current and projected eligibility checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .course import CourseIdentity


class RegistrationIntent(StrEnum):
    """Why the caller is asking about registering for a course."""

    NORMAL = "NORMAL"
    RETAKE_AFTER_FAILURE = "RETAKE_AFTER_FAILURE"
    RETAKE_FOR_IMPROVEMENT = "RETAKE_FOR_IMPROVEMENT"


class EvaluationHorizon(StrEnum):
    """Time perspective used for an eligibility evaluation."""

    CURRENT = "CURRENT"
    PROJECTED = "PROJECTED"


@dataclass(frozen=True, slots=True)
class ProposedTermContext:
    """Immutable same-term registration scenario for projected checks.

    ``target_course`` makes the concurrency invariant explicit: a proposed
    course list is meaningful only for the target being evaluated.
    """

    target_course: CourseIdentity
    proposed_courses: tuple[CourseIdentity, ...]
    term_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target_course, CourseIdentity):
            raise TypeError("target_course must be a CourseIdentity")
        if self.term_id is not None and (
            not isinstance(self.term_id, str) or not self.term_id.strip()
        ):
            raise ValueError("term_id must be non-empty when provided")
        courses = tuple(self.proposed_courses)
        if not all(isinstance(course, CourseIdentity) for course in courses):
            raise TypeError("proposed_courses must contain CourseIdentity values")
        if len(courses) != len(set(courses)):
            raise ValueError("proposed_courses must not contain duplicates")
        object.__setattr__(
            self,
            "proposed_courses",
            tuple(sorted(courses, key=lambda course: course.course_id)),
        )

    def contains(self, course: CourseIdentity) -> bool:
        """Return whether ``course`` is explicitly in this proposed term."""

        return course in self.proposed_courses

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic, JSON-compatible scenario representation."""

        return {
            "target_course": self.target_course.course_id,
            "proposed_courses": [course.course_id for course in self.proposed_courses],
            "term_id": self.term_id,
        }


@dataclass(frozen=True, slots=True)
class EligibilityContext:
    """Context dimensions that influence an eligibility decision."""

    intent: RegistrationIntent = RegistrationIntent.NORMAL
    horizon: EvaluationHorizon = EvaluationHorizon.CURRENT
    proposed_term: ProposedTermContext | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.intent, RegistrationIntent):
            raise TypeError("intent must be a RegistrationIntent")
        if not isinstance(self.horizon, EvaluationHorizon):
            raise TypeError("horizon must be an EvaluationHorizon")
        if self.proposed_term is not None and not isinstance(
            self.proposed_term, ProposedTermContext
        ):
            raise TypeError("proposed_term must be a ProposedTermContext or None")
        if self.horizon is EvaluationHorizon.CURRENT and self.proposed_term is not None:
            raise ValueError("current evaluations cannot carry proposed-term context")

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic machine-readable evaluation context."""

        return {
            "intent": self.intent.value,
            "horizon": self.horizon.value,
            "proposed_term": (
                self.proposed_term.to_dict() if self.proposed_term is not None else None
            ),
        }
