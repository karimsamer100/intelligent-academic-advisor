"""Deterministic orchestration for one proposed academic semester."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations

from ..candidates.service import CandidateGenerator
from ..domain.candidates import (
    CandidateAvailability,
    CandidateCourse,
    CandidateGenerationRequest,
    CandidateGenerationResult,
    CandidateGenerationStatus,
)
from ..domain.conditions import FutureCondition
from ..domain.context import EvaluationHorizon, RegistrationIntent
from ..domain.eligibility import EligibilityDecision
from ..domain.planning import (
    LoadPreference,
    PlanAlternative,
    PlanAlternativeType,
    PlanDiagnostic,
    PlanDiagnosticCode,
    PlanExclusion,
    PlanExclusionCode,
    PlanSelectionReasonCode,
    PlanStatus,
    PlanTargetDeviation,
    PlanningCoverage,
    PlanningCoverageStatus,
    SelectedPlanCourse,
    SingleSemesterPlanResult,
    SingleSemesterPlanningRequest,
)
from ..domain.ranking import PriorityRankingResult, RankedCandidate
from ..domain.reasons import ReasonCode
from ..domain.results import ResultMetadata
from ..domain.semester import (
    ProposedCourse,
    ProposedSemester,
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
from ..policy import ExecutionMode, ExecutionPolicy
from ..ranking.service import PriorityRankingService
from ..semester.service import SemesterValidator


@dataclass(frozen=True, slots=True)
class _EvaluatedPlan:
    items: tuple[RankedCandidate, ...]
    validation: SemesterValidationResult
    status: PlanStatus

    @property
    def identities(self) -> tuple[object, ...]:
        return tuple(item.candidate.identity for item in self.items)


@dataclass(frozen=True, slots=True)
class SingleSemesterPlanner:
    """Compose candidate generation, ranking, and final semester validation."""

    candidate_generator: CandidateGenerator
    priority_ranker: PriorityRankingService
    semester_validator: SemesterValidator

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_generator, CandidateGenerator):
            raise TypeError("candidate_generator must be a CandidateGenerator")
        if not isinstance(self.priority_ranker, PriorityRankingService):
            raise TypeError("priority_ranker must be a PriorityRankingService")
        if not isinstance(self.semester_validator, SemesterValidator):
            raise TypeError("semester_validator must be a SemesterValidator")

    def plan(self, request: SingleSemesterPlanningRequest) -> SingleSemesterPlanResult:
        if not isinstance(request, SingleSemesterPlanningRequest):
            raise TypeError("request must be a SingleSemesterPlanningRequest")

        candidate_result = self.candidate_generator.generate(
            _discovery_request(request.candidate_request)
        )
        ranking = self.priority_ranker.rank(candidate_result)
        considered, search_limited = _bounded_items(
            ranking,
            request.search_policy.max_candidates_considered,
            excluded_courses=request.excluded_courses,
        )

        safe_items = tuple(
            item
            for item in considered
            if item.candidate.availability
            in {CandidateAvailability.AVAILABLE, CandidateAvailability.CONDITIONAL}
            and not (
                item.candidate.availability is CandidateAvailability.CONDITIONAL
                and request.horizon is EvaluationHorizon.CURRENT
            )
        )
        safe_plans, hit_limit = self._search(request, safe_items, allow_review=False)
        search_limited = search_limited or hit_limit

        review_items = tuple(
            item
            for item in considered
            if item.candidate.availability is CandidateAvailability.REVIEW_REQUIRED
        )
        review_plans: tuple[_EvaluatedPlan, ...] = ()
        if not safe_plans or request.preferences.include_review_candidates:
            review_plans, hit_limit = self._search(
                request,
                (*safe_items, *review_items),
                allow_review=True,
            )
            search_limited = search_limited or hit_limit
            review_plans = tuple(
                item
                for item in review_plans
                if item.status in {PlanStatus.REVIEW_REQUIRED, PlanStatus.UNSUPPORTED}
            )

        primary = min(
            safe_plans,
            key=lambda item: _objective(item, request),
            default=None,
        )
        if primary is None and review_plans:
            primary = min(review_plans, key=lambda item: _objective(item, request))

        coverage = _coverage_for(candidate_result, search_limited)
        deviation = (
            _deviation(primary, request, coverage) if primary is not None else None
        )
        status = (
            _plan_status(primary, deviation, coverage)
            if primary is not None
            else PlanStatus.NO_FEASIBLE_PLAN
        )

        selected = _selected_courses(primary, request) if primary is not None else ()
        alternatives = self._alternatives(
            request,
            primary,
            safe_plans,
            review_plans,
            coverage,
        )
        exclusions = _exclusions(
            candidate_result,
            considered,
            selected,
            primary,
            search_limited,
            request,
        )
        diagnostics = _diagnostics(
            candidate_result,
            coverage,
            primary,
            deviation,
            search_limited,
        )
        conditions = _conditions_for(primary)
        metadata = _metadata(
            request,
            candidate_result,
            ranking,
            primary,
            coverage,
            status,
            diagnostics,
            self.semester_validator.eligibility_service.rule_evaluator.policy,
        )
        trace = _plan_trace(
            request,
            candidate_result,
            ranking,
            primary,
            alternatives,
            coverage,
            status,
        )
        if metadata.decision_trace is None:
            metadata = ResultMetadata(
                dataset_version=metadata.dataset_version,
                execution_mode=metadata.execution_mode,
                authoritative=metadata.authoritative,
                approval_status=metadata.approval_status,
                verification_status=metadata.verification_status,
                engine_version=metadata.engine_version,
                ruleset_version=metadata.ruleset_version,
                warnings=metadata.warnings,
                reason_codes=metadata.reason_codes,
                provenance=metadata.provenance,
                decision_trace=trace,
                requires_human_review=metadata.requires_human_review,
            )
        else:
            metadata = _replace_trace(metadata, trace)

        achieved_credit_hours = (
            primary.validation.load_result.total_credit_hours
            if primary is not None
            else None
        )
        achieved_course_count = len(selected)
        return SingleSemesterPlanResult(
            status=status,
            selected_courses=selected,
            validation_result=primary.validation if primary is not None else None,
            alternatives=alternatives,
            achieved_credit_hours=achieved_credit_hours,
            achieved_course_count=achieved_course_count,
            preferences=request.preferences,
            conditions=conditions,
            review_items=diagnostics,
            exclusions=exclusions,
            coverage=coverage,
            metadata=metadata,
            trace=trace,
            deviation=deviation,
        )

    def _search(
        self,
        request: SingleSemesterPlanningRequest,
        items: tuple[RankedCandidate, ...],
        *,
        allow_review: bool,
    ) -> tuple[tuple[_EvaluatedPlan, ...], bool]:
        plans: list[_EvaluatedPlan] = []
        evaluated = 0
        hit_limit = False
        for size in range(1, len(items) + 1):
            for combo in combinations(items, size):
                if evaluated >= request.search_policy.max_combinations_evaluated:
                    hit_limit = True
                    return tuple(plans), hit_limit
                evaluated += 1
                validation = self._validate_combination(request, combo)
                plan_status = _validation_plan_status(combo, validation)
                if plan_status in {PlanStatus.VALID, PlanStatus.CONDITIONAL}:
                    plans.append(_EvaluatedPlan(tuple(combo), validation, plan_status))
                elif allow_review and plan_status in {
                    PlanStatus.REVIEW_REQUIRED,
                    PlanStatus.UNSUPPORTED,
                }:
                    plans.append(_EvaluatedPlan(tuple(combo), validation, plan_status))
        return tuple(plans), hit_limit

    def _validate_combination(
        self,
        request: SingleSemesterPlanningRequest,
        items: tuple[RankedCandidate, ...],
    ) -> SemesterValidationResult:
        proposed = tuple(
            ProposedCourse(
                item.candidate.course,
                registration_intent=_registration_intent(item.candidate),
            )
            for item in items
        )
        return self.semester_validator.validate(
            SemesterValidationRequest(
                student=request.student,
                semester=ProposedSemester(
                    request.term_type,
                    proposed,
                    request.effective_term_id,
                ),
                rule_sets=request.candidate_request.rule_sets,
                load_policy=request.load_policy,
                horizon=request.horizon,
            )
        )

    def _alternatives(
        self,
        request: SingleSemesterPlanningRequest,
        primary: _EvaluatedPlan | None,
        safe_plans: tuple[_EvaluatedPlan, ...],
        review_plans: tuple[_EvaluatedPlan, ...],
        coverage: PlanningCoverage,
    ) -> tuple[PlanAlternative, ...]:
        if primary is None or request.search_policy.max_alternatives == 0:
            return ()
        candidates = sorted(
            (*safe_plans, *review_plans),
            key=lambda item: _objective(item, request),
        )
        result: list[PlanAlternative] = []
        seen: set[tuple[object, ...]] = {primary.identities}
        for item in candidates:
            if len(result) >= request.search_policy.max_alternatives:
                break
            if item.identities in seen:
                continue
            if (
                item.status is PlanStatus.REVIEW_REQUIRED
                and not request.preferences.include_review_candidates
                and primary.status is not PlanStatus.REVIEW_REQUIRED
            ):
                continue
            alternative_type = _alternative_type(primary, item)
            selected = _selected_courses(item, request)
            deviation = _deviation(item, request, coverage)
            alternative_status = _plan_status(item, deviation, coverage)
            result.append(
                PlanAlternative(
                    alternative_type=alternative_type,
                    selected_courses=selected,
                    validation_result=item.validation,
                    status=alternative_status,
                    conditions=_conditions_for(item),
                    deviation=deviation,
                    trace=_alternative_trace(alternative_type, item),
                )
            )
            seen.add(item.identities)
        return tuple(result)


def _bounded_items(
    ranking: PriorityRankingResult,
    maximum: int,
    *,
    excluded_courses: tuple[object, ...] = (),
) -> tuple[tuple[RankedCandidate, ...], bool]:
    excluded = set(excluded_courses)
    available = tuple(
        item for item in ranking.items if item.candidate.identity not in excluded
    )
    values = available[:maximum]
    return values, len(available) > len(values)


def _discovery_request(
    request: CandidateGenerationRequest,
) -> CandidateGenerationRequest:
    """Make potential same-term references visible during candidate discovery.

    Candidate generation happens before the planner has selected a set.  A
    concurrent prerequisite therefore cannot be classified from the final
    semester yet.  The catalog is used only as a potential discovery context;
    every accepted combination is re-evaluated by ``SemesterValidator`` with
    its exact proposed-term membership.
    """

    if request.context.proposed_courses:
        return request
    potential_courses = tuple(item.identity for item in request.courses)
    if not potential_courses:
        return request
    context = replace(
        request.context,
        proposed_courses=potential_courses,
    )
    return replace(request, context=context)


def _registration_intent(candidate: CandidateCourse) -> RegistrationIntent:
    if candidate.eligibility is not None:
        return candidate.eligibility.intent
    return RegistrationIntent.NORMAL


def _validation_plan_status(
    items: tuple[RankedCandidate, ...], validation: SemesterValidationResult
) -> PlanStatus:
    if any(
        item.candidate.availability is CandidateAvailability.REVIEW_REQUIRED
        for item in items
    ):
        if validation.status is SemesterValidationStatus.UNSUPPORTED:
            return PlanStatus.UNSUPPORTED
        if validation.status is not SemesterValidationStatus.INVALID:
            return PlanStatus.REVIEW_REQUIRED
    return {
        SemesterValidationStatus.VALID: PlanStatus.VALID,
        SemesterValidationStatus.CONDITIONAL: PlanStatus.CONDITIONAL,
        SemesterValidationStatus.HUMAN_REVIEW_REQUIRED: PlanStatus.REVIEW_REQUIRED,
        SemesterValidationStatus.UNSUPPORTED: PlanStatus.UNSUPPORTED,
        SemesterValidationStatus.INVALID: PlanStatus.NO_FEASIBLE_PLAN,
    }[validation.status]


def _plan_status(
    evaluated: _EvaluatedPlan,
    deviation: PlanTargetDeviation | None,
    coverage: PlanningCoverage,
) -> PlanStatus:
    if evaluated.status in {
        PlanStatus.CONDITIONAL,
        PlanStatus.REVIEW_REQUIRED,
        PlanStatus.UNSUPPORTED,
    }:
        return evaluated.status
    if (
        deviation is not None
        or coverage.academic_overall is not PlanningCoverageStatus.COMPLETE
    ):
        return PlanStatus.PARTIAL
    return PlanStatus.VALID


def _objective(
    evaluated: _EvaluatedPlan,
    request: SingleSemesterPlanningRequest,
) -> tuple[object, ...]:
    total = evaluated.validation.load_result.total_credit_hours or 0
    count = evaluated.validation.load_result.course_count
    band = request.load_policy.band_for(request.term_type, request.student.gpa)
    target = request.preferences.preferred_credit_target(
        band.max_credit_hours if band is not None else None
    )
    over_credit = (
        max(total - request.preferences.maximum_preferred_credit_hours, 0)
        if request.preferences.maximum_preferred_credit_hours is not None
        else 0
    )
    over_count = (
        max(count - request.preferences.maximum_preferred_course_count, 0)
        if request.preferences.maximum_preferred_course_count is not None
        else 0
    )
    if (
        request.preferences.load_preference is LoadPreference.MAXIMIZE_ALLOWED
        and request.preferences.target_credit_hours is None
        and request.preferences.maximum_preferred_credit_hours is None
    ):
        load_key: tuple[object, ...] = (-total, -count)
    else:
        distance = abs(total - target) if target is not None else 0
        load_key = (distance, over_credit, over_count)
    required = sum(
        CandidateAvailability.AVAILABLE is item.candidate.availability
        and any(
            code.value.startswith("REQUIRED") for code in item.candidate.reason_codes
        )
        for item in evaluated.items
    )
    unlocks = sum(item.factors.unlock_count for item in evaluated.items)
    concentrations = sum(
        item.factors.concentration_contribution for item in evaluated.items
    )
    electives = sum(item.factors.elective_contribution for item in evaluated.items)
    status_rank = {
        PlanStatus.VALID: 0,
        PlanStatus.CONDITIONAL: 1,
        PlanStatus.REVIEW_REQUIRED: 2,
        PlanStatus.UNSUPPORTED: 3,
        PlanStatus.PARTIAL: 4,
        PlanStatus.NO_FEASIBLE_PLAN: 5,
    }[evaluated.status]
    return (
        status_rank,
        *load_key,
        -required,
        -unlocks,
        -concentrations,
        -electives,
        tuple(item.rank for item in evaluated.items),
        tuple(item.candidate.identity.course_id for item in evaluated.items),
    )


def _selected_courses(
    evaluated: _EvaluatedPlan | None,
    request: SingleSemesterPlanningRequest,
) -> tuple[SelectedPlanCourse, ...]:
    if evaluated is None:
        return ()
    result = []
    all_conditions = _conditions_for(evaluated)
    for item in evaluated.items:
        candidate = item.candidate
        reasons = set()
        if any(code.value == "REQUIRED_FOR_PROGRAM" for code in candidate.reason_codes):
            reasons.add(PlanSelectionReasonCode.REQUIRED_PROGRESS)
        if any(code.value == "REQUIRED_ZERO_CREDIT" for code in candidate.reason_codes):
            reasons.add(PlanSelectionReasonCode.ZERO_CREDIT_PROGRESS)
        if any(code.value == "ELECTIVE_REQUIREMENT" for code in candidate.reason_codes):
            reasons.add(PlanSelectionReasonCode.ELECTIVE_PROGRESS)
        if any(
            code.value == "CONCENTRATION_PROGRESS" for code in candidate.reason_codes
        ):
            reasons.add(PlanSelectionReasonCode.CONCENTRATION_PROGRESS)
        if candidate.unlocks:
            reasons.add(PlanSelectionReasonCode.DEPENDENCY_UNLOCK)
        if any(code.value.startswith("RETAKE") for code in candidate.reason_codes):
            reasons.add(PlanSelectionReasonCode.RETAKE_REQUEST)
        if candidate.availability is CandidateAvailability.CONDITIONAL:
            reasons.add(PlanSelectionReasonCode.CONDITIONAL_FUTURE)
        reasons.add(PlanSelectionReasonCode.PRIORITY_ORDER)
        if request.preferences.target_credit_hours is not None:
            reasons.add(PlanSelectionReasonCode.PREFERENCE_FIT)
        conditions = tuple(
            condition
            for condition in all_conditions
            if condition in _conditions_for_candidate(candidate)
            or condition in evaluated.validation.conditions
        )
        result.append(
            SelectedPlanCourse(
                candidate=candidate,
                priority_factors=item.factors,
                registration_intent=_registration_intent(candidate),
                why_selected=tuple(reasons),
                conditions=conditions,
                trace=candidate.trace,
            )
        )
    return tuple(result)


def _conditions_for_candidate(
    candidate: CandidateCourse,
) -> tuple[FutureCondition, ...]:
    if candidate.eligibility is None:
        return ()
    return candidate.eligibility.conditions


def _conditions_for(evaluated: _EvaluatedPlan | None) -> tuple[FutureCondition, ...]:
    if evaluated is None:
        return ()
    conditions: list[FutureCondition] = list(evaluated.validation.conditions)
    for item in evaluated.items:
        conditions.extend(_conditions_for_candidate(item.candidate))
    return _unique_conditions(tuple(conditions))


def _unique_conditions(
    conditions: tuple[FutureCondition, ...],
) -> tuple[FutureCondition, ...]:
    result = []
    seen = set()
    for condition in conditions:
        key = repr(condition.to_dict())
        if key not in seen:
            seen.add(key)
            result.append(condition)
    return tuple(result)


def _deviation(
    evaluated: _EvaluatedPlan,
    request: SingleSemesterPlanningRequest,
    coverage: PlanningCoverage,
) -> PlanTargetDeviation | None:
    band = request.load_policy.band_for(request.term_type, request.student.gpa)
    target = request.preferences.preferred_credit_target(
        band.max_credit_hours if band is not None else None
    )
    achieved = evaluated.validation.load_result.total_credit_hours
    if target is None or achieved is None or achieved == target:
        return None
    reasons = [ReasonCode.PLAN_TARGET_NOT_REACHED]
    if coverage.overall is not PlanningCoverageStatus.COMPLETE:
        reasons.append(ReasonCode.CANDIDATE_COVERAGE_INCOMPLETE)
    return PlanTargetDeviation(
        requested_credit_hours=target,
        achieved_credit_hours=achieved,
        difference=achieved - target,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def _coverage_for(
    candidate_result: CandidateGenerationResult,
    search_limited: bool,
) -> PlanningCoverage:
    source = candidate_result.source_coverage

    def convert(value: CandidateGenerationStatus) -> PlanningCoverageStatus:
        return PlanningCoverageStatus(value.value)

    return PlanningCoverage(
        academic_requirements=convert(source.requirements),
        candidate_generation=convert(candidate_result.status),
        eligibility_rules=convert(source.eligibility_rules),
        dependency=convert(source.dependency_graph),
        offering=PlanningCoverageStatus.UNAVAILABLE,
        timetable=PlanningCoverageStatus.UNAVAILABLE,
        search=(
            PlanningCoverageStatus.INCOMPLETE
            if search_limited
            else PlanningCoverageStatus.COMPLETE
        ),
        projection=PlanningCoverageStatus.COMPLETE,
        uel=convert(source.uel),
    )


def _exclusions(
    candidate_result: CandidateGenerationResult,
    considered: tuple[RankedCandidate, ...],
    selected: tuple[SelectedPlanCourse, ...],
    primary: _EvaluatedPlan | None,
    search_limited: bool,
    request: SingleSemesterPlanningRequest,
) -> tuple[PlanExclusion, ...]:
    selected_ids = {item.identity for item in selected}
    exclusions: dict[object, PlanExclusion] = {}
    for identity in candidate_result.excluded_course_ids:
        exclusions[identity] = PlanExclusion(
            identity,
            PlanExclusionCode.ACADEMICALLY_INELIGIBLE,
            reason_codes=(ReasonCode.MISSING_PREREQUISITE,),
        )
    candidate_by_id = {item.identity: item for item in candidate_result.candidates}
    for identity in request.excluded_courses:
        if identity in selected_ids:
            continue
        exclusions[identity] = PlanExclusion(
            identity,
            PlanExclusionCode.SCENARIO_EXCLUDED,
            candidate_by_id.get(identity),
            reason_codes=(ReasonCode.SCENARIO_EXCLUSION,),
        )
    considered_ids = {item.candidate.identity for item in considered}
    for item in considered:
        identity = item.candidate.identity
        if identity in selected_ids:
            continue
        if (
            item.candidate.eligibility is not None
            and item.candidate.eligibility.decision is EligibilityDecision.UNSUPPORTED
        ):
            code = PlanExclusionCode.UNSUPPORTED
        elif item.candidate.availability is CandidateAvailability.REVIEW_REQUIRED:
            code = PlanExclusionCode.REVIEW_REQUIRED
        elif (
            item.candidate.availability is CandidateAvailability.CONDITIONAL
            and request.horizon is EvaluationHorizon.CURRENT
        ):
            code = PlanExclusionCode.CONDITIONAL_NOT_NEEDED
        elif primary is None:
            code = PlanExclusionCode.LOAD_LIMIT
        else:
            code = PlanExclusionCode.LOWER_PRIORITY
        exclusions[identity] = PlanExclusion(identity, code, item.candidate)
    if search_limited:
        for item in candidate_result.candidates:
            if (
                item.identity not in considered_ids
                and item.identity not in selected_ids
                and item.identity not in request.excluded_courses
            ):
                exclusions[item.identity] = PlanExclusion(
                    item.identity,
                    PlanExclusionCode.SEARCH_LIMIT,
                    item,
                    reason_codes=(ReasonCode.PLAN_SEARCH_LIMIT_REACHED,),
                )
    return tuple(sorted(exclusions.values(), key=lambda item: item.course.course_id))


def _diagnostics(
    candidate_result: CandidateGenerationResult,
    coverage: PlanningCoverage,
    primary: _EvaluatedPlan | None,
    deviation: PlanTargetDeviation | None,
    search_limited: bool,
) -> tuple[PlanDiagnostic, ...]:
    diagnostics: list[PlanDiagnostic] = []
    if primary is None:
        diagnostics.append(
            PlanDiagnostic(
                PlanDiagnosticCode.NO_FEASIBLE_PLAN,
                reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
            )
        )
    if not candidate_result.candidates:
        diagnostics.append(PlanDiagnostic(PlanDiagnosticCode.NO_CANDIDATES))
    if primary is not None and primary.status is PlanStatus.REVIEW_REQUIRED:
        diagnostics.append(
            PlanDiagnostic(
                PlanDiagnosticCode.REVIEW_REQUIRED,
                reason_codes=(ReasonCode.ADVISOR_REVIEW_REQUIRED,),
            )
        )
    if primary is not None and primary.status is PlanStatus.UNSUPPORTED:
        diagnostics.append(
            PlanDiagnostic(
                PlanDiagnosticCode.UNSUPPORTED,
                reason_codes=(ReasonCode.UNSUPPORTED_CASE,),
            )
        )
    if coverage.overall is not PlanningCoverageStatus.COMPLETE:
        diagnostics.append(
            PlanDiagnostic(
                PlanDiagnosticCode.COVERAGE_INCOMPLETE,
                expected=PlanningCoverageStatus.COMPLETE.value,
                actual=coverage.overall.value,
                reason_codes=(ReasonCode.CANDIDATE_COVERAGE_INCOMPLETE,),
            )
        )
    if coverage.offering is PlanningCoverageStatus.UNAVAILABLE:
        diagnostics.append(PlanDiagnostic(PlanDiagnosticCode.OFFERING_UNAVAILABLE))
    if coverage.timetable is PlanningCoverageStatus.UNAVAILABLE:
        diagnostics.append(PlanDiagnostic(PlanDiagnosticCode.TIMETABLE_UNAVAILABLE))
    if search_limited:
        diagnostics.append(
            PlanDiagnostic(
                PlanDiagnosticCode.SEARCH_LIMIT_REACHED,
                reason_codes=(ReasonCode.PLAN_SEARCH_LIMIT_REACHED,),
            )
        )
    if deviation is not None:
        diagnostics.append(
            PlanDiagnostic(
                PlanDiagnosticCode.PLAN_TARGET_NOT_REACHED,
                expected=deviation.requested_credit_hours,
                actual=deviation.achieved_credit_hours,
                reason_codes=deviation.reason_codes,
            )
        )
    return tuple(diagnostics)


def _metadata(
    request: SingleSemesterPlanningRequest,
    candidate_result: CandidateGenerationResult,
    ranking: PriorityRankingResult,
    primary: _EvaluatedPlan | None,
    coverage: PlanningCoverage,
    status: PlanStatus,
    diagnostics: tuple[PlanDiagnostic, ...],
    policy: ExecutionPolicy,
) -> ResultMetadata:
    if not isinstance(policy, ExecutionPolicy):
        raise TypeError("policy must be an ExecutionPolicy")
    validation_metadata = primary.validation.metadata if primary is not None else None
    reason_codes = list(candidate_result.metadata.reason_codes)
    reason_codes.extend(ranking.metadata.reason_codes)
    if validation_metadata is not None:
        reason_codes.extend(validation_metadata.reason_codes)
    reason_codes.extend(
        reason for diagnostic in diagnostics for reason in diagnostic.reason_codes
    )
    provenance = list(candidate_result.metadata.provenance)
    provenance.extend(ranking.metadata.provenance)
    if validation_metadata is not None:
        provenance.extend(validation_metadata.provenance)
    authoritative = (
        policy.mode is ExecutionMode.AUTHORITATIVE
        and status is PlanStatus.VALID
        and coverage.overall is PlanningCoverageStatus.COMPLETE
        and candidate_result.metadata.authoritative
        and ranking.metadata.authoritative
        and validation_metadata is not None
        and validation_metadata.authoritative
    )
    requires_review = (
        status in {PlanStatus.REVIEW_REQUIRED, PlanStatus.UNSUPPORTED}
        or candidate_result.metadata.requires_human_review
        or (
            validation_metadata is not None
            and validation_metadata.requires_human_review
        )
    )
    return ResultMetadata(
        dataset_version=candidate_result.metadata.dataset_version,
        execution_mode=policy.mode,
        authoritative=authoritative,
        approval_status=(
            validation_metadata.approval_status
            if validation_metadata is not None
            else candidate_result.metadata.approval_status
        ),
        verification_status=(
            validation_metadata.verification_status
            if validation_metadata is not None
            else candidate_result.metadata.verification_status
        ),
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        provenance=tuple(dict.fromkeys(provenance)),
        requires_human_review=requires_review,
    )


def _replace_trace(metadata: ResultMetadata, trace: DecisionTrace) -> ResultMetadata:
    return ResultMetadata(
        dataset_version=metadata.dataset_version,
        execution_mode=metadata.execution_mode,
        authoritative=metadata.authoritative,
        approval_status=metadata.approval_status,
        verification_status=metadata.verification_status,
        engine_version=metadata.engine_version,
        ruleset_version=metadata.ruleset_version,
        warnings=metadata.warnings,
        reason_codes=metadata.reason_codes,
        provenance=metadata.provenance,
        decision_trace=trace,
        requires_human_review=metadata.requires_human_review,
    )


def _plan_trace(
    request: SingleSemesterPlanningRequest,
    candidate_result: CandidateGenerationResult,
    ranking: PriorityRankingResult,
    primary: _EvaluatedPlan | None,
    alternatives: tuple[PlanAlternative, ...],
    coverage: PlanningCoverage,
    status: PlanStatus,
) -> DecisionTrace:
    children = [
        _preferences_trace(request).root,
        candidate_result.trace.root,
        ranking.trace.root,
    ]
    if primary is not None:
        children.append(_selection_trace(primary, status).root)
        children.append(primary.validation.trace.root)
    children.extend(item.trace.root for item in alternatives if item.trace is not None)
    status_value = _trace_status(status)
    root = DecisionTraceNode(
        node_id="single-semester-planning",
        code=TraceCode.SINGLE_SEMESTER_PLANNING,
        node_type=TraceNodeType.ROOT,
        status=status_value,
        expected_value=PlanStatus.VALID.value,
        actual_value=status.value,
        children=tuple(children),
        metadata=(
            TraceMetadata("term_type", request.term_type.value),
            TraceMetadata("horizon", request.horizon.value),
            TraceMetadata("load_preference", request.preferences.load_preference.value),
            TraceMetadata("coverage", coverage.overall.value),
        ),
    )
    return DecisionTrace(root)


def _preferences_trace(request: SingleSemesterPlanningRequest) -> DecisionTrace:
    preferences = request.preferences
    return DecisionTrace(
        DecisionTraceNode(
            node_id="planning-preferences",
            code=TraceCode.PLANNING_PREFERENCES,
            node_type=TraceNodeType.VALUE_CHECK,
            status=DecisionStatus.SATISFIED,
            expected_value=preferences.load_preference.value,
            actual_value=preferences.load_preference.value,
            metadata=(
                TraceMetadata("target_credit_hours", preferences.target_credit_hours),
                TraceMetadata(
                    "maximum_preferred_credit_hours",
                    preferences.maximum_preferred_credit_hours,
                ),
                TraceMetadata(
                    "maximum_preferred_course_count",
                    preferences.maximum_preferred_course_count,
                ),
            ),
        )
    )


def _selection_trace(evaluated: _EvaluatedPlan, status: PlanStatus) -> DecisionTrace:
    identities = tuple(item.candidate.identity.course_id for item in evaluated.items)
    return DecisionTrace(
        DecisionTraceNode(
            node_id="plan-selection",
            code=TraceCode.PLAN_SELECTION,
            node_type=TraceNodeType.REQUIREMENT_CHECK,
            status=_trace_status(status),
            expected_value=PlanStatus.VALID.value,
            actual_value=identities,
            children=tuple(item.trace.root for item in evaluated.items),
            metadata=(
                TraceMetadata("course_count", len(identities)),
                TraceMetadata("validation_status", evaluated.validation.status.value),
            ),
        )
    )


def _alternative_trace(
    alternative_type: PlanAlternativeType,
    evaluated: _EvaluatedPlan,
) -> DecisionTrace:
    return DecisionTrace(
        DecisionTraceNode(
            node_id=f"plan-alternative:{alternative_type.value}",
            code=TraceCode.PLAN_ALTERNATIVE,
            node_type=TraceNodeType.REQUIREMENT_CHECK,
            status=_trace_status(evaluated.status),
            actual_value=alternative_type.value,
            children=(evaluated.validation.trace.root,),
        )
    )


def _trace_status(status: PlanStatus) -> DecisionStatus:
    return {
        PlanStatus.VALID: DecisionStatus.SATISFIED,
        PlanStatus.CONDITIONAL: DecisionStatus.CONDITIONAL,
        PlanStatus.PARTIAL: DecisionStatus.INDETERMINATE,
        PlanStatus.REVIEW_REQUIRED: DecisionStatus.ADVISOR_REVIEW,
        PlanStatus.NO_FEASIBLE_PLAN: DecisionStatus.FAILED,
        PlanStatus.UNSUPPORTED: DecisionStatus.UNSUPPORTED,
    }[status]


def _alternative_type(primary: _EvaluatedPlan, alternative: _EvaluatedPlan):
    if alternative.status is PlanStatus.REVIEW_REQUIRED:
        return PlanAlternativeType.REVIEW_PATH
    if alternative.status is PlanStatus.CONDITIONAL:
        return PlanAlternativeType.CONDITIONAL_PATH
    primary_total = primary.validation.load_result.total_credit_hours or 0
    alternative_total = alternative.validation.load_result.total_credit_hours or 0
    if alternative_total < primary_total:
        return PlanAlternativeType.LOWER_LOAD
    if any(
        any(
            code.value in {"ELECTIVE_REQUIREMENT", "CONCENTRATION_PROGRESS"}
            for code in item.candidate.reason_codes
        )
        for item in alternative.items
    ):
        return PlanAlternativeType.ALTERNATE_ELECTIVE
    return PlanAlternativeType.LOWER_LOAD


__all__ = ["SingleSemesterPlanner"]
