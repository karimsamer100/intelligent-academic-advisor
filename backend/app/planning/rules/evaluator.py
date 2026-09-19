"""Deterministic evaluation of structured academic rules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from ..domain.conditions import (
    AllConditions,
    AnyConditions,
    CourseMustBePassedCondition,
    FutureCondition,
)
from ..domain.context import EligibilityContext, EvaluationHorizon
from ..domain.course import CourseIdentity
from ..domain.evaluation import EvaluationOutcome, RuleEvaluationResult
from ..domain.expressions import (
    AndExpression,
    CourseCompletedExpression,
    CourseConcurrentExpression,
    CourseCurrentlyRegisteredExpression,
    CoursePassedExpression,
    MaxEarnedCreditsExpression,
    MaxGpaExpression,
    MinEarnedCreditsExpression,
    MinGpaExpression,
    NotExpression,
    OrExpression,
    RuleExpression,
    UnsupportedExpression,
)
from ..domain.lifecycle import ApprovalStatus
from ..domain.provenance import Provenance
from ..domain.reasons import ReasonCode
from ..domain.results import ResultMetadata
from ..domain.rules import AcademicRule
from ..domain.student import AcademicHistoryCoverage, FactStatus, StudentState
from ..domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceMetadata,
    TraceNodeType,
    TraceValue,
)
from ..domain.version import DatasetVersion
from ..policy import ExecutionPolicy, PolicyDecision


@dataclass(frozen=True, slots=True)
class _ExpressionEvaluation:
    outcome: EvaluationOutcome
    trace_node: DecisionTraceNode
    reason_codes: tuple[ReasonCode, ...] = ()
    conditions: tuple[FutureCondition, ...] = ()


@dataclass(frozen=True, slots=True)
class RuleEvaluator:
    """Pure evaluator over an already-loaded rule and student state."""

    policy: ExecutionPolicy
    dataset_version: DatasetVersion
    engine_version: str | None = None
    ruleset_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.policy, ExecutionPolicy):
            raise TypeError("policy must be an ExecutionPolicy")
        if not isinstance(self.dataset_version, DatasetVersion):
            raise TypeError("dataset_version must be a DatasetVersion")
        for name in ("engine_version", "ruleset_version"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string when provided")

    def evaluate(
        self,
        rule: AcademicRule,
        student: StudentState,
    ) -> RuleEvaluationResult:
        """Evaluate using the backward-compatible current-state defaults."""

        return self._evaluate(
            rule,
            student,
            context=EligibilityContext(),
        )

    def evaluate_with_context(
        self,
        rule: AcademicRule,
        student: StudentState,
        context: EligibilityContext,
    ) -> RuleEvaluationResult:
        """Evaluate one rule with explicit current/projected context."""

        if not isinstance(context, EligibilityContext):
            raise TypeError("context must be an EligibilityContext")
        return self._evaluate(rule, student, context=context)

    def _evaluate(
        self,
        rule: AcademicRule,
        student: StudentState,
        *,
        context: EligibilityContext | None = None,
    ) -> RuleEvaluationResult:
        """Evaluate one rule without consulting repositories or external systems."""

        if not isinstance(rule, AcademicRule):
            raise TypeError("rule must be an AcademicRule")
        if not isinstance(student, StudentState):
            raise TypeError("student must be a StudentState")
        context = context or EligibilityContext()
        if not isinstance(context, EligibilityContext):
            raise TypeError("context must be an EligibilityContext")
        decision = self.policy.assess(
            rule.approval_status,
            verification_status=rule.verification_status,
            critical=rule.critical_for_planner,
        )
        if not decision.allowed:
            evaluation = self._policy_evaluation(rule.rule_id, decision)
        elif rule.expression is None:
            evaluation = self._unsupported_evaluation(rule.rule_id, "MISSING")
        else:
            evaluation = self._evaluate_expression(
                rule.expression,
                student,
                rule.rule_id,
                context=context,
            )
        provenance = self._provenance(rule)
        trace_node = replace(
            evaluation.trace_node,
            provenance=provenance,
            metadata=(TraceMetadata("rule_id", rule.rule_id),)
            + evaluation.trace_node.metadata,
        )
        trace = DecisionTrace(trace_node)
        reason_codes = _unique_reason_codes(
            (*decision.reason_codes, *evaluation.reason_codes)
        )
        indeterminate = evaluation.outcome is EvaluationOutcome.INDETERMINATE
        requires_human_review = (
            decision.requires_human_review
            or (
                evaluation.outcome is not EvaluationOutcome.SATISFIED
                and _trace_contains_unresolved_child(evaluation.trace_node)
            )
            or (indeterminate and not evaluation.conditions)
        )
        metadata = ResultMetadata(
            dataset_version=self.dataset_version,
            execution_mode=decision.mode,
            authoritative=decision.authoritative
            and not indeterminate
            and not requires_human_review,
            approval_status=decision.approval_status,
            verification_status=decision.verification_status,
            reason_codes=reason_codes,
            provenance=provenance,
            decision_trace=trace,
            requires_human_review=requires_human_review,
            engine_version=self.engine_version,
            ruleset_version=self.ruleset_version,
        )
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            outcome=evaluation.outcome,
            metadata=metadata,
            conditions=evaluation.conditions,
        )

    @classmethod
    def _evaluate_expression(
        cls,
        expression: RuleExpression,
        student: StudentState,
        rule_id: str,
        path: str = "root",
        *,
        context: EligibilityContext,
    ) -> _ExpressionEvaluation:
        """Evaluate an expression recursively and preserve every child trace."""

        if isinstance(expression, AndExpression):
            children = tuple(
                cls._evaluate_expression(
                    child,
                    student,
                    rule_id,
                    f"{path}.{index}",
                    context=context,
                )
                for index, child in enumerate(expression.children)
            )
            outcomes = tuple(child.outcome for child in children)
            if any(outcome is EvaluationOutcome.UNSATISFIED for outcome in outcomes):
                outcome = EvaluationOutcome.UNSATISFIED
            elif all(outcome is EvaluationOutcome.SATISFIED for outcome in outcomes):
                outcome = EvaluationOutcome.SATISFIED
            else:
                outcome = EvaluationOutcome.INDETERMINATE
            return cls._logical_node(
                rule_id,
                path,
                TraceCode.AND,
                outcome,
                children,
                conditions=_logical_conditions(
                    children, operator="AND", outcome=outcome
                ),
            )

        if isinstance(expression, OrExpression):
            children = tuple(
                cls._evaluate_expression(
                    child,
                    student,
                    rule_id,
                    f"{path}.{index}",
                    context=context,
                )
                for index, child in enumerate(expression.children)
            )
            outcomes = tuple(child.outcome for child in children)
            if any(outcome is EvaluationOutcome.SATISFIED for outcome in outcomes):
                outcome = EvaluationOutcome.SATISFIED
            elif all(outcome is EvaluationOutcome.UNSATISFIED for outcome in outcomes):
                outcome = EvaluationOutcome.UNSATISFIED
            else:
                outcome = EvaluationOutcome.INDETERMINATE
            return cls._logical_node(
                rule_id,
                path,
                TraceCode.OR,
                outcome,
                children,
                conditions=_logical_conditions(
                    children, operator="OR", outcome=outcome
                ),
            )

        if isinstance(expression, NotExpression):
            child = cls._evaluate_expression(
                expression.operand,
                student,
                rule_id,
                f"{path}.0",
                context=context,
            )
            outcome = {
                EvaluationOutcome.SATISFIED: EvaluationOutcome.UNSATISFIED,
                EvaluationOutcome.UNSATISFIED: EvaluationOutcome.SATISFIED,
                EvaluationOutcome.INDETERMINATE: EvaluationOutcome.INDETERMINATE,
            }[child.outcome]
            return cls._logical_node(
                rule_id,
                path,
                TraceCode.NOT,
                outcome,
                (child,),
                conditions=(
                    child.conditions
                    if outcome is EvaluationOutcome.INDETERMINATE
                    else ()
                ),
            )

        if isinstance(expression, CoursePassedExpression):
            course = expression.course
            status = student.pass_status(course)
            if status is FactStatus.UNKNOWN:
                return cls._unknown_course_leaf(
                    rule_id,
                    path,
                    TraceCode.COURSE_PASSED,
                    course,
                )
            if (
                status is FactStatus.KNOWN_FALSE
                and context.horizon is EvaluationHorizon.PROJECTED
                and student.registration_status(course) is FactStatus.KNOWN_TRUE
                and student.history_coverage is AcademicHistoryCoverage.COMPLETE
            ):
                condition = CourseMustBePassedCondition(
                    course=course,
                    rule_id=rule_id,
                    expression_path=path,
                )
                return cls._leaf(
                    rule_id,
                    path,
                    TraceCode.COURSE_PASSED,
                    subject=course,
                    expected_value=True,
                    actual_value=False,
                    outcome=EvaluationOutcome.INDETERMINATE,
                    reason_codes=(ReasonCode.CONDITIONAL_REQUIREMENT,),
                    conditions=(condition,),
                )
            return cls._course_leaf(
                rule_id,
                path,
                TraceCode.COURSE_PASSED,
                course,
                status is FactStatus.KNOWN_TRUE,
            )

        if isinstance(expression, CourseCompletedExpression):
            course = expression.course
            status = student.completion_status(course)
            if status is FactStatus.UNKNOWN:
                return cls._unknown_course_leaf(
                    rule_id,
                    path,
                    TraceCode.COURSE_COMPLETED,
                    course,
                )
            return cls._course_leaf(
                rule_id,
                path,
                TraceCode.COURSE_COMPLETED,
                course,
                status is FactStatus.KNOWN_TRUE,
            )

        if isinstance(expression, CourseCurrentlyRegisteredExpression):
            course = expression.course
            status = student.registration_status(course)
            if status is FactStatus.UNKNOWN:
                return cls._unknown_course_leaf(
                    rule_id,
                    path,
                    TraceCode.COURSE_CURRENTLY_REGISTERED,
                    course,
                )
            return cls._course_leaf(
                rule_id,
                path,
                TraceCode.COURSE_CURRENTLY_REGISTERED,
                course,
                status is FactStatus.KNOWN_TRUE,
            )

        if isinstance(expression, CourseConcurrentExpression):
            return cls._concurrent_leaf(
                rule_id,
                path,
                expression.course,
                context,
            )

        if isinstance(expression, MinEarnedCreditsExpression):
            actual = student.earned_credit_hours
            return cls._numeric_leaf(
                rule_id,
                path,
                TraceCode.MIN_EARNED_CREDITS,
                expected=expression.minimum,
                actual=actual,
                comparison=lambda value: value >= expression.minimum,
            )

        if isinstance(expression, MaxEarnedCreditsExpression):
            actual = student.earned_credit_hours
            return cls._numeric_leaf(
                rule_id,
                path,
                TraceCode.MAX_EARNED_CREDITS,
                expected=expression.maximum,
                actual=actual,
                comparison=lambda value: value <= expression.maximum,
            )

        if isinstance(expression, MinGpaExpression):
            return cls._gpa_leaf(
                rule_id,
                path,
                expression.minimum,
                student.gpa,
                TraceCode.MIN_GPA,
                lambda actual: actual >= expression.minimum,
            )

        if isinstance(expression, MaxGpaExpression):
            return cls._gpa_leaf(
                rule_id,
                path,
                expression.maximum,
                student.gpa,
                TraceCode.MAX_GPA,
                lambda actual: actual <= expression.maximum,
            )

        if isinstance(expression, UnsupportedExpression):
            return cls._unsupported_expression_evaluation(
                rule_id,
                path,
                expression,
            )

        return cls._unsupported_evaluation(rule_id, type(expression).__name__)

    @staticmethod
    def _policy_evaluation(
        rule_id: str,
        decision: PolicyDecision,
    ) -> _ExpressionEvaluation:
        """Create a trace for a rule blocked before expression evaluation."""

        approval_status = decision.approval_status
        if approval_status is ApprovalStatus.BLOCKED:
            status = DecisionStatus.BLOCKED
        elif approval_status is ApprovalStatus.CONFLICTED:
            status = DecisionStatus.CONFLICTED
        else:
            status = DecisionStatus.NOT_EVALUATED
        reason_codes = tuple(decision.reason_codes)
        trace_node = DecisionTraceNode(
            node_id=rule_id,
            code=TraceCode.RULE,
            node_type=TraceNodeType.RULE_CHECK,
            status=status,
            reason_codes=reason_codes,
        )
        return _ExpressionEvaluation(
            EvaluationOutcome.INDETERMINATE,
            trace_node,
            reason_codes,
        )

    @staticmethod
    def _unsupported_evaluation(
        rule_id: str,
        expression_type: str,
        path: str = "root",
        metadata: tuple[TraceMetadata, ...] = (),
    ) -> _ExpressionEvaluation:
        trace_node = DecisionTraceNode(
            node_id=_node_id(rule_id, path),
            code=TraceCode.RULE,
            node_type=TraceNodeType.RULE_CHECK,
            status=DecisionStatus.UNSUPPORTED,
            reason_codes=(ReasonCode.UNSUPPORTED_RULE,),
            metadata=(TraceMetadata("expression_type", expression_type), *metadata),
        )
        return _ExpressionEvaluation(
            EvaluationOutcome.INDETERMINATE,
            trace_node,
            (ReasonCode.UNSUPPORTED_RULE,),
        )

    @classmethod
    def _unsupported_expression_evaluation(
        cls,
        rule_id: str,
        path: str,
        expression: UnsupportedExpression,
    ) -> _ExpressionEvaluation:
        metadata: list[TraceMetadata] = []
        for key, value in (
            ("course_id", expression.course_id),
            ("course_code", expression.course_code),
            ("code", expression.code),
            ("condition_note", expression.condition_note),
            ("reason", expression.reason),
            ("external_reference", expression.external_reference),
        ):
            if value is not None:
                metadata.append(TraceMetadata(key, value))
        return cls._unsupported_evaluation(
            rule_id,
            expression.source_type,
            path,
            tuple(metadata),
        )

    @classmethod
    def _logical_node(
        cls,
        rule_id: str,
        path: str,
        code: TraceCode,
        outcome: EvaluationOutcome,
        children: tuple[_ExpressionEvaluation, ...],
        conditions: tuple[FutureCondition, ...] = (),
    ) -> _ExpressionEvaluation:
        reason_codes = _unique_reason_codes(
            tuple(code for child in children for code in child.reason_codes)
        )
        trace_node = DecisionTraceNode(
            node_id=_node_id(rule_id, path),
            code=code,
            node_type=TraceNodeType.LOGICAL,
            status=_trace_status(outcome, conditional=bool(conditions)),
            reason_codes=reason_codes,
            children=tuple(child.trace_node for child in children),
        )
        return _ExpressionEvaluation(outcome, trace_node, reason_codes, conditions)

    @classmethod
    def _concurrent_leaf(
        cls,
        rule_id: str,
        path: str,
        course: CourseIdentity,
        context: EligibilityContext,
    ) -> _ExpressionEvaluation:
        proposed = context.proposed_term
        if proposed is None:
            return cls._leaf(
                rule_id,
                path,
                TraceCode.COURSE_CONCURRENT,
                subject=course,
                expected_value=True,
                actual_value=None,
                outcome=EvaluationOutcome.INDETERMINATE,
                reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
            )
        if not proposed.contains(proposed.target_course):
            return cls._leaf(
                rule_id,
                path,
                TraceCode.COURSE_CONCURRENT,
                subject=course,
                expected_value=True,
                actual_value=None,
                outcome=EvaluationOutcome.INDETERMINATE,
                reason_codes=(ReasonCode.CONCURRENT_CONTEXT_INVALID,),
            )
        actual = proposed.contains(course)
        return cls._leaf(
            rule_id,
            path,
            TraceCode.COURSE_CONCURRENT,
            subject=course,
            expected_value=True,
            actual_value=actual,
            outcome=_boolean_outcome(actual),
        )

    @classmethod
    def _course_leaf(
        cls,
        rule_id: str,
        path: str,
        code: TraceCode,
        course: CourseIdentity,
        actual: bool,
    ) -> _ExpressionEvaluation:
        return cls._leaf(
            rule_id,
            path,
            code,
            subject=course,
            expected_value=True,
            actual_value=actual,
            outcome=_boolean_outcome(actual),
        )

    @classmethod
    def _unknown_course_leaf(
        cls,
        rule_id: str,
        path: str,
        code: TraceCode,
        course: CourseIdentity,
    ) -> _ExpressionEvaluation:
        return cls._leaf(
            rule_id,
            path,
            code,
            subject=course,
            expected_value=True,
            actual_value=None,
            outcome=EvaluationOutcome.INDETERMINATE,
            reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
        )

    @classmethod
    def _gpa_leaf(
        cls,
        rule_id: str,
        path: str,
        expected: int | float,
        actual: int | float | None,
        code: TraceCode,
        comparison: Callable[[int | float], bool],
    ) -> _ExpressionEvaluation:
        return cls._numeric_leaf(
            rule_id,
            path,
            code,
            expected=expected,
            actual=actual,
            comparison=comparison,
        )

    @classmethod
    def _numeric_leaf(
        cls,
        rule_id: str,
        path: str,
        code: TraceCode,
        *,
        expected: int | float,
        actual: int | float | None,
        comparison: Callable[[int | float], bool],
    ) -> _ExpressionEvaluation:
        if actual is None:
            return cls._leaf(
                rule_id,
                path,
                code,
                expected_value=expected,
                actual_value=actual,
                outcome=EvaluationOutcome.INDETERMINATE,
                reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
            )
        return cls._leaf(
            rule_id,
            path,
            code,
            expected_value=expected,
            actual_value=actual,
            outcome=_boolean_outcome(comparison(actual)),
        )

    @staticmethod
    def _leaf(
        rule_id: str,
        path: str,
        code: TraceCode,
        *,
        subject: CourseIdentity | str | None = None,
        expected_value: TraceValue = None,
        actual_value: TraceValue = None,
        outcome: EvaluationOutcome,
        reason_codes: tuple[ReasonCode, ...] = (),
        conditions: tuple[FutureCondition, ...] = (),
    ) -> _ExpressionEvaluation:
        trace_node = DecisionTraceNode(
            node_id=_node_id(rule_id, path),
            code=code,
            node_type=(
                TraceNodeType.COURSE_CHECK
                if subject is not None
                else TraceNodeType.VALUE_CHECK
            ),
            status=_trace_status(outcome, conditional=bool(conditions)),
            subject=subject,
            expected_value=expected_value,
            actual_value=actual_value,
            reason_codes=reason_codes,
        )
        return _ExpressionEvaluation(outcome, trace_node, reason_codes, conditions)

    @staticmethod
    def _provenance(rule: AcademicRule) -> tuple[Provenance, ...]:
        if rule.provenance is not None:
            return (rule.provenance,)
        return (
            Provenance(
                rule_id=rule.rule_id,
                approval_status=rule.approval_status,
                verification_status=rule.verification_status,
            ),
        )


def _boolean_outcome(actual: bool) -> EvaluationOutcome:
    return EvaluationOutcome.SATISFIED if actual else EvaluationOutcome.UNSATISFIED


def _node_id(rule_id: str, path: str) -> str:
    return rule_id if path == "root" else f"{rule_id}:{path}"


def _trace_status(
    outcome: EvaluationOutcome,
    *,
    conditional: bool = False,
) -> DecisionStatus:
    if conditional and outcome is EvaluationOutcome.INDETERMINATE:
        return DecisionStatus.CONDITIONAL
    return {
        EvaluationOutcome.SATISFIED: DecisionStatus.SATISFIED,
        EvaluationOutcome.UNSATISFIED: DecisionStatus.FAILED,
        EvaluationOutcome.INDETERMINATE: DecisionStatus.INDETERMINATE,
    }[outcome]


def _logical_conditions(
    children: tuple[_ExpressionEvaluation, ...],
    *,
    operator: str,
    outcome: EvaluationOutcome,
) -> tuple[FutureCondition, ...]:
    """Preserve projected conditions without turning unknown facts into plans."""

    if outcome is not EvaluationOutcome.INDETERMINATE:
        return ()
    conditions = tuple(
        condition for child in children for condition in child.conditions
    )
    if not conditions:
        return ()
    if len(conditions) == 1:
        return conditions
    group: FutureCondition = (
        AllConditions(conditions) if operator == "AND" else AnyConditions(conditions)
    )
    return (group,)


def _unique_reason_codes(
    reason_codes: tuple[ReasonCode, ...],
) -> tuple[ReasonCode, ...]:
    return tuple(dict.fromkeys(reason_codes))


def _trace_contains_unresolved_child(node: DecisionTraceNode) -> bool:
    """Find unresolved nested branches that affect a non-satisfied result."""

    unresolved_statuses = {
        DecisionStatus.INDETERMINATE,
        DecisionStatus.BLOCKED,
        DecisionStatus.CONFLICTED,
        DecisionStatus.NOT_EVALUATED,
        DecisionStatus.UNSUPPORTED,
    }
    return node.status in unresolved_statuses or any(
        _trace_contains_unresolved_child(child) for child in node.children
    )
