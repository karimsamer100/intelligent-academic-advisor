"""Evaluate typed what-if scenarios without mutating observed state."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..domain.multi_semester import (
    MultiSemesterPlanResult,
    MultiSemesterPlanningRequest,
)
from ..domain.planning import PlanDiagnostic
from ..domain.reasons import ReasonCode
from ..domain.results import ResultMetadata
from ..domain.scenario import (
    CourseOutcomeScenario,
    ExcludeCourseScenario,
    PlanningHorizonScenario,
    PlanningPreferenceScenario,
    ScenarioOperation,
    WhatIfDelta,
    WhatIfPlanningRequest,
    WhatIfResult,
)
from ..domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceMetadata,
    TraceNodeType,
)
from ..domain.student import StudentState
from ..projection.service import HypotheticalStateTransitionService
from ..multi_semester.service import MultiSemesterPlanner


@dataclass(frozen=True, slots=True)
class WhatIfEvaluationService:
    """Apply ordered scenario operations and rerun the bounded planner."""

    planner: MultiSemesterPlanner
    transition_service: HypotheticalStateTransitionService = (
        HypotheticalStateTransitionService()
    )

    def __post_init__(self) -> None:
        if not isinstance(self.planner, MultiSemesterPlanner):
            raise TypeError("planner must be a MultiSemesterPlanner")
        if not isinstance(self.transition_service, HypotheticalStateTransitionService):
            raise TypeError(
                "transition_service must be a HypotheticalStateTransitionService"
            )

    def evaluate(self, request: WhatIfPlanningRequest) -> WhatIfResult:
        if not isinstance(request, WhatIfPlanningRequest):
            raise TypeError("request must be a WhatIfPlanningRequest")

        baseline = self.planner.plan(request.baseline)
        scenario_request = request.baseline
        for index, scenario in enumerate(request.scenarios, start=1):
            scenario_request = self._apply(
                scenario_request,
                scenario,
                operation_index=index,
            )
        scenario_result = self.planner.plan(scenario_request)
        trace = _what_if_trace(request, baseline, scenario_result)
        metadata = _what_if_metadata(scenario_result.metadata, trace)
        return WhatIfResult(
            baseline=baseline,
            scenario=scenario_result,
            delta=_delta(baseline, scenario_result),
            scenarios=request.scenarios,
            metadata=metadata,
            trace=trace,
        )

    def _apply(
        self,
        request: MultiSemesterPlanningRequest,
        scenario: ScenarioOperation,
        *,
        operation_index: int,
    ) -> MultiSemesterPlanningRequest:
        if isinstance(scenario, CourseOutcomeScenario):
            current = request.initial_student
            sequence = _next_projection_sequence(current)
            outcome = replace(
                scenario.to_hypothetical_outcome(),
                sequence=sequence,
            )
            projected = self.transition_service.apply(current, (outcome,))
            return _replace_student(request, projected.student_state)

        if isinstance(scenario, ExcludeCourseScenario):
            excluded = tuple(
                sorted(
                    {*request.excluded_courses, scenario.course},
                    key=lambda item: item.course_id,
                )
            )
            return replace(request, excluded_courses=excluded)

        if isinstance(scenario, PlanningPreferenceScenario):
            return replace(request, preferences=scenario.preferences)

        if isinstance(scenario, PlanningHorizonScenario):
            terms = _resize_terms(request, scenario.max_semesters)
            return replace(
                request,
                max_semesters=scenario.max_semesters,
                term_sequence=terms,
                search_policy=replace(
                    request.search_policy,
                    max_semesters=scenario.max_semesters,
                ),
            )

        raise TypeError(f"unsupported scenario operation at index {operation_index}")


def _replace_student(
    request: MultiSemesterPlanningRequest,
    student: StudentState,
) -> MultiSemesterPlanningRequest:
    return replace(
        request,
        initial_student=student,
        candidate_request=replace(request.candidate_request, student=student),
    )


def _next_projection_sequence(student: StudentState) -> int:
    return max((item.sequence for item in student.projected_outcomes), default=0) + 1


def _resize_terms(
    request: MultiSemesterPlanningRequest,
    max_semesters: int,
) -> tuple:
    if not request.term_sequence:
        return ()
    terms = list(request.term_sequence[:max_semesters])
    if len(terms) >= max_semesters:
        return tuple(terms)
    from ..domain.multi_semester import PlanningTerm
    from ..domain.semester import TermType

    next_index = max((item.index for item in terms), default=0) + 1
    terms.extend(
        PlanningTerm(index, TermType.MAIN)
        for index in range(next_index, max_semesters + 1)
    )
    return tuple(terms)


def _delta(
    baseline: MultiSemesterPlanResult,
    scenario: MultiSemesterPlanResult,
) -> WhatIfDelta:
    baseline_courses = _selected_courses(baseline)
    scenario_courses = _selected_courses(scenario)
    baseline_satisfied, baseline_blocking = _audit_ids(baseline)
    scenario_satisfied, scenario_blocking = _audit_ids(scenario)
    baseline_conditions = _condition_keys(baseline.conditions)
    new_conditions = tuple(
        condition
        for condition in scenario.conditions
        if repr(condition.to_dict()) not in baseline_conditions
    )
    baseline_reviews = _review_codes(baseline)
    scenario_reviews = _review_codes(scenario)
    baseline_credits = baseline.final_state.earned_credit_hours
    scenario_credits = scenario.final_state.earned_credit_hours
    credit_delta = (
        scenario_credits - baseline_credits
        if baseline_credits is not None and scenario_credits is not None
        else None
    )
    return WhatIfDelta(
        baseline_status=baseline.status,
        scenario_status=scenario.status,
        added_courses=tuple(scenario_courses - baseline_courses),
        removed_courses=tuple(baseline_courses - scenario_courses),
        newly_satisfied_requirements=tuple(scenario_satisfied - baseline_satisfied),
        newly_blocking_requirements=tuple(scenario_blocking - baseline_blocking),
        earned_credit_hours_delta=credit_delta,
        path_length_delta=len(scenario.steps) - len(baseline.steps),
        new_conditions=tuple(new_conditions),
        new_review_items=tuple(scenario_reviews - baseline_reviews),
    )


def _selected_courses(result: MultiSemesterPlanResult) -> set:
    return {
        item.identity for step in result.steps for item in step.plan.selected_courses
    }


def _audit_ids(result: MultiSemesterPlanResult) -> tuple[set[str], set[str]]:
    if result.final_audit is None:
        return set(), set()
    progress = result.final_audit.progress
    return (
        set(progress.satisfied_requirement_ids),
        set(progress.blocking_requirement_ids),
    )


def _condition_keys(conditions) -> set[str]:
    return {repr(item.to_dict()) for item in conditions}


def _review_codes(result: MultiSemesterPlanResult) -> set[str]:
    diagnostics: list[PlanDiagnostic] = list(result.review_items)
    diagnostics.extend(item for step in result.steps for item in step.plan.review_items)
    return {item.code.value for item in diagnostics}


def _what_if_trace(
    request: WhatIfPlanningRequest,
    baseline: MultiSemesterPlanResult,
    scenario: MultiSemesterPlanResult,
) -> DecisionTrace:
    return DecisionTrace(
        DecisionTraceNode(
            node_id="what-if-evaluation",
            code=TraceCode.WHAT_IF,
            node_type=TraceNodeType.ROOT,
            status=DecisionStatus.INDETERMINATE,
            expected_value=baseline.status.value,
            actual_value=scenario.status.value,
            reason_codes=(ReasonCode.PROJECTION_ASSUMPTION,),
            children=(baseline.trace.root, scenario.trace.root),
            metadata=(
                TraceMetadata("scenario_count", len(request.scenarios)),
                TraceMetadata("baseline_status", baseline.status.value),
                TraceMetadata("scenario_status", scenario.status.value),
            ),
        )
    )


def _what_if_metadata(metadata: ResultMetadata, trace: DecisionTrace) -> ResultMetadata:
    return replace(
        metadata,
        authoritative=False,
        reason_codes=tuple(
            dict.fromkeys((*metadata.reason_codes, ReasonCode.PROJECTION_ASSUMPTION))
        ),
        decision_trace=trace,
    )


__all__ = ["WhatIfEvaluationService"]
