"""Structured future conditions produced by projected rule evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .course import CourseIdentity


class FutureCondition:
    """Nominal base for machine-readable projected requirements."""

    __slots__ = ()
    condition_type: ClassVar[str]

    def to_dict(self) -> dict[str, object]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class CourseMustBePassedCondition(FutureCondition):
    """A future evaluation is conditional on passing one course."""

    course: CourseIdentity
    rule_id: str | None = None
    expression_path: str = "root"
    condition_type: ClassVar[str] = "COURSE_MUST_BE_PASSED"

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")
        if self.rule_id is not None and (
            not isinstance(self.rule_id, str) or not self.rule_id.strip()
        ):
            raise ValueError("rule_id must be non-empty when provided")
        if (
            not isinstance(self.expression_path, str)
            or not self.expression_path.strip()
        ):
            raise ValueError("expression_path must be non-empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.condition_type,
            "course": self.course.course_id,
            "rule_id": self.rule_id,
            "expression_path": self.expression_path,
        }


@dataclass(frozen=True, slots=True)
class AllConditions(FutureCondition):
    """All child future conditions must hold."""

    children: tuple[FutureCondition, ...]
    condition_type: ClassVar[str] = "ALL"

    def __post_init__(self) -> None:
        children = tuple(self.children)
        _validate_children(children)
        object.__setattr__(self, "children", children)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.condition_type,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(frozen=True, slots=True)
class AnyConditions(FutureCondition):
    """At least one child future condition must hold."""

    children: tuple[FutureCondition, ...]
    condition_type: ClassVar[str] = "ANY"

    def __post_init__(self) -> None:
        children = tuple(self.children)
        _validate_children(children)
        object.__setattr__(self, "children", children)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.condition_type,
            "children": [child.to_dict() for child in self.children],
        }


def _validate_children(children: tuple[FutureCondition, ...]) -> None:
    if not children:
        raise ValueError("condition groups require at least one child")
    if not all(isinstance(child, FutureCondition) for child in children):
        raise TypeError("condition children must be FutureCondition values")
