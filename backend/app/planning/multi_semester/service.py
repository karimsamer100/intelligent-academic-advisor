"""Deterministic forward orchestration over the single-semester planner."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..audit.service import DegreeAuditService
from ..domain.academic_state import AcademicStateLayer, HypotheticalAcademicOutcome
from ..domain.audit import DegreeAuditRequest, DegreeAuditResult, DegreeAuditStatus
from ..domain.candidates import CandidateGenerationStatus
from ..domain.context import RegistrationIntent
from ..domain.multi_semester import (
    MultiSemesterPlanResult,
    MultiSemesterPlanStatus,
    MultiSemesterPlanStep,
    MultiSemesterPlanningRequest,
    MultiSemesterStopReason,
    PlanningTerm,
    ProjectedStateSummary,
)
from ..domain.planning import (
    PlanDiagnostic,
    PlanDiagnosticCode,
    PlanStatus,
    PlanningCoverage,
    PlanningCoverageStatus,
    SingleSemesterPlanningRequest,
)
from ..domain.projection import ProjectionPolicy
from ..domain.requirements import RequirementSetStatus
from ..domain.reasons import ReasonCode
from ..domain.results import ResultMetadata
from ..domain.student import StudentState
from ..domain.student_history import AttemptOutcome, AttemptPurpose
from ..domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceMetadata,
    TraceNodeType,
)
from ..planner.service import SingleSemesterPlanner
from ..projection.service import HypotheticalStateTransitionService


@dataclass(frozen=True, slots=True)
class MultiSemesterPlanner:
    """Replan one bounded term at a time over ephemeral projected state."""

    single_semester_planner: SingleSemesterPlanner
    transition_service: HypotheticalStateTransitionService = (
        HypotheticalStateTransitionService()
    )
    degree_audit_service: DegreeAuditService | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.single_semester_planner, SingleSemesterPlanner):
            raise TypeError("single_semester_planner must be a SingleSemesterPlanner")
        if not isinstance(self.transition_service, HypotheticalStateTransitionService):
            raise TypeError(
                "transition_service must be a HypotheticalStateTransitionService"
            )
        if self.degree_audit_service is None:
            evaluator = self.single_semester_planner.semester_validator.eligibility_service.rule_evaluator
            object.__setattr__(
                self,
                "degree_audit_service",
                DegreeAuditService(evaluator.policy, evaluator.dataset_version),
            )
        elif not isinstance(self.degree_audit_service, DegreeAuditService):
            raise TypeError("degree_audit_service must be a DegreeAuditService or None")

    def plan(self, request: MultiSemesterPlanningRequest) -> MultiSemesterPlanResult:
        if not isinstance(request, MultiSemesterPlanningRequest):
            raise TypeError("request must be a MultiSemesterPlanningRequest")

        current = request.initial_student
        initial = current
        steps: list[MultiSemesterPlanStep] = []
        all_conditions = []
        diagnostics: list[PlanDiagnostic] = []
        coverage = _initial_coverage(request)
        final_audit = self._audit(current, request)
        stop_reason: MultiSemesterStopReason | None = None
        status: MultiSemesterPlanStatus | None = None

        if _audit_is_complete(final_audit, request):
            stop_reason = MultiSemesterStopReason.ACADEMIC_REQUIREMENTS_SATISFIED
            status = MultiSemesterPlanStatus.COMPLETION_PATH_FOUND

        for term in request.terms if status is None else ():
            before = ProjectedStateSummary.from_student(current)
            audit = self._audit(current, request)
            candidate_request = _candidate_request_for(
                request,
                current,
                audit,
                term,
            )
            single_request = SingleSemesterPlanningRequest(
                student=current,
                term_type=term.term_type,
                load_policy=request.load_policy,
                candidate_request=candidate_request,
                preferences=request.preferences,
                search_policy=request.single_search_policy,
                term_id=term.term_id,
                excluded_courses=request.excluded_courses,
            )
            plan = self.single_semester_planner.plan(single_request)
            coverage = _merge_coverage(coverage, plan.coverage)
            all_conditions.extend(plan.conditions)

            if not plan.selected_courses:
                stop_reason = _stop_for_empty_plan(plan)
                status = _status_for_stop(stop_reason, all_conditions)
                diagnostics.extend(plan.review_items)
                steps.append(
                    MultiSemesterPlanStep(
                        term=term,
                        input_state=before,
                        plan=plan,
                        applied_outcomes=(),
                        output_state=before,
                        audit=audit,
                        conditions=plan.conditions,
                        trace=plan.trace,
                    )
                )
                break

            if plan.status in {PlanStatus.REVIEW_REQUIRED, PlanStatus.UNSUPPORTED}:
                stop_reason = (
                    MultiSemesterStopReason.REVIEW_REQUIRED
                    if plan.status.name == "REVIEW_REQUIRED"
                    else MultiSemesterStopReason.UNSUPPORTED
                )
                status = _status_for_stop(stop_reason, all_conditions)
                diagnostics.extend(plan.review_items)
                steps.append(
                    MultiSemesterPlanStep(
                        term=term,
                        input_state=before,
                        plan=plan,
                        applied_outcomes=(),
                        output_state=before,
                        audit=audit,
                        conditions=plan.conditions,
                        trace=plan.trace,
                    )
                )
                break

            outcomes = _projection_outcomes(plan, term, request.projection_policy)
            transition = self.transition_service.apply(
                current,
                outcomes,
                policy=request.projection_policy,
            )
            projected = transition.student_state
            coverage = _with_projection_uncertainty(coverage)
            after = ProjectedStateSummary.from_student(projected)
            post_audit = self._audit(projected, request)
            final_audit = post_audit
            all_conditions.extend(plan.conditions)
            step_trace = _step_trace(term, plan, transition)
            steps.append(
                MultiSemesterPlanStep(
                    term=term,
                    input_state=before,
                    plan=plan,
                    applied_outcomes=outcomes,
                    output_state=after,
                    audit=post_audit,
                    conditions=plan.conditions,
                    trace=step_trace,
                )
            )

            if _same_progress(current, projected, request):
                stop_reason = MultiSemesterStopReason.NO_PROGRESS
                status = MultiSemesterPlanStatus.NO_PROGRESS
                diagnostics.append(
                    PlanDiagnostic(
                        PlanDiagnosticCode.NO_PROGRESS,
                        reason_codes=(ReasonCode.NO_PROGRESS,),
                    )
                )
                break

            current = projected
            if _audit_is_complete(post_audit, request):
                stop_reason = MultiSemesterStopReason.ACADEMIC_REQUIREMENTS_SATISFIED
                status = (
                    MultiSemesterPlanStatus.CONDITIONAL_PATH
                    if all_conditions
                    else MultiSemesterPlanStatus.COMPLETION_PATH_FOUND
                )
                break

        if status is None:
            stop_reason = MultiSemesterStopReason.HORIZON_REACHED
            status = (
                MultiSemesterPlanStatus.CONDITIONAL_PATH
                if all_conditions
                else MultiSemesterPlanStatus.PARTIAL_PATH
            )
            diagnostics.append(
                PlanDiagnostic(
                    PlanDiagnosticCode.HORIZON_REACHED,
                    reason_codes=(ReasonCode.HORIZON_REACHED,),
                )
            )

        if (
            final_audit is None
            and request.candidate_request.requirement_set is not None
        ):
            final_audit = self._audit(current, request)
        diagnostics.extend(
            item
            for step in steps
            for item in step.plan.review_items
            if item not in diagnostics
        )
        final_coverage = _merge_coverage(
            coverage, _audit_coverage(final_audit, uel=coverage.uel)
        )
        trace = _multi_trace(request, steps, final_coverage, status, stop_reason)
        metadata = _result_metadata(
            self,
            steps,
            final_coverage,
            status,
            trace,
            diagnostics,
        )
        return MultiSemesterPlanResult(
            status=status,
            initial_state=initial,
            final_state=current,
            steps=tuple(steps),
            final_audit=final_audit,
            stop_reason=stop_reason,
            projection_policy=request.projection_policy,
            conditions=_unique_conditions(tuple(all_conditions)),
            review_items=tuple(diagnostics),
            coverage=final_coverage,
            metadata=metadata,
            trace=trace,
            uel_evaluation=request.candidate_request.uel_evaluation,
        )

    def _audit(
        self,
        student: StudentState,
        request: MultiSemesterPlanningRequest,
    ) -> DegreeAuditResult | None:
        requirement_set = request.candidate_request.requirement_set
        if requirement_set is None:
            return None
        assert self.degree_audit_service is not None
        return self.degree_audit_service.audit(
            DegreeAuditRequest(
                student=student,
                requirement_set=requirement_set,
                pools=request.candidate_request.pools,
                concentrations=request.candidate_request.concentrations,
                program_facts=request.program_facts,
            )
        )


def _candidate_request_for(
    request: MultiSemesterPlanningRequest,
    student: StudentState,
    audit: DegreeAuditResult | None,
    term: PlanningTerm,
):
    context = replace(
        request.candidate_request.context,
        horizon=request.horizon,
        proposed_courses=(),
        term_id=term.term_id,
    )
    return replace(
        request.candidate_request,
        student=student,
        degree_audit=audit,
        context=context,
    )


def _projection_outcomes(plan, term: PlanningTerm, policy: ProjectionPolicy):
    if policy is not ProjectionPolicy.ASSUME_SELECTED_COURSES_PASSED:
        return ()
    outcomes = []
    for selected in plan.selected_courses:
        purpose = {
            RegistrationIntent.NORMAL: AttemptPurpose.INITIAL,
            RegistrationIntent.RETAKE_AFTER_FAILURE: AttemptPurpose.REPEAT,
            RegistrationIntent.RETAKE_FOR_IMPROVEMENT: AttemptPurpose.IMPROVEMENT,
        }[selected.registration_intent]
        outcomes.append(
            HypotheticalAcademicOutcome(
                course=selected.identity,
                outcome=AttemptOutcome.PASSED,
                purpose=purpose,
                sequence=term.index,
                earned_credit_hours=selected.candidate.course.credit_hours,
                intent=selected.registration_intent,
                layer=AcademicStateLayer.PROJECTED,
            )
        )
    return tuple(outcomes)


def _audit_is_complete(
    audit: DegreeAuditResult | None,
    request: MultiSemesterPlanningRequest,
) -> bool:
    return bool(
        audit is not None
        and request.candidate_request.requirement_set is not None
        and request.candidate_request.requirement_set.status
        is RequirementSetStatus.COMPLETE
        and audit.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED
    )


def _same_progress(
    before: StudentState,
    after: StudentState,
    request: MultiSemesterPlanningRequest,
) -> bool:
    if before.earned_credit_hours != after.earned_credit_hours:
        return False
    identities = tuple(item.identity for item in request.candidate_request.courses)
    return all(
        before.pass_status(item) is after.pass_status(item) for item in identities
    )


def _stop_for_empty_plan(plan):
    if plan.status.name == "REVIEW_REQUIRED":
        return MultiSemesterStopReason.REVIEW_REQUIRED
    if plan.status.name == "UNSUPPORTED":
        return MultiSemesterStopReason.UNSUPPORTED
    if any(item.code is PlanDiagnosticCode.NO_CANDIDATES for item in plan.diagnostics):
        return MultiSemesterStopReason.NO_CANDIDATES
    return MultiSemesterStopReason.NO_FEASIBLE_SEMESTER


def _status_for_stop(
    stop_reason: MultiSemesterStopReason,
    conditions,
) -> MultiSemesterPlanStatus:
    if stop_reason is MultiSemesterStopReason.REVIEW_REQUIRED:
        return MultiSemesterPlanStatus.REVIEW_REQUIRED
    if stop_reason is MultiSemesterStopReason.UNSUPPORTED:
        return MultiSemesterPlanStatus.UNSUPPORTED
    if stop_reason is MultiSemesterStopReason.NO_PROGRESS:
        return MultiSemesterPlanStatus.NO_PROGRESS
    if conditions:
        return MultiSemesterPlanStatus.CONDITIONAL_PATH
    return MultiSemesterPlanStatus.NO_FEASIBLE_PATH


def _initial_coverage(request: MultiSemesterPlanningRequest) -> PlanningCoverage:
    source = request.candidate_request.source_coverage

    def convert(value: CandidateGenerationStatus) -> PlanningCoverageStatus:
        return PlanningCoverageStatus(value.value)

    requirements = request.candidate_request.requirement_set
    requirement_status = (
        PlanningCoverageStatus(requirements.status.value)
        if requirements is not None
        else PlanningCoverageStatus.UNAVAILABLE
    )
    uel_status = convert(source.uel)
    if request.candidate_request.uel_evaluation is not None:
        uel_status = PlanningCoverageStatus(
            request.candidate_request.uel_evaluation.coverage.overall.value
        )
    return PlanningCoverage(
        academic_requirements=requirement_status,
        candidate_generation=convert(source.overall),
        eligibility_rules=convert(source.eligibility_rules),
        dependency=convert(source.dependency_graph),
        offering=PlanningCoverageStatus.UNAVAILABLE,
        timetable=PlanningCoverageStatus.UNAVAILABLE,
        search=PlanningCoverageStatus.COMPLETE,
        projection=PlanningCoverageStatus.COMPLETE,
        uel=uel_status,
    )


def _audit_coverage(
    audit: DegreeAuditResult | None,
    *,
    uel: PlanningCoverageStatus = PlanningCoverageStatus.UNAVAILABLE,
) -> PlanningCoverage:
    if audit is None:
        status = PlanningCoverageStatus.UNAVAILABLE
    else:
        status = PlanningCoverageStatus(audit.requirement_set_status.value)
    return PlanningCoverage(
        academic_requirements=status,
        candidate_generation=PlanningCoverageStatus.UNAVAILABLE,
        eligibility_rules=PlanningCoverageStatus.UNAVAILABLE,
        dependency=PlanningCoverageStatus.UNAVAILABLE,
        offering=PlanningCoverageStatus.UNAVAILABLE,
        timetable=PlanningCoverageStatus.UNAVAILABLE,
        search=PlanningCoverageStatus.UNAVAILABLE,
        projection=PlanningCoverageStatus.COMPLETE,
        uel=uel,
    )


def _merge_coverage(
    left: PlanningCoverage, right: PlanningCoverage
) -> PlanningCoverage:
    def merge(a: PlanningCoverageStatus, b: PlanningCoverageStatus):
        if (
            a is PlanningCoverageStatus.INCOMPLETE
            or b is PlanningCoverageStatus.INCOMPLETE
        ):
            return PlanningCoverageStatus.INCOMPLETE
        if (
            a is PlanningCoverageStatus.UNAVAILABLE
            and b is PlanningCoverageStatus.UNAVAILABLE
        ):
            return PlanningCoverageStatus.UNAVAILABLE
        if (
            a is PlanningCoverageStatus.UNAVAILABLE
            or b is PlanningCoverageStatus.UNAVAILABLE
        ):
            return PlanningCoverageStatus.INCOMPLETE
        return PlanningCoverageStatus.COMPLETE

    return PlanningCoverage(
        academic_requirements=merge(
            left.academic_requirements, right.academic_requirements
        ),
        candidate_generation=merge(
            left.candidate_generation, right.candidate_generation
        ),
        eligibility_rules=merge(left.eligibility_rules, right.eligibility_rules),
        dependency=merge(left.dependency, right.dependency),
        offering=merge(left.offering, right.offering),
        timetable=merge(left.timetable, right.timetable),
        search=merge(left.search, right.search),
        projection=merge(left.projection, right.projection),
        uel=merge(left.uel, right.uel),
    )


def _with_projection_uncertainty(
    coverage: PlanningCoverage,
) -> PlanningCoverage:
    return PlanningCoverage(
        academic_requirements=coverage.academic_requirements,
        candidate_generation=coverage.candidate_generation,
        eligibility_rules=coverage.eligibility_rules,
        dependency=coverage.dependency,
        offering=coverage.offering,
        timetable=coverage.timetable,
        search=coverage.search,
        projection=PlanningCoverageStatus.INCOMPLETE,
        uel=coverage.uel,
    )


def _unique_conditions(conditions):
    result = []
    seen = set()
    for condition in conditions:
        key = repr(condition.to_dict())
        if key not in seen:
            seen.add(key)
            result.append(condition)
    return tuple(result)


def _step_trace(term, plan, transition):
    return DecisionTrace(
        DecisionTraceNode(
            node_id=f"multi-semester-step:{term.index}",
            code=TraceCode.HYPOTHETICAL_TRANSITION,
            node_type=TraceNodeType.ROOT,
            status=DecisionStatus.CONDITIONAL
            if plan.conditions
            else DecisionStatus.SATISFIED,
            actual_value=tuple(
                item.course.course_id for item in transition.applied_outcomes
            ),
            children=(plan.trace.root,),
            metadata=(
                TraceMetadata("term_index", term.index),
                TraceMetadata("projection_policy", transition.policy.value),
                TraceMetadata("fact_layer", transition.layer.value),
            ),
        )
    )


def _multi_trace(request, steps, coverage, status, stop_reason):
    return DecisionTrace(
        DecisionTraceNode(
            node_id="multi-semester-planning",
            code=TraceCode.MULTI_SEMESTER_PLANNING,
            node_type=TraceNodeType.ROOT,
            status={
                MultiSemesterPlanStatus.COMPLETION_PATH_FOUND: DecisionStatus.SATISFIED,
                MultiSemesterPlanStatus.CONDITIONAL_PATH: DecisionStatus.CONDITIONAL,
                MultiSemesterPlanStatus.PARTIAL_PATH: DecisionStatus.INDETERMINATE,
                MultiSemesterPlanStatus.REVIEW_REQUIRED: DecisionStatus.ADVISOR_REVIEW,
                MultiSemesterPlanStatus.NO_PROGRESS: DecisionStatus.INDETERMINATE,
                MultiSemesterPlanStatus.NO_FEASIBLE_PATH: DecisionStatus.FAILED,
                MultiSemesterPlanStatus.UNSUPPORTED: DecisionStatus.UNSUPPORTED,
            }[status],
            expected_value=MultiSemesterPlanStatus.COMPLETION_PATH_FOUND.value,
            actual_value=status.value,
            children=tuple(item.trace.root for item in steps if item.trace is not None),
            metadata=(
                TraceMetadata("max_semesters", request.max_semesters),
                TraceMetadata("coverage", coverage.overall.value),
                TraceMetadata("stop_reason", stop_reason.value),
                TraceMetadata("projection_policy", request.projection_policy.value),
            ),
        )
    )


def _result_metadata(
    planner: MultiSemesterPlanner,
    steps,
    coverage,
    status,
    trace,
    diagnostics,
):
    evaluator = planner.single_semester_planner.semester_validator.eligibility_service.rule_evaluator
    source = steps[-1].plan.metadata if steps else None
    reasons = list(source.reason_codes if source is not None else ())
    reasons.extend(
        reason for diagnostic in diagnostics for reason in diagnostic.reason_codes
    )
    reasons.extend(
        reason
        for reason in (
            ReasonCode.OFFERING_UNAVAILABLE,
            ReasonCode.TIMETABLE_UNAVAILABLE,
        )
        if reason not in reasons
    )
    authoritative = bool(
        source is not None
        and source.authoritative
        and status is MultiSemesterPlanStatus.COMPLETION_PATH_FOUND
        and coverage.academic_overall is PlanningCoverageStatus.COMPLETE
    )
    return ResultMetadata(
        dataset_version=evaluator.dataset_version,
        execution_mode=evaluator.policy.mode,
        authoritative=authoritative,
        approval_status=source.approval_status if source is not None else None,
        verification_status=source.verification_status if source is not None else None,
        reason_codes=tuple(dict.fromkeys(reasons)),
        provenance=source.provenance if source is not None else (),
        decision_trace=trace,
        requires_human_review=status
        in {
            MultiSemesterPlanStatus.REVIEW_REQUIRED,
            MultiSemesterPlanStatus.UNSUPPORTED,
        }
        or any(
            item.code is PlanDiagnosticCode.INSUFFICIENT_DATA for item in diagnostics
        ),
    )


__all__ = ["MultiSemesterPlanner"]
