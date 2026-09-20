from dataclasses import FrozenInstanceError

import pytest

from app.planning.domain.course import CourseIdentity
from app.planning.domain.expressions import (
    AndExpression,
    CourseCompletedExpression,
    CourseCurrentlyRegisteredExpression,
    CoursePassedExpression,
    ExpressionType,
    MaxEarnedCreditsExpression,
    MaxGpaExpression,
    MinEarnedCreditsExpression,
    MinGpaExpression,
    NotExpression,
    OrExpression,
    UnsupportedExpression,
)


def test_course_passed_expression_is_typed_and_immutable() -> None:
    course = CourseIdentity.parse("R23:CAIE:CSE241")
    expression = CoursePassedExpression(course)

    assert expression.expression_type is ExpressionType.COURSE_PASSED
    assert expression.course is course
    with pytest.raises(FrozenInstanceError):
        expression.course = CourseIdentity.parse("R23:CAIE:CSE281")


def test_logical_expressions_support_recursive_immutable_children() -> None:
    first = CoursePassedExpression(CourseIdentity.parse("R23:CAIE:CSE241"))
    second = CourseCompletedExpression(CourseIdentity.parse("R23:CAIE:CSE281"))
    nested = OrExpression((second, MinEarnedCreditsExpression(90)))
    expression = AndExpression((first, nested))

    assert expression.expression_type is ExpressionType.AND
    assert expression.children == (first, nested)
    assert nested.expression_type is ExpressionType.OR
    with pytest.raises(FrozenInstanceError):
        expression.children = ()


def test_not_expression_wraps_one_expression() -> None:
    operand = CourseCurrentlyRegisteredExpression(
        CourseIdentity.parse("R23:CAIE:CSE341")
    )
    expression = NotExpression(operand)

    assert expression.expression_type is ExpressionType.NOT
    assert expression.operand is operand


def test_leaf_expressions_capture_typed_thresholds() -> None:
    assert MaxEarnedCreditsExpression(180).maximum == 180
    assert MinGpaExpression(2.0).minimum == 2.0
    assert MaxGpaExpression(4.0).maximum == 4.0


def test_logical_expressions_reject_empty_or_untyped_operands() -> None:
    with pytest.raises(ValueError):
        AndExpression(())
    with pytest.raises(ValueError):
        OrExpression(())
    with pytest.raises(TypeError):
        NotExpression(())  # type: ignore[arg-type]


def test_unsupported_expression_preserves_structured_source_fields() -> None:
    expression = UnsupportedExpression(
        source_type="CONDITIONAL_COURSE_PASSED",
        course_code="ASU041",
        condition_note="Only if applicable",
        external_reference=True,
    )

    assert expression.source_type == "CONDITIONAL_COURSE_PASSED"
    assert expression.course_code == "ASU041"
    assert expression.condition_note == "Only if applicable"
    assert expression.external_reference is True


def test_unsupported_expression_rejects_empty_source_type() -> None:
    with pytest.raises(ValueError, match="source_type"):
        UnsupportedExpression(source_type="")
