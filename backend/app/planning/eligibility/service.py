"""Deterministic orchestration for target-course eligibility decisions."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.academic_state import AcademicHistoryCoverage, FactStatus
from ..domain.conditions import FutureCondition
from ..domain.context import (
    EligibilityContext,
    RegistrationIntent,
)
from ..domain.course import Course, CourseIdentity
from ..domain.eligibility import (
    CourseEligibilityRuleSet,
    EligibilityRequest,
    EligibilityResult,
    EligibilityStatus,
    RuleSetStatus,
)
from ..domain.evaluation import EvaluationOutcome, RuleEvaluationResult
from ..domain.lifecycle import ApprovalStatus
from ..domain.provenance import Provenance
from ..domain.reasons import ReasonCode
from ..domain.results import ResultMetadata
from ..domain.rules import AcademicRule
from ..domain.student import StudentState
from ..domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceMetadata,
    TraceNodeType,
)
from ..policy import ExecutionMode, PolicyDecision
from ..rules.evaluator import RuleEvaluator


_UNSAFE_APPROVAL_STATES = {
    ApprovalStatus.BLOCKED,
    ApprovalStatus.CONFLICTED,
    ApprovalStatus.SUPERSEDED,
}
_APPROVAL_REVIEW_REASONS = {
    ReasonCode.UNAPPROVED_RULE,
    ReasonCode.UNVERIFIED_RULE,
}


@dataclass(frozen=True, slots=True)
class EligibilityService:
    """Pure eligibility orchestration over already-loaded domain objects."""

    rule_evaluator: RuleEvaluator

    def __post_init__(self) -> None:
        if not isinstance(self.rule_evaluator, RuleEvaluator):
            raise TypeError("rule_evaluator must be a RuleEvaluator")

    def check(self, request: EligibilityRequest) -> EligibilityResult:
        """Return a deterministic structured eligibility result."""

        if not isinstance(request, EligibilityRequest):
            raise TypeError("request must be an EligibilityRequest")

        student = request.student
        course = request.course
        rule_set = request.rule_set
        if rule_set.target_course != course.identity:
            raise ValueError("rule_set.target_course must match course.identity")

        scope_reasons = _scope_reason_codes(student, course)
        scope_node = _scope_trace(course, student, scope_reasons)
        if scope_reasons:
            return self._result(
                request,
                status=EligibilityStatus.NOT_ELIGIBLE,
                eligible=False,
                children=(scope_node,),
                reason_codes=scope_reasons,
                requires_human_review=False,
                target_decision=None,
                rule_results=(),
            )

        target_decision = self.rule_evaluator.policy.assess(
            course.approval_status,
            verification_status=course.verification_status,
            critical=True,
        )
        lifecycle_node = _course_lifecycle_trace(course, target_decision)
        base_children = [scope_node, lifecycle_node]

        if not target_decision.allowed:
            status = _blocked_course_status(target_decision)
            return self._result(
                request,
                status=status,
                eligible=None,
                children=tuple(base_children),
                reason_codes=target_decision.reason_codes,
                requires_human_review=True,
                target_decision=target_decision,
                rule_results=(),
            )

        if (
            request.context.proposed_term is not None
            and request.context.proposed_term.target_course != course.identity
        ):
            context_node = _proposed_context_trace(course, request.context)
            return self._result(
                request,
                status=EligibilityStatus.HUMAN_REVIEW_REQUIRED,
                eligible=None,
                children=tuple((*base_children, context_node)),
                reason_codes=(
                    *target_decision.reason_codes,
                    ReasonCode.CONCURRENT_CONTEXT_INVALID,
                ),
                requires_human_review=True,
                target_decision=target_decision,
                rule_results=(),
            )

        pass_status = _eligibility_pass_status(student, course.identity)
        registration_status = _eligibility_registration_status(student, course.identity)
        completion_unknown = pass_status is FactStatus.UNKNOWN
        completed = pass_status is FactStatus.KNOWN_TRUE
        currently_registered = registration_status is FactStatus.KNOWN_TRUE
        not_completed_node = _not_completed_trace(
            course,
            completed=None if completion_unknown else completed,
        )
        not_registered_node = _not_registered_trace(
            course,
            currently_registered=currently_registered,
        )
        base_children.extend((not_completed_node, not_registered_node))

        if completion_unknown:
            return self._result(
                request,
                status=EligibilityStatus.HUMAN_REVIEW_REQUIRED,
                eligible=None,
                children=tuple(base_children),
                reason_codes=(
                    *target_decision.reason_codes,
                    ReasonCode.MISSING_REQUIRED_DATA,
                ),
                requires_human_review=True,
                target_decision=target_decision,
                rule_results=(),
            )

        intent_result = _intent_gate(
            student,
            course.identity,
            request.context.intent,
            pass_status=pass_status,
        )
        if intent_result is not None:
            intent_status, intent_eligible, intent_reasons, intent_review = (
                intent_result
            )
            return self._result(
                request,
                status=intent_status,
                eligible=intent_eligible,
                children=tuple(base_children),
                reason_codes=(
                    *target_decision.reason_codes,
                    *intent_reasons,
                ),
                requires_human_review=intent_review,
                target_decision=target_decision,
                rule_results=(),
            )

        if completed:
            reasons = [*target_decision.reason_codes, ReasonCode.ALREADY_COMPLETED]
            if currently_registered:
                reasons.append(ReasonCode.CURRENTLY_REGISTERED)
            return self._result(
                request,
                status=EligibilityStatus.ALREADY_COMPLETED,
                eligible=False,
                children=tuple(base_children),
                reason_codes=tuple(reasons),
                requires_human_review=False,
                target_decision=target_decision,
                rule_results=(),
            )

        if currently_registered:
            return self._result(
                request,
                status=EligibilityStatus.CURRENTLY_REGISTERED,
                eligible=False,
                children=tuple(base_children),
                reason_codes=(
                    *target_decision.reason_codes,
                    ReasonCode.CURRENTLY_REGISTERED,
                ),
                requires_human_review=False,
                target_decision=target_decision,
                rule_results=(),
            )

        availability_node = _rule_set_availability_trace(rule_set)
        children = [*base_children, availability_node]
        rule_results: list[RuleEvaluationResult] = []
        rule_scope_reasons: list[ReasonCode] = []

        for rule in rule_set.rules:
            reasons = _rule_scope_reason_codes(student, course, rule)
            if reasons:
                rule_scope_reasons.extend(reasons)
                children.append(_rule_scope_trace(rule, reasons))
                continue
            evaluation = self.rule_evaluator.evaluate_with_context(
                rule,
                student,
                request.context,
            )
            rule_results.append(evaluation)
            children.append(evaluation.decision_trace.root)

        reason_codes = _unique_reason_codes(
            (
                *target_decision.reason_codes,
                *rule_set.reason_codes,
                *_rule_set_default_reasons(rule_set.status),
                *rule_scope_reasons,
                *(reason for result in rule_results for reason in result.reason_codes),
            )
        )
        warnings = _unique_reason_codes(
            tuple(warning for result in rule_results for warning in result.warnings)
        )

        has_unsatisfied = any(
            result.outcome is EvaluationOutcome.UNSATISFIED for result in rule_results
        )
        has_unsupported = ReasonCode.UNSUPPORTED_RULE in rule_set.reason_codes or any(
            ReasonCode.UNSUPPORTED_RULE in result.reason_codes
            for result in rule_results
        )
        has_rule_scope_issue = bool(rule_scope_reasons)
        has_review_issue = (
            rule_set.status is not RuleSetStatus.COMPLETE
            or has_rule_scope_issue
            or any(result.requires_human_review for result in rule_results)
        )
        blocked_by_unverified = _has_authoritative_approval_block(
            self.rule_evaluator,
            rule_results,
        )

        conditions = tuple(
            condition for result in rule_results for condition in result.conditions
        )
        has_conditional_results = bool(conditions) and all(
            result.conditions or result.outcome is EvaluationOutcome.SATISFIED
            for result in rule_results
        )

        if has_unsatisfied:
            status = EligibilityStatus.NOT_ELIGIBLE
            eligible = False
        elif has_unsupported:
            status = EligibilityStatus.UNSUPPORTED
            eligible = None
            has_review_issue = True
        elif blocked_by_unverified:
            status = EligibilityStatus.BLOCKED_BY_UNVERIFIED_RULE
            eligible = None
            has_review_issue = True
        elif has_conditional_results and not has_review_issue:
            status = EligibilityStatus.CONDITIONAL
            eligible = None
        elif request.context.intent is RegistrationIntent.RETAKE_FOR_IMPROVEMENT:
            status = EligibilityStatus.REQUIRES_ADVISOR_REVIEW
            eligible = None
            has_review_issue = True
        elif has_review_issue:
            status = EligibilityStatus.HUMAN_REVIEW_REQUIRED
            eligible = None
        else:
            status = EligibilityStatus.ELIGIBLE
            eligible = True

        return self._result(
            request,
            status=status,
            eligible=eligible,
            children=tuple(children),
            reason_codes=reason_codes,
            warnings=warnings,
            requires_human_review=has_review_issue,
            target_decision=target_decision,
            rule_results=tuple(rule_results),
            conditions=conditions,
        )

    def _result(
        self,
        request: EligibilityRequest,
        *,
        status: EligibilityStatus,
        eligible: bool | None,
        children: tuple[DecisionTraceNode, ...],
        reason_codes: tuple[ReasonCode, ...],
        requires_human_review: bool,
        target_decision: PolicyDecision | None,
        rule_results: tuple[RuleEvaluationResult, ...],
        warnings: tuple[ReasonCode, ...] = (),
        conditions: tuple[FutureCondition, ...] = (),
    ) -> EligibilityResult:
        rule_set = request.rule_set
        provenance = _unique_provenance(
            tuple(
                provenance
                for result in rule_results
                for provenance in result.provenance
            )
        )
        root = DecisionTraceNode(
            node_id=f"eligibility:{request.course.identity.course_id}",
            code=TraceCode.ELIGIBILITY,
            node_type=TraceNodeType.ROOT,
            status=_eligibility_trace_status(status),
            subject=request.course.identity,
            expected_value=True,
            actual_value=eligible,
            reason_codes=_unique_reason_codes(reason_codes),
            children=children,
            provenance=provenance,
            metadata=(
                TraceMetadata("eligibility_status", status.value),
                TraceMetadata("rule_set_status", rule_set.status.value),
                TraceMetadata("intent", request.context.intent.value),
                TraceMetadata("horizon", request.context.horizon.value),
            ),
        )
        trace = DecisionTrace(root)
        metadata = ResultMetadata(
            dataset_version=self.rule_evaluator.dataset_version,
            execution_mode=self.rule_evaluator.policy.mode,
            authoritative=_aggregate_authoritative(
                status,
                requires_human_review,
                target_decision,
                rule_set,
                rule_results,
            ),
            approval_status=(
                target_decision.approval_status
                if target_decision is not None
                else request.course.approval_status
            ),
            verification_status=(
                target_decision.verification_status
                if target_decision is not None
                else request.course.verification_status
            ),
            engine_version=self.rule_evaluator.engine_version,
            ruleset_version=self.rule_evaluator.ruleset_version,
            warnings=warnings,
            reason_codes=_unique_reason_codes(reason_codes),
            provenance=provenance,
            decision_trace=trace,
            requires_human_review=requires_human_review,
        )
        return EligibilityResult(
            target_course=request.course.identity,
            status=status,
            eligible=eligible,
            rule_set_status=rule_set.status,
            metadata=metadata,
            rule_results=rule_results,
            conditions=conditions,
            intent=request.context.intent,
            horizon=request.context.horizon,
        )


def _scope_reason_codes(
    student: StudentState, course: Course
) -> tuple[ReasonCode, ...]:
    reasons: list[ReasonCode] = []
    if course.identity.regulation is not student.regulation:
        reasons.append(ReasonCode.WRONG_REGULATION)
    if course.identity.program != student.program:
        reasons.append(ReasonCode.WRONG_PROGRAM)
    return _unique_reason_codes(tuple(reasons))


def _eligibility_pass_status(
    student: StudentState,
    course: CourseIdentity,
) -> FactStatus:
    """Use v2 facts first, retaining one explicit legacy construction boundary."""

    identity = course
    if student.course_records or student.history_coverage is not None:
        return student.pass_status(identity)
    if identity in student.unknown_completion_status_courses:
        return FactStatus.UNKNOWN
    if identity in student.completed_courses:
        return FactStatus.KNOWN_TRUE
    return student.pass_status(identity)


def _eligibility_registration_status(
    student: StudentState,
    course: CourseIdentity,
) -> FactStatus:
    identity = course
    return student.registration_status(identity)


def _intent_gate(
    student: StudentState,
    course: CourseIdentity,
    intent: RegistrationIntent,
    *,
    pass_status: FactStatus,
) -> tuple[EligibilityStatus, bool | None, tuple[ReasonCode, ...], bool] | None:
    """Validate only intent/history compatibility, not registration policy."""

    identity = course
    if intent is RegistrationIntent.NORMAL:
        return None

    if intent is RegistrationIntent.RETAKE_FOR_IMPROVEMENT:
        if pass_status is FactStatus.KNOWN_TRUE:
            return (
                EligibilityStatus.REQUIRES_ADVISOR_REVIEW,
                None,
                (
                    ReasonCode.ADVISOR_REVIEW_REQUIRED,
                    ReasonCode.EXCEPTION_REQUIRED,
                ),
                True,
            )
        if _coverage_is_complete_or_legacy(student):
            return (
                EligibilityStatus.NOT_ELIGIBLE,
                False,
                (ReasonCode.INTENT_MISMATCH,),
                False,
            )
        return (
            EligibilityStatus.HUMAN_REVIEW_REQUIRED,
            None,
            (ReasonCode.MISSING_REQUIRED_DATA,),
            True,
        )

    failed_status = _failed_attempt_status(student, identity)  # type: ignore[arg-type]
    if pass_status is FactStatus.KNOWN_TRUE:
        return (
            EligibilityStatus.NOT_ELIGIBLE,
            False,
            (ReasonCode.INTENT_MISMATCH,),
            False,
        )
    if failed_status is FactStatus.KNOWN_TRUE:
        return None
    if failed_status is FactStatus.KNOWN_FALSE and _coverage_is_complete_or_legacy(
        student
    ):
        return (
            EligibilityStatus.NOT_ELIGIBLE,
            False,
            (ReasonCode.INTENT_MISMATCH,),
            False,
        )
    return (
        EligibilityStatus.HUMAN_REVIEW_REQUIRED,
        None,
        (ReasonCode.MISSING_REQUIRED_DATA,),
        True,
    )


def _failed_attempt_status(student: StudentState, course: CourseIdentity) -> FactStatus:
    identity = course
    record = student.course_record(identity)
    if record is not None:
        return (
            FactStatus.KNOWN_TRUE
            if record.has_failed_attempt
            else FactStatus.KNOWN_FALSE
        )
    if student.has_failed_attempt(identity):
        return FactStatus.KNOWN_TRUE
    if student.history_coverage is AcademicHistoryCoverage.COMPLETE:
        return FactStatus.KNOWN_FALSE
    if student.history_coverage is not None:
        return FactStatus.UNKNOWN
    return FactStatus.KNOWN_FALSE


def _coverage_is_complete_or_legacy(student: StudentState) -> bool:
    return student.history_coverage in (None, AcademicHistoryCoverage.COMPLETE)


def _rule_scope_reason_codes(
    student: StudentState,
    course: Course,
    rule: AcademicRule,
) -> tuple[ReasonCode, ...]:
    reasons: list[ReasonCode] = []
    if (
        rule.regulation is not student.regulation
        or rule.regulation is not course.identity.regulation
    ):
        reasons.append(ReasonCode.WRONG_REGULATION)
    if rule.program != student.program or rule.program != course.identity.program:
        reasons.append(ReasonCode.WRONG_PROGRAM)
    return _unique_reason_codes(tuple(reasons))


def _scope_trace(
    course: Course,
    student: StudentState,
    reason_codes: tuple[ReasonCode, ...],
) -> DecisionTraceNode:
    expected = (course.identity.regulation.value, str(course.identity.program))
    actual = (student.regulation.value, str(student.program))
    return DecisionTraceNode(
        node_id="scope-check",
        code=TraceCode.SCOPE_CHECK,
        node_type=TraceNodeType.REQUIREMENT_CHECK,
        status=(DecisionStatus.FAILED if reason_codes else DecisionStatus.SATISFIED),
        subject=course.identity,
        expected_value=expected,
        actual_value=actual,
        reason_codes=reason_codes,
    )


def _course_lifecycle_trace(
    course: Course,
    decision: PolicyDecision,
) -> DecisionTraceNode:
    if decision.allowed:
        status = DecisionStatus.SATISFIED
    elif decision.approval_status is ApprovalStatus.BLOCKED:
        status = DecisionStatus.BLOCKED
    elif decision.approval_status is ApprovalStatus.CONFLICTED:
        status = DecisionStatus.CONFLICTED
    else:
        status = DecisionStatus.INDETERMINATE
    return DecisionTraceNode(
        node_id="course-lifecycle",
        code=TraceCode.COURSE_LIFECYCLE,
        node_type=TraceNodeType.REQUIREMENT_CHECK,
        status=status,
        subject=course.identity,
        expected_value=True,
        actual_value=decision.allowed,
        reason_codes=decision.reason_codes,
        metadata=(
            TraceMetadata("approval_status", decision.approval_status.value),
            TraceMetadata(
                "verification_status",
                decision.verification_status.value
                if decision.verification_status is not None
                else None,
            ),
        ),
    )


def _not_completed_trace(
    course: Course,
    *,
    completed: bool | None,
) -> DecisionTraceNode:
    if completed is None:
        status = DecisionStatus.INDETERMINATE
        reasons = (ReasonCode.MISSING_REQUIRED_DATA,)
    else:
        status = DecisionStatus.FAILED if completed else DecisionStatus.SATISFIED
        reasons = (ReasonCode.ALREADY_COMPLETED,) if completed else ()
    return DecisionTraceNode(
        node_id="not-already-completed",
        code=TraceCode.NOT_ALREADY_COMPLETED,
        node_type=TraceNodeType.COURSE_CHECK,
        status=status,
        subject=course.identity,
        expected_value=False,
        actual_value=completed,
        reason_codes=reasons,
    )


def _not_registered_trace(
    course: Course,
    *,
    currently_registered: bool,
) -> DecisionTraceNode:
    return DecisionTraceNode(
        node_id="not-currently-registered",
        code=TraceCode.NOT_CURRENTLY_REGISTERED,
        node_type=TraceNodeType.COURSE_CHECK,
        status=(
            DecisionStatus.FAILED if currently_registered else DecisionStatus.SATISFIED
        ),
        subject=course.identity,
        expected_value=False,
        actual_value=currently_registered,
        reason_codes=(
            (ReasonCode.CURRENTLY_REGISTERED,) if currently_registered else ()
        ),
    )


def _proposed_context_trace(
    course: Course,
    context: EligibilityContext,
) -> DecisionTraceNode:
    proposed_target = (
        context.proposed_term.target_course
        if context.proposed_term is not None
        else None
    )
    return DecisionTraceNode(
        node_id="proposed-term-context",
        code=TraceCode.PROPOSED_TERM_CONTEXT,
        node_type=TraceNodeType.REQUIREMENT_CHECK,
        status=DecisionStatus.INDETERMINATE,
        subject=course.identity,
        expected_value=course.identity.course_id,
        actual_value=(
            proposed_target.course_id if proposed_target is not None else None
        ),
        reason_codes=(ReasonCode.CONCURRENT_CONTEXT_INVALID,),
    )


def _rule_set_availability_trace(
    rule_set: CourseEligibilityRuleSet,
) -> DecisionTraceNode:
    if rule_set.status is RuleSetStatus.COMPLETE:
        status = DecisionStatus.SATISFIED
        reasons: tuple[ReasonCode, ...] = ()
    elif ReasonCode.UNSUPPORTED_RULE in rule_set.reason_codes:
        status = DecisionStatus.UNSUPPORTED
        reasons = rule_set.reason_codes
    else:
        status = DecisionStatus.INDETERMINATE
        reasons = _unique_reason_codes(
            (*rule_set.reason_codes, ReasonCode.MISSING_REQUIRED_DATA)
        )
    return DecisionTraceNode(
        node_id="rule-set-availability",
        code=TraceCode.RULE_SET_AVAILABILITY,
        node_type=TraceNodeType.REQUIREMENT_CHECK,
        status=status,
        subject=rule_set.target_course,
        expected_value=RuleSetStatus.COMPLETE.value,
        actual_value=rule_set.status.value,
        reason_codes=reasons,
    )


def _rule_scope_trace(
    rule: AcademicRule,
    reason_codes: tuple[ReasonCode, ...],
) -> DecisionTraceNode:
    return DecisionTraceNode(
        node_id=f"rule-scope:{rule.rule_id}",
        code=TraceCode.RULE,
        node_type=TraceNodeType.RULE_CHECK,
        status=DecisionStatus.INDETERMINATE,
        subject=rule.rule_id,
        reason_codes=reason_codes,
        provenance=(rule.provenance,) if rule.provenance is not None else (),
        metadata=(TraceMetadata("rule_id", rule.rule_id),),
    )


def _blocked_course_status(decision: PolicyDecision) -> EligibilityStatus:
    if decision.approval_status in _UNSAFE_APPROVAL_STATES:
        return EligibilityStatus.HUMAN_REVIEW_REQUIRED
    return EligibilityStatus.BLOCKED_BY_UNVERIFIED_RULE


def _has_authoritative_approval_block(
    evaluator: RuleEvaluator,
    results: list[RuleEvaluationResult],
) -> bool:
    if evaluator.policy.mode is not ExecutionMode.AUTHORITATIVE:
        return False
    return any(
        result.requires_human_review
        and result.approval_status not in _UNSAFE_APPROVAL_STATES
        and any(reason in _APPROVAL_REVIEW_REASONS for reason in result.reason_codes)
        for result in results
    )


def _rule_set_default_reasons(status: RuleSetStatus) -> tuple[ReasonCode, ...]:
    if status is RuleSetStatus.COMPLETE:
        return ()
    return (ReasonCode.MISSING_REQUIRED_DATA,)


def _aggregate_authoritative(
    status: EligibilityStatus,
    requires_human_review: bool,
    target_decision: PolicyDecision | None,
    rule_set: CourseEligibilityRuleSet,
    rule_results: tuple[RuleEvaluationResult, ...],
) -> bool:
    if target_decision is None or not target_decision.authoritative:
        return False
    if status in {
        EligibilityStatus.BLOCKED_BY_UNVERIFIED_RULE,
        EligibilityStatus.HUMAN_REVIEW_REQUIRED,
        EligibilityStatus.UNSUPPORTED,
    }:
        return False
    if requires_human_review or rule_set.status is not RuleSetStatus.COMPLETE:
        return False
    return all(result.authoritative for result in rule_results)


def _eligibility_trace_status(status: EligibilityStatus) -> DecisionStatus:
    if status in {
        EligibilityStatus.ELIGIBLE,
    }:
        return DecisionStatus.SATISFIED
    if status in {
        EligibilityStatus.NOT_ELIGIBLE,
        EligibilityStatus.ALREADY_COMPLETED,
        EligibilityStatus.CURRENTLY_REGISTERED,
    }:
        return DecisionStatus.FAILED
    if status is EligibilityStatus.CONDITIONAL:
        return DecisionStatus.CONDITIONAL
    if status is EligibilityStatus.REQUIRES_ADVISOR_REVIEW:
        return DecisionStatus.ADVISOR_REVIEW
    if status is EligibilityStatus.UNSUPPORTED:
        return DecisionStatus.UNSUPPORTED
    return DecisionStatus.INDETERMINATE


def _unique_reason_codes(
    reason_codes: tuple[ReasonCode, ...],
) -> tuple[ReasonCode, ...]:
    return tuple(dict.fromkeys(reason_codes))


def _unique_provenance(provenance: tuple[Provenance, ...]) -> tuple[Provenance, ...]:
    return tuple(dict.fromkeys(provenance))
