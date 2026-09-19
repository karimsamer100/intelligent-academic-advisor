"""Deterministic validation of an explicitly proposed semester."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.context import EligibilityContext
from ..domain.eligibility import (
    CourseEligibilityRuleSet,
    EligibilityDecision,
    EligibilityRequest,
    RuleSetStatus,
)
from ..domain.reasons import ReasonCode
from ..domain.results import ResultMetadata
from ..domain.semester import (
    ProposedCourse,
    SemesterCourseResult,
    SemesterIssueCode,
    SemesterLoadResult,
    SemesterValidationIssue,
    SemesterValidationRequest,
    SemesterValidationResult,
    SemesterValidationStatus,
)
from ..domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceMetadata,
    TraceNodeType,
)
from ..eligibility.service import EligibilityService
from ..policy import ExecutionMode


@dataclass(frozen=True, slots=True)
class SemesterValidator:
    """Pure orchestration over a supplied student, proposal, and rule data."""

    eligibility_service: EligibilityService

    def __post_init__(self) -> None:
        if not isinstance(self.eligibility_service, EligibilityService):
            raise TypeError("eligibility_service must be an EligibilityService")

    def validate(self, request: SemesterValidationRequest) -> SemesterValidationResult:
        if not isinstance(request, SemesterValidationRequest):
            raise TypeError("request must be a SemesterValidationRequest")

        rule_sets = {item.target_course: item for item in request.rule_sets}
        unique_entries = _unique_entries(request.semester.courses)
        proposed_ids = request.semester.unique_course_ids
        course_results: list[SemesterCourseResult] = []
        all_conditions = []
        reason_codes: list[ReasonCode] = []
        review_items: list[SemesterValidationIssue] = []
        violations: list[SemesterValidationIssue] = []

        for proposed_course in unique_entries:
            identity = proposed_course.identity
            rule_set = rule_sets.get(identity)
            if rule_set is None:
                rule_set = CourseEligibilityRuleSet(
                    target_course=identity,
                    status=RuleSetStatus.UNAVAILABLE,
                    reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                )
            context = EligibilityContext(
                intent=proposed_course.registration_intent,
                horizon=request.horizon,
                proposed_term=_proposed_context(
                    identity, proposed_ids, request.semester.term_id
                ),
            )
            eligibility = self.eligibility_service.check(
                EligibilityRequest(
                    student=request.student,
                    course=proposed_course.course,
                    rule_set=rule_set,
                    context=context,
                )
            )
            course_results.append(SemesterCourseResult(proposed_course, eligibility))
            all_conditions.extend(eligibility.conditions)
            reason_codes.extend(eligibility.reason_codes)
            if eligibility.decision is EligibilityDecision.INELIGIBLE:
                violations.append(
                    SemesterValidationIssue(
                        SemesterIssueCode.ELIGIBILITY_FAILED,
                        course=identity,
                        expected=True,
                        actual=False,
                        reason_codes=eligibility.reason_codes,
                    )
                )
            elif eligibility.decision is EligibilityDecision.UNSUPPORTED:
                review_items.append(
                    SemesterValidationIssue(
                        SemesterIssueCode.UNSUPPORTED_ELIGIBILITY,
                        course=identity,
                        reason_codes=eligibility.reason_codes,
                    )
                )
            elif eligibility.decision in {
                EligibilityDecision.REQUIRES_ADVISOR_REVIEW,
                EligibilityDecision.HUMAN_REVIEW_REQUIRED,
            }:
                review_items.append(
                    SemesterValidationIssue(
                        SemesterIssueCode.ELIGIBILITY_UNRESOLVED,
                        course=identity,
                        reason_codes=eligibility.reason_codes,
                    )
                )

        for identity in request.semester.duplicate_course_ids:
            issue = SemesterValidationIssue(
                SemesterIssueCode.DUPLICATE_COURSE,
                course=identity,
                expected=1,
                actual=sum(
                    item.identity == identity for item in request.semester.courses
                ),
                reason_codes=(ReasonCode.DUPLICATE_COURSE,),
            )
            violations.append(issue)
            reason_codes.append(ReasonCode.DUPLICATE_COURSE)

        load_result, load_issues, load_review, load_reasons = self._validate_load(
            request, unique_entries
        )
        violations.extend(load_issues)
        review_items.extend(load_review)
        reason_codes.extend(load_reasons)
        status = _aggregate_status(
            course_results, load_result, violations, review_items
        )
        conditions = _unique_conditions(all_conditions)
        trace = self._trace(
            request,
            status,
            course_results,
            load_result,
            violations,
            review_items,
        )
        policy = self.eligibility_service.rule_evaluator.policy
        load_decision = policy.assess(
            request.load_policy.approval_status,
            verification_status=request.load_policy.verification_status,
            critical=True,
        )
        authoritative = (
            policy.mode is ExecutionMode.AUTHORITATIVE
            and status
            in {SemesterValidationStatus.VALID, SemesterValidationStatus.INVALID}
            and not review_items
            and load_decision.authoritative
            and all(item.eligibility.authoritative for item in course_results)
        )
        metadata = ResultMetadata(
            dataset_version=policy_version(self),
            execution_mode=policy.mode,
            authoritative=authoritative,
            approval_status=load_decision.approval_status,
            verification_status=load_decision.verification_status,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            provenance=(
                (request.load_policy.provenance,)
                if request.load_policy.provenance is not None
                else ()
            ),
            decision_trace=trace,
            requires_human_review=bool(review_items),
        )
        return SemesterValidationResult(
            status=status,
            course_results=tuple(course_results),
            load_result=load_result,
            conditions=conditions,
            violations=tuple(violations),
            review_items=tuple(review_items),
            metadata=metadata,
            trace=trace,
        )

    def _validate_load(
        self,
        request: SemesterValidationRequest,
        entries: tuple[ProposedCourse, ...],
    ) -> tuple[
        SemesterLoadResult,
        tuple[SemesterValidationIssue, ...],
        tuple[SemesterValidationIssue, ...],
        tuple[ReasonCode, ...],
    ]:
        policy = self.eligibility_service.rule_evaluator.policy
        load_policy = request.load_policy
        policy_decision = policy.assess(
            load_policy.approval_status,
            verification_status=load_policy.verification_status,
            critical=True,
        )
        scope_reasons = []
        if load_policy.regulation is not request.student.regulation:
            scope_reasons.append(ReasonCode.WRONG_REGULATION)
        if load_policy.program != request.student.program:
            scope_reasons.append(ReasonCode.WRONG_PROGRAM)
        scope_matches = not scope_reasons
        total: int | float | None
        if all(
            item.credit_hours_known and item.credit_hours is not None
            for item in entries
        ):
            total = sum(
                item.credit_hours for item in entries if item.credit_hours is not None
            )
        else:
            total = None
        band = load_policy.band_for(request.semester.term_type, request.student.gpa)
        reasons = list(policy_decision.reason_codes)
        violations: list[SemesterValidationIssue] = []
        review: list[SemesterValidationIssue] = []
        if not scope_matches:
            status = SemesterValidationStatus.HUMAN_REVIEW_REQUIRED
            reasons.extend((*scope_reasons, ReasonCode.LOAD_POLICY_UNRESOLVED))
            review.append(
                SemesterValidationIssue(
                    SemesterIssueCode.LOAD_POLICY_UNRESOLVED,
                    expected=(
                        request.student.regulation.value,
                        str(request.student.program),
                    ),
                    actual=(load_policy.regulation.value, str(load_policy.program)),
                    reason_codes=tuple(
                        (*scope_reasons, ReasonCode.LOAD_POLICY_UNRESOLVED)
                    ),
                )
            )
        elif not policy_decision.allowed:
            status = SemesterValidationStatus.HUMAN_REVIEW_REQUIRED
            reasons.append(ReasonCode.LOAD_POLICY_UNRESOLVED)
            review.append(
                SemesterValidationIssue(
                    SemesterIssueCode.LOAD_POLICY_UNRESOLVED,
                    reason_codes=policy_decision.reason_codes,
                )
            )
        elif request.student.gpa is None or band is None:
            status = SemesterValidationStatus.HUMAN_REVIEW_REQUIRED
            reasons.extend(
                (ReasonCode.MISSING_REQUIRED_DATA, ReasonCode.LOAD_POLICY_UNRESOLVED)
            )
            review.append(
                SemesterValidationIssue(
                    SemesterIssueCode.LOAD_POLICY_UNRESOLVED,
                    expected="GPA_BAND",
                    actual=None,
                    reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                )
            )
        elif total is None:
            status = SemesterValidationStatus.HUMAN_REVIEW_REQUIRED
            reasons.extend(
                (ReasonCode.MISSING_REQUIRED_DATA, ReasonCode.UNKNOWN_COURSE_CREDITS)
            )
            review.append(
                SemesterValidationIssue(
                    SemesterIssueCode.UNKNOWN_COURSE_CREDITS,
                    reason_codes=(ReasonCode.UNKNOWN_COURSE_CREDITS,),
                )
            )
        elif band.allows(total, len(entries)):
            status = SemesterValidationStatus.VALID
        else:
            status = SemesterValidationStatus.INVALID
            reasons.append(ReasonCode.LOAD_LIMIT_EXCEEDED)
            violations.append(
                SemesterValidationIssue(
                    SemesterIssueCode.LOAD_LIMIT_EXCEEDED,
                    expected=(band.max_credit_hours, band.max_course_count),
                    actual=(total, len(entries)),
                    reason_codes=(ReasonCode.LOAD_LIMIT_EXCEEDED,),
                )
            )
        trace = DecisionTrace(
            DecisionTraceNode(
                node_id="semester-load",
                code=TraceCode.LOAD_POLICY,
                node_type=TraceNodeType.VALUE_CHECK,
                status=_trace_status(status),
                subject=load_policy.policy_id,
                expected_value=(band.max_credit_hours if band else None),
                actual_value=total,
                reason_codes=tuple(dict.fromkeys(reasons)),
                metadata=(
                    TraceMetadata("course_count", len(entries)),
                    TraceMetadata(
                        "max_course_count", band.max_course_count if band else None
                    ),
                    TraceMetadata("term_type", request.semester.term_type.value),
                ),
            )
        )
        return (
            SemesterLoadResult(
                status=status,
                term_type=request.semester.term_type,
                gpa=request.student.gpa,
                band_id=band.band_id if band else None,
                total_credit_hours=total,
                course_count=len(entries),
                max_credit_hours=band.max_credit_hours if band else None,
                max_course_count=band.max_course_count if band else None,
                reason_codes=tuple(dict.fromkeys(reasons)),
                trace=trace,
            ),
            tuple(violations),
            tuple(review),
            tuple(dict.fromkeys(reasons)),
        )

    def _trace(
        self,
        request: SemesterValidationRequest,
        status: SemesterValidationStatus,
        course_results: list[SemesterCourseResult],
        load_result: SemesterLoadResult,
        violations: list[SemesterValidationIssue],
        review_items: list[SemesterValidationIssue],
    ) -> DecisionTrace:
        children = [
            item.eligibility.metadata.decision_trace.root
            for item in sorted(
                course_results, key=lambda item: item.proposed_course.identity.course_id
            )
        ]
        children.append(load_result.trace.root)
        root = DecisionTraceNode(
            node_id="semester-validation",
            code=TraceCode.SEMESTER_VALIDATION,
            node_type=TraceNodeType.ROOT,
            status=_trace_status(status),
            subject=request.semester.term_id or request.semester.term_type.value,
            expected_value=True,
            actual_value=status is SemesterValidationStatus.VALID,
            reason_codes=tuple(
                dict.fromkeys(
                    reason
                    for issue in (*violations, *review_items)
                    for reason in issue.reason_codes
                )
            ),
            children=tuple(children),
            metadata=(
                TraceMetadata("term_type", request.semester.term_type.value),
                TraceMetadata("horizon", request.horizon.value),
            ),
        )
        return DecisionTrace(root)


def _unique_entries(entries: tuple[ProposedCourse, ...]) -> tuple[ProposedCourse, ...]:
    by_identity: dict[object, ProposedCourse] = {}
    for entry in entries:
        by_identity.setdefault(entry.identity, entry)
    return tuple(sorted(by_identity.values(), key=lambda item: item.identity.course_id))


def _proposed_context(identity, proposed_ids, term_id):
    from ..domain.context import ProposedTermContext

    return ProposedTermContext(
        target_course=identity,
        proposed_courses=proposed_ids,
        term_id=term_id,
    )


def _aggregate_status(course_results, load_result, violations, review_items):
    if violations:
        return SemesterValidationStatus.INVALID
    if any(
        item.eligibility.decision is EligibilityDecision.UNSUPPORTED
        for item in course_results
    ):
        return SemesterValidationStatus.UNSUPPORTED
    if (
        review_items
        or load_result.status is SemesterValidationStatus.HUMAN_REVIEW_REQUIRED
    ):
        return SemesterValidationStatus.HUMAN_REVIEW_REQUIRED
    if any(
        item.eligibility.decision is not EligibilityDecision.ELIGIBLE
        for item in course_results
    ):
        return SemesterValidationStatus.CONDITIONAL
    return SemesterValidationStatus.VALID


def _trace_status(status: SemesterValidationStatus) -> DecisionStatus:
    return {
        SemesterValidationStatus.VALID: DecisionStatus.SATISFIED,
        SemesterValidationStatus.INVALID: DecisionStatus.FAILED,
        SemesterValidationStatus.CONDITIONAL: DecisionStatus.CONDITIONAL,
        SemesterValidationStatus.HUMAN_REVIEW_REQUIRED: DecisionStatus.INDETERMINATE,
        SemesterValidationStatus.UNSUPPORTED: DecisionStatus.UNSUPPORTED,
    }[status]


def _unique_conditions(conditions):
    result = []
    seen = set()
    for condition in conditions:
        key = repr(condition.to_dict())
        if key not in seen:
            seen.add(key)
            result.append(condition)
    return tuple(result)


def policy_version(service: SemesterValidator):
    return service.eligibility_service.rule_evaluator.dataset_version


__all__ = ["SemesterValidator"]
