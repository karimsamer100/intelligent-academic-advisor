"""Immutable structured rule expressions.

Expressions describe academic logic only. Approval, verification, and
provenance belong to the owning :class:`AcademicRule` record.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from .course import CourseIdentity


class ExpressionType(StrEnum):
    """Machine-readable type for a structured rule expression."""

    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    COURSE_PASSED = "COURSE_PASSED"
    COURSE_COMPLETED = "COURSE_COMPLETED"
    COURSE_CURRENTLY_REGISTERED = "COURSE_CURRENTLY_REGISTERED"
    MIN_EARNED_CREDITS = "MIN_EARNED_CREDITS"
    MAX_EARNED_CREDITS = "MAX_EARNED_CREDITS"
    MIN_GPA = "MIN_GPA"
    MAX_GPA = "MAX_GPA"


class RuleExpression:
    """Nominal base for immutable expression value objects."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class CoursePassedExpression(RuleExpression):
    """Check whether a canonical course is present in passed state."""

    course: CourseIdentity
    expression_type: ClassVar[ExpressionType] = ExpressionType.COURSE_PASSED

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")


@dataclass(frozen=True, slots=True)
class CourseCompletedExpression(RuleExpression):
    """Check whether a canonical course is present in completed state."""

    course: CourseIdentity
    expression_type: ClassVar[ExpressionType] = ExpressionType.COURSE_COMPLETED

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")


@dataclass(frozen=True, slots=True)
class CourseCurrentlyRegisteredExpression(RuleExpression):
    """Check whether a canonical course is currently registered."""

    course: CourseIdentity
    expression_type: ClassVar[ExpressionType] = (
        ExpressionType.COURSE_CURRENTLY_REGISTERED
    )

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")


@dataclass(frozen=True, slots=True)
class AndExpression(RuleExpression):
    """Require every child expression to be satisfied."""

    children: tuple[RuleExpression, ...]
    expression_type: ClassVar[ExpressionType] = ExpressionType.AND

    def __post_init__(self) -> None:
        children = tuple(self.children)
        _validate_children(children)
        object.__setattr__(self, "children", children)


@dataclass(frozen=True, slots=True)
class OrExpression(RuleExpression):
    """Require at least one child expression to be satisfied."""

    children: tuple[RuleExpression, ...]
    expression_type: ClassVar[ExpressionType] = ExpressionType.OR

    def __post_init__(self) -> None:
        children = tuple(self.children)
        _validate_children(children)
        object.__setattr__(self, "children", children)


@dataclass(frozen=True, slots=True)
class NotExpression(RuleExpression):
    """Negate one child expression."""

    operand: RuleExpression
    expression_type: ClassVar[ExpressionType] = ExpressionType.NOT

    def __post_init__(self) -> None:
        if not isinstance(self.operand, RuleExpression):
            raise TypeError("operand must be a RuleExpression")


@dataclass(frozen=True, slots=True)
class UnsupportedExpression(RuleExpression):
    """Structured sentinel for source logic not yet supported by the engine."""

    source_type: str
    course_id: str | None = None
    course_code: str | None = None
    code: str | None = None
    condition_note: str | None = None
    reason: str | None = None
    external_reference: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_type, str) or not self.source_type.strip():
            raise ValueError("source_type must be a non-empty string")
        for name in (
            "course_id",
            "course_code",
            "code",
            "condition_note",
            "reason",
        ):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string when provided")
        if self.external_reference is not None and not isinstance(
            self.external_reference, bool
        ):
            raise TypeError("external_reference must be a bool or None")


@dataclass(frozen=True, slots=True)
class MinEarnedCreditsExpression(RuleExpression):
    """Require at least ``minimum`` earned credit hours."""

    minimum: int | float
    expression_type: ClassVar[ExpressionType] = ExpressionType.MIN_EARNED_CREDITS

    def __post_init__(self) -> None:
        _validate_number(self.minimum, "minimum", nonnegative=True)


@dataclass(frozen=True, slots=True)
class MaxEarnedCreditsExpression(RuleExpression):
    """Require no more than ``maximum`` earned credit hours."""

    maximum: int | float
    expression_type: ClassVar[ExpressionType] = ExpressionType.MAX_EARNED_CREDITS

    def __post_init__(self) -> None:
        _validate_number(self.maximum, "maximum", nonnegative=True)


@dataclass(frozen=True, slots=True)
class MinGpaExpression(RuleExpression):
    """Require GPA to be at least ``minimum`` without assuming a GPA scale."""

    minimum: int | float
    expression_type: ClassVar[ExpressionType] = ExpressionType.MIN_GPA

    def __post_init__(self) -> None:
        _validate_number(self.minimum, "minimum")


@dataclass(frozen=True, slots=True)
class MaxGpaExpression(RuleExpression):
    """Require GPA to be no more than ``maximum`` without assuming a GPA scale."""

    maximum: int | float
    expression_type: ClassVar[ExpressionType] = ExpressionType.MAX_GPA

    def __post_init__(self) -> None:
        _validate_number(self.maximum, "maximum")


def _validate_children(children: tuple[RuleExpression, ...]) -> None:
    if not children:
        raise ValueError("logical expressions require at least one child")
    if not all(isinstance(child, RuleExpression) for child in children):
        raise TypeError("logical expression children must be RuleExpression values")


def _validate_number(value: object, name: str, *, nonnegative: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if nonnegative and value < 0:
        raise ValueError(f"{name} cannot be negative")
