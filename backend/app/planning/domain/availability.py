"""Minimal future boundaries for course offering and timetable evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .course import CourseIdentity
from .planning import PlanningCoverageStatus
from .provenance import Provenance
from .semester import TermType


@dataclass(frozen=True, slots=True)
class CourseOfferingFact:
    """Typed evidence about whether a course is offered in a broad term."""

    course: CourseIdentity
    term_type: TermType
    is_offered: bool
    term_id: str | None = None
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")
        if not isinstance(self.term_type, TermType):
            raise TypeError("term_type must be a TermType")
        if not isinstance(self.is_offered, bool):
            raise TypeError("is_offered must be a bool")
        if self.term_id is not None and (
            not isinstance(self.term_id, str) or not self.term_id.strip()
        ):
            raise ValueError("term_id must be non-empty when provided")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")

    def to_dict(self) -> dict[str, object]:
        return {
            "course": self.course.course_id,
            "term_type": self.term_type.value,
            "term_id": self.term_id,
            "is_offered": self.is_offered,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


@dataclass(frozen=True, slots=True)
class CourseOfferingCoverage:
    status: PlanningCoverageStatus
    facts: tuple[CourseOfferingFact, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, PlanningCoverageStatus):
            raise TypeError("status must be a PlanningCoverageStatus")
        facts = tuple(self.facts)
        if not all(isinstance(item, CourseOfferingFact) for item in facts):
            raise TypeError("facts must contain CourseOfferingFact values")
        if len({(item.course, item.term_type, item.term_id) for item in facts}) != len(
            facts
        ):
            raise ValueError("offering facts must be unique")
        object.__setattr__(
            self,
            "facts",
            tuple(
                sorted(
                    facts,
                    key=lambda item: (
                        item.course.course_id,
                        item.term_type.value,
                        item.term_id or "",
                    ),
                )
            ),
        )

    def fact_for(
        self,
        course: CourseIdentity,
        term_type: TermType,
        term_id: str | None = None,
    ) -> CourseOfferingFact | None:
        return next(
            (
                item
                for item in self.facts
                if item.course == course
                and item.term_type is term_type
                and item.term_id == term_id
            ),
            None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "facts": [item.to_dict() for item in self.facts],
        }


class CourseOfferingProvider(Protocol):
    """Future repository boundary; no provider is implemented here."""

    @property
    def coverage(self) -> CourseOfferingCoverage: ...

    def fact_for(
        self,
        course: CourseIdentity,
        term_type: TermType,
        term_id: str | None = None,
    ) -> CourseOfferingFact | None: ...


@dataclass(frozen=True, slots=True)
class TimetableFact:
    """Future typed timetable evidence without section scheduling behavior."""

    course: CourseIdentity
    term_type: TermType
    conflict_free: bool | None
    term_id: str | None = None
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")
        if not isinstance(self.term_type, TermType):
            raise TypeError("term_type must be a TermType")
        if self.conflict_free is not None and not isinstance(self.conflict_free, bool):
            raise TypeError("conflict_free must be a bool or None")
        if self.term_id is not None and (
            not isinstance(self.term_id, str) or not self.term_id.strip()
        ):
            raise ValueError("term_id must be non-empty when provided")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")

    def to_dict(self) -> dict[str, object]:
        return {
            "course": self.course.course_id,
            "term_type": self.term_type.value,
            "term_id": self.term_id,
            "conflict_free": self.conflict_free,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


@dataclass(frozen=True, slots=True)
class TimetableCoverage:
    status: PlanningCoverageStatus
    facts: tuple[TimetableFact, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, PlanningCoverageStatus):
            raise TypeError("status must be a PlanningCoverageStatus")
        facts = tuple(self.facts)
        if not all(isinstance(item, TimetableFact) for item in facts):
            raise TypeError("facts must contain TimetableFact values")
        object.__setattr__(
            self,
            "facts",
            tuple(
                sorted(
                    facts,
                    key=lambda item: (
                        item.course.course_id,
                        item.term_type.value,
                        item.term_id or "",
                    ),
                )
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "facts": [item.to_dict() for item in self.facts],
        }


class TimetableProvider(Protocol):
    """Future repository boundary; no timetable provider is implemented here."""

    @property
    def coverage(self) -> TimetableCoverage: ...

    def fact_for(
        self,
        course: CourseIdentity,
        term_type: TermType,
        term_id: str | None = None,
    ) -> TimetableFact | None: ...


__all__ = [
    "CourseOfferingCoverage",
    "CourseOfferingFact",
    "CourseOfferingProvider",
    "TimetableCoverage",
    "TimetableFact",
    "TimetableProvider",
]
