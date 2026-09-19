"""Recursive mapping from Academic Data expressions to Planning expressions."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.course import CourseIdentity, Program, Regulation
from ...domain.errors import PlanningErrorCode
from ...domain.expressions import (
    AndExpression,
    CourseConcurrentExpression,
    CoursePassedExpression,
    EntryRequirementExpression,
    MinEarnedCreditsExpression,
    NotExpression,
    OrExpression,
    RuleExpression,
    UnsupportedExpression,
)
from ...domain.entry import EntryRequirementReference, RequirementApplicability
from ...domain.reasons import ReasonCode
from .academic_data_types import (
    AcademicDataDiagnostic,
    AcademicDataDiagnosticCode,
)
from .academic_json_loader import RawExpression


@dataclass(frozen=True, slots=True)
class ExpressionMappingResult:
    expression: RuleExpression | None
    diagnostics: tuple[AcademicDataDiagnostic, ...] = ()
    contains_unsupported: bool = False


def map_expression(
    expression: RawExpression | None,
    *,
    regulation: Regulation,
    program: Program,
    record_id: str,
) -> ExpressionMappingResult:
    if expression is None:
        return ExpressionMappingResult(
            expression=None,
            diagnostics=(
                _diagnostic(
                    AcademicDataDiagnosticCode.INCOMPLETE_EXPRESSION,
                    planning_code=PlanningErrorCode.UNSUPPORTED_RULE,
                    record_id=record_id,
                    field="expression",
                    requires_human_review=True,
                ),
            ),
            contains_unsupported=True,
        )

    if expression.source_type in {"AND", "OR"}:
        children: list[RuleExpression] = []
        diagnostics: list[AcademicDataDiagnostic] = []
        contains_unsupported = False
        for child in expression.conditions:
            mapped = map_expression(
                child,
                regulation=regulation,
                program=program,
                record_id=record_id,
            )
            diagnostics.extend(mapped.diagnostics)
            contains_unsupported = contains_unsupported or mapped.contains_unsupported
            if mapped.expression is None:
                contains_unsupported = True
                children.append(
                    UnsupportedExpression(
                        source_type="INCOMPLETE_EXPRESSION",
                        reason="child expression could not be mapped",
                    )
                )
            else:
                children.append(mapped.expression)
        try:
            mapped_expression: RuleExpression
            if expression.source_type == "AND":
                mapped_expression = AndExpression(tuple(children))
            else:
                mapped_expression = OrExpression(tuple(children))
        except (TypeError, ValueError):
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.INCOMPLETE_EXPRESSION,
                    planning_code=PlanningErrorCode.UNSUPPORTED_RULE,
                    record_id=record_id,
                    source_type=expression.source_type,
                    field="expression.conditions",
                    requires_human_review=True,
                )
            )
            return ExpressionMappingResult(
                expression=UnsupportedExpression(
                    source_type="INCOMPLETE_EXPRESSION",
                    reason="logical expression has no valid children",
                ),
                diagnostics=tuple(diagnostics),
                contains_unsupported=True,
            )
        return ExpressionMappingResult(
            expression=mapped_expression,
            diagnostics=tuple(diagnostics),
            contains_unsupported=contains_unsupported,
        )

    if expression.source_type == "NOT":
        if len(expression.conditions) != 1:
            return ExpressionMappingResult(
                expression=UnsupportedExpression(
                    source_type="NOT",
                    reason="NOT requires exactly one operand",
                ),
                diagnostics=(
                    _diagnostic(
                        AcademicDataDiagnosticCode.INCOMPLETE_EXPRESSION,
                        planning_code=PlanningErrorCode.UNSUPPORTED_RULE,
                        record_id=record_id,
                        source_type="NOT",
                        field="expression.conditions",
                        requires_human_review=True,
                    ),
                ),
                contains_unsupported=True,
            )
        mapped = map_expression(
            expression.conditions[0],
            regulation=regulation,
            program=program,
            record_id=record_id,
        )
        operand = mapped.expression or UnsupportedExpression(
            source_type="INCOMPLETE_EXPRESSION",
            reason="NOT operand could not be mapped",
        )
        return ExpressionMappingResult(
            expression=NotExpression(operand),
            diagnostics=mapped.diagnostics,
            contains_unsupported=mapped.contains_unsupported,
        )

    if expression.source_type == "COURSE_PASSED":
        return _map_course_passed(expression, regulation, program, record_id)

    if expression.source_type == "CONCURRENT_COURSE":
        return _map_course_concurrent(expression, regulation, program, record_id)

    if expression.source_type == "MIN_EARNED_CREDITS":
        if isinstance(expression.value, bool) or not isinstance(
            expression.value, (int, float)
        ):
            return _unsupported_result(
                expression,
                record_id,
                code=AcademicDataDiagnosticCode.INCOMPLETE_EXPRESSION,
                planning_code=PlanningErrorCode.UNSUPPORTED_RULE,
                reason="MIN_EARNED_CREDITS requires a numeric value",
            )
        try:
            mapped = MinEarnedCreditsExpression(expression.value)
        except (TypeError, ValueError):
            return _unsupported_result(
                expression,
                record_id,
                code=AcademicDataDiagnosticCode.INCOMPLETE_EXPRESSION,
                planning_code=PlanningErrorCode.UNSUPPORTED_RULE,
                reason="MIN_EARNED_CREDITS value is invalid",
            )
        return ExpressionMappingResult(mapped)

    return _unsupported_result(
        expression,
        record_id,
        code=AcademicDataDiagnosticCode.UNSUPPORTED_EXPRESSION,
        planning_code=PlanningErrorCode.UNSUPPORTED_RULE,
        reason="source expression type is not supported by the Planning Engine",
    )


def _map_course_passed(
    expression: RawExpression,
    regulation: Regulation,
    program: Program,
    record_id: str,
) -> ExpressionMappingResult:
    if expression.course_id is None:
        return _unsupported_result(
            expression,
            record_id,
            code=AcademicDataDiagnosticCode.INCOMPLETE_EXPRESSION,
            planning_code=PlanningErrorCode.INVALID_REQUEST,
            reason="COURSE_PASSED requires a canonical course_id",
        )
    try:
        course = CourseIdentity.parse(expression.course_id)
    except ValueError:
        return _unsupported_result(
            expression,
            record_id,
            code=AcademicDataDiagnosticCode.MALFORMED_IDENTITY,
            planning_code=PlanningErrorCode.INVALID_REQUEST,
            reason="COURSE_PASSED contains a malformed course identity",
        )
    if course.regulation is not regulation or course.program != program:
        return _unsupported_result(
            expression,
            record_id,
            code=AcademicDataDiagnosticCode.RULE_TARGET_MISMATCH,
            planning_code=PlanningErrorCode.INVALID_REQUEST,
            reason="COURSE_PASSED course is outside the rule scope",
        )
    if (
        expression.course_code is not None
        and expression.course_code != course.course_code
    ):
        return _unsupported_result(
            expression,
            record_id,
            code=AcademicDataDiagnosticCode.RULE_TARGET_MISMATCH,
            planning_code=PlanningErrorCode.INVALID_REQUEST,
            reason="course_code does not match course_id",
        )
    return ExpressionMappingResult(CoursePassedExpression(course))


def _map_course_concurrent(
    expression: RawExpression,
    regulation: Regulation,
    program: Program,
    record_id: str,
) -> ExpressionMappingResult:
    if expression.course_id is None:
        return _unsupported_result(
            expression,
            record_id,
            code=AcademicDataDiagnosticCode.INCOMPLETE_EXPRESSION,
            planning_code=PlanningErrorCode.INVALID_REQUEST,
            reason="CONCURRENT_COURSE requires a canonical course_id",
        )
    try:
        course = CourseIdentity.parse(expression.course_id)
    except ValueError:
        return _unsupported_result(
            expression,
            record_id,
            code=AcademicDataDiagnosticCode.MALFORMED_IDENTITY,
            planning_code=PlanningErrorCode.INVALID_REQUEST,
            reason="CONCURRENT_COURSE contains a malformed course identity",
        )
    if course.regulation is not regulation or course.program != program:
        return _unsupported_result(
            expression,
            record_id,
            code=AcademicDataDiagnosticCode.RULE_TARGET_MISMATCH,
            planning_code=PlanningErrorCode.INVALID_REQUEST,
            reason="CONCURRENT_COURSE course is outside the rule scope",
        )
    if (
        expression.course_code is not None
        and expression.course_code != course.course_code
    ):
        return _unsupported_result(
            expression,
            record_id,
            code=AcademicDataDiagnosticCode.RULE_TARGET_MISMATCH,
            planning_code=PlanningErrorCode.INVALID_REQUEST,
            reason="course_code does not match course_id",
        )
    return ExpressionMappingResult(CourseConcurrentExpression(course))


def _unsupported_result(
    expression: RawExpression,
    record_id: str,
    *,
    code: AcademicDataDiagnosticCode,
    planning_code: PlanningErrorCode,
    reason: str,
) -> ExpressionMappingResult:
    unsupported_expression: RuleExpression
    if expression.source_type == "ENTRY_REQUIREMENT":
        unsupported_expression = EntryRequirementExpression(
            source_type=expression.source_type,
            course_id=expression.course_id,
            course_code=expression.course_code,
            code=expression.code,
            condition_note=expression.condition_note,
            reason=expression.reason or reason,
            external_reference=expression.external_reference,
            reference=EntryRequirementReference(
                code=(
                    expression.code
                    or expression.course_code
                    or expression.condition_note
                    or "UNSPECIFIED_ENTRY_REQUIREMENT"
                ),
                applicability=RequirementApplicability.UNKNOWN,
            ),
        )
    else:
        unsupported_expression = UnsupportedExpression(
            source_type=expression.source_type,
            course_id=expression.course_id,
            course_code=expression.course_code,
            code=expression.code,
            condition_note=expression.condition_note,
            reason=expression.reason or reason,
            external_reference=expression.external_reference,
        )
    return ExpressionMappingResult(
        expression=unsupported_expression,
        diagnostics=(
            _diagnostic(
                code,
                planning_code=planning_code,
                reason_codes=(
                    ReasonCode.UNSUPPORTED_RULE
                    if planning_code is PlanningErrorCode.UNSUPPORTED_RULE
                    else ReasonCode.MISSING_REQUIRED_DATA,
                ),
                record_id=record_id,
                source_type=expression.source_type,
                field="expression",
                requires_human_review=True,
            ),
        ),
        contains_unsupported=True,
    )


def _diagnostic(
    code: AcademicDataDiagnosticCode,
    *,
    planning_code: PlanningErrorCode,
    reason_codes: tuple[ReasonCode, ...] = (),
    record_id: str | None = None,
    source_type: str | None = None,
    field: str | None = None,
    requires_human_review: bool = False,
) -> AcademicDataDiagnostic:
    return AcademicDataDiagnostic(
        code=code,
        planning_code=planning_code,
        reason_codes=reason_codes,
        record_id=record_id,
        source_type=source_type,
        field=field,
        requires_human_review=requires_human_review,
    )
