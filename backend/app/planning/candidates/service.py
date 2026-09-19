"""Candidate generation from typed audit, dependency, and eligibility facts."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.academic_state import FactStatus
from ..domain.candidates import (
    CandidateAvailability,
    CandidateCourse,
    CandidateGenerationRequest,
    CandidateGenerationResult,
    CandidateGenerationStatus,
    CandidateIntent,
    CandidateReasonCode,
    CandidateSourceCoverage,
)
from ..domain.context import (
    EligibilityContext,
    EvaluationHorizon,
    ProposedTermContext,
    RegistrationIntent,
)
from ..domain.dependency import DependencyCoverageStatus
from ..domain.electives import Concentration, ElectivePool
from ..domain.eligibility import (
    CourseEligibilityRuleSet,
    EligibilityDecision,
    EligibilityRequest,
    RuleSetStatus,
)
from ..domain.evaluation import EvaluationOutcome
from ..domain.reasons import ReasonCode
from ..domain.requirements import (
    ConcentrationRequirement,
    CourseCompletionRequirement,
    CourseCountFromPoolRequirement,
    EarnedCreditThresholdRequirement,
    ElectiveSlotRequirement,
    FieldTrainingRequirement,
    MinimumGPARequirement,
    RequirementSetStatus,
    TotalProgramCreditsRequirement,
    ZeroCreditCourseRequirement,
)
from ..domain.results import ResultMetadata
from ..domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceMetadata,
    TraceNodeType,
)
from ..domain.version import DatasetVersion
from ..eligibility.service import EligibilityService
from ..policy import ExecutionMode


@dataclass
class _CandidateDraft:
    reasons: set[CandidateReasonCode] = field(default_factory=set)
    requirement_ids: set[str] = field(default_factory=set)
    unlocks: set[object] = field(default_factory=set)
    concentration_ids: set[object] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class CandidateGenerator:
    """Generate relevant course possibilities without selecting a semester."""

    eligibility_service: EligibilityService
    dataset_version: DatasetVersion | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.eligibility_service, EligibilityService):
            raise TypeError("eligibility_service must be an EligibilityService")
        if self.dataset_version is not None and not isinstance(
            self.dataset_version, DatasetVersion
        ):
            raise TypeError("dataset_version must be a DatasetVersion or None")
        if self.dataset_version is None:
            object.__setattr__(
                self,
                "dataset_version",
                self.eligibility_service.rule_evaluator.dataset_version,
            )

    def generate(
        self, request: CandidateGenerationRequest
    ) -> CandidateGenerationResult:
        if not isinstance(request, CandidateGenerationRequest):
            raise TypeError("request must be a CandidateGenerationRequest")
        courses = {item.identity: item for item in request.courses}
        rule_sets = {item.target_course: item for item in request.rule_sets}
        drafts: dict[object, _CandidateDraft] = {}
        required_targets: set[object] = set()
        catalog_gap = False
        requirements_gap = False
        dependency_gap = False

        def add(
            identity, reason, *, requirement_id=None, unlock=None, concentration=None
        ):
            nonlocal catalog_gap
            if identity not in courses:
                catalog_gap = True
                return
            draft = drafts.setdefault(identity, _CandidateDraft())
            draft.reasons.add(reason)
            if requirement_id is not None:
                draft.requirement_ids.add(requirement_id)
            if unlock is not None:
                draft.unlocks.add(unlock)
            if concentration is not None:
                draft.concentration_ids.add(concentration)

        if request.requirement_set is not None:
            for requirement in request.requirement_set.requirements:
                definition = requirement.definition
                if isinstance(definition, CourseCompletionRequirement):
                    if not _requirement_satisfied(
                        request, requirement.requirement_id, definition.course
                    ):
                        add(
                            definition.course,
                            CandidateReasonCode.REQUIRED_FOR_PROGRAM,
                            requirement_id=requirement.requirement_id,
                        )
                        required_targets.add(definition.course)
                elif isinstance(definition, ZeroCreditCourseRequirement):
                    if not _requirement_satisfied(
                        request, requirement.requirement_id, definition.course
                    ):
                        add(
                            definition.course,
                            CandidateReasonCode.REQUIRED_ZERO_CREDIT,
                            requirement_id=requirement.requirement_id,
                        )
                        required_targets.add(definition.course)
                elif isinstance(definition, CourseCountFromPoolRequirement):
                    pool = _find_pool(request.pools, definition.pool_id)
                    if pool is None or not self._pool_allowed(pool):
                        requirements_gap = True
                    elif not _requirement_satisfied(
                        request, requirement.requirement_id, None
                    ):
                        for identity in pool.allowed_courses:
                            if (
                                request.student.pass_status(identity)
                                is not FactStatus.KNOWN_TRUE
                            ):
                                add(
                                    identity,
                                    CandidateReasonCode.ELECTIVE_REQUIREMENT,
                                    requirement_id=requirement.requirement_id,
                                )
                elif isinstance(definition, ElectiveSlotRequirement):
                    pool = _find_pool(request.pools, definition.pool_id)
                    if pool is None or not self._pool_allowed(pool):
                        requirements_gap = True
                    elif not _requirement_satisfied(
                        request, requirement.requirement_id, None
                    ):
                        for identity in pool.allowed_courses:
                            if (
                                request.student.pass_status(identity)
                                is not FactStatus.KNOWN_TRUE
                            ):
                                add(
                                    identity,
                                    CandidateReasonCode.ELECTIVE_REQUIREMENT,
                                    requirement_id=requirement.requirement_id,
                                )
                elif isinstance(definition, ConcentrationRequirement):
                    if not _requirement_satisfied(
                        request, requirement.requirement_id, None
                    ):
                        for concentration_id in definition.concentrations:
                            concentration = _find_concentration(
                                request.concentrations, concentration_id
                            )
                            if concentration is None or not self._concentration_allowed(
                                concentration
                            ):
                                requirements_gap = True
                                continue
                            for identity in concentration.allowed_courses:
                                if (
                                    request.student.pass_status(identity)
                                    is not FactStatus.KNOWN_TRUE
                                ):
                                    add(
                                        identity,
                                        CandidateReasonCode.CONCENTRATION_PROGRESS,
                                        requirement_id=requirement.requirement_id,
                                        concentration=concentration_id,
                                    )
                elif isinstance(
                    definition,
                    (
                        EarnedCreditThresholdRequirement,
                        FieldTrainingRequirement,
                        MinimumGPARequirement,
                        TotalProgramCreditsRequirement,
                    ),
                ):
                    # These requirements affect audit/progress facts, not the
                    # course-candidate universe directly.
                    continue
                else:
                    requirements_gap = True

        # Structural unlock sources are deliberately kept separate from
        # requirement-driven candidates.  Reachability is not proof of need.
        if request.dependency_graph is not None:
            for target in sorted(required_targets, key=lambda item: item.course_id):
                for reference in request.dependency_graph.direct_dependencies(target):
                    if not reference.traversable or not hasattr(
                        reference.dependency, "course_id"
                    ):
                        continue
                    dependency = reference.dependency
                    if (
                        request.student.pass_status(dependency)
                        is not FactStatus.KNOWN_TRUE
                    ):
                        add(
                            dependency,
                            CandidateReasonCode.UNLOCKS_REQUIRED_COURSE,
                            unlock=target,
                        )
            for current in sorted(
                request.student.current_courses, key=lambda item: item.course_id
            ):
                for reference in request.dependency_graph.direct_dependents(current):
                    add(
                        reference.target_course, CandidateReasonCode.PROJECTED_NEXT_STEP
                    )
            if any(
                item.dependency_coverage is not DependencyCoverageStatus.COMPLETE
                for item in request.dependency_graph.definitions
            ) or any(
                not item.node_present for item in request.dependency_graph.references
            ):
                dependency_gap = True

        for intent in request.intents:
            if intent.intent is RegistrationIntent.RETAKE_AFTER_FAILURE:
                if (
                    request.student.has_failed_attempt(intent.course)
                    and request.student.pass_status(intent.course)
                    is not FactStatus.KNOWN_TRUE
                ):
                    add(intent.course, CandidateReasonCode.RETAKE_AFTER_FAILURE)
            elif intent.intent is RegistrationIntent.RETAKE_FOR_IMPROVEMENT:
                if request.student.pass_status(intent.course) is FactStatus.KNOWN_TRUE:
                    add(intent.course, CandidateReasonCode.RETAKE_FOR_IMPROVEMENT)

        candidates: list[CandidateCourse] = []
        excluded: list[object] = []
        for identity in sorted(drafts, key=lambda item: item.course_id):
            draft = drafts[identity]
            intent = _intent_for(request.intents, identity)
            rule_set = rule_sets.get(identity)
            if rule_set is None:
                rule_set = CourseEligibilityRuleSet(
                    target_course=identity,
                    status=RuleSetStatus.UNAVAILABLE,
                    reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                )
            proposed_courses = request.context.proposed_courses
            proposed_term = None
            if (
                request.context.horizon is EvaluationHorizon.PROJECTED
                or proposed_courses
            ):
                proposed_term = ProposedTermContext(
                    target_course=identity,
                    proposed_courses=tuple(
                        sorted(
                            set((*proposed_courses, identity)),
                            key=lambda item: item.course_id,
                        )
                    ),
                    term_id=request.context.term_id,
                )
            eligibility = self.eligibility_service.check(
                EligibilityRequest(
                    student=request.student,
                    course=courses[identity],
                    rule_set=rule_set,
                    context=EligibilityContext(
                        intent=intent,
                        horizon=request.context.horizon,
                        proposed_term=proposed_term,
                    ),
                )
            )
            availability = _availability_for(eligibility.decision)
            if availability is None:
                excluded.append(identity)
                continue
            reasons = set(draft.reasons)
            if len(draft.unlocks) > 1:
                reasons.add(CandidateReasonCode.UNLOCKS_MULTIPLE_COURSES)
            candidate = CandidateCourse(
                course=courses[identity],
                eligibility=eligibility,
                availability=availability,
                reason_codes=tuple(reasons),
                requirement_ids=tuple(draft.requirement_ids),
                unlocks=tuple(draft.unlocks),
                concentration_ids=tuple(draft.concentration_ids),
                metadata=eligibility.metadata,
                trace=_candidate_trace(identity, availability, eligibility),
            )
            candidates.append(candidate)

        source_coverage = _coverage_for(
            request,
            catalog_gap=catalog_gap,
            requirements_gap=requirements_gap,
            dependency_gap=dependency_gap,
            candidate_identities=tuple(drafts),
        )
        status = source_coverage.overall
        policy = self.eligibility_service.rule_evaluator.policy
        reason_codes = []
        if status is CandidateGenerationStatus.INCOMPLETE:
            reason_codes.append(ReasonCode.CANDIDATE_COVERAGE_INCOMPLETE)
        elif status is CandidateGenerationStatus.UNAVAILABLE:
            reason_codes.append(ReasonCode.CANDIDATE_COVERAGE_UNAVAILABLE)
        reason_codes.extend(
            reason
            for candidate in candidates
            if candidate.eligibility is not None
            for reason in candidate.eligibility.reason_codes
        )
        review = status is not CandidateGenerationStatus.COMPLETE or any(
            item.availability is CandidateAvailability.REVIEW_REQUIRED
            for item in candidates
        )
        authoritative = (
            policy.mode is ExecutionMode.AUTHORITATIVE
            and status is CandidateGenerationStatus.COMPLETE
            and not review
            and all(
                item.metadata is not None and item.metadata.authoritative
                for item in candidates
            )
        )
        trace = _generation_trace(status, candidates, source_coverage)
        provenance = tuple(
            provenance
            for item in candidates
            if item.metadata is not None
            for provenance in item.metadata.provenance
        )
        metadata = ResultMetadata(
            dataset_version=self.dataset_version,
            execution_mode=policy.mode,
            authoritative=authoritative,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            provenance=tuple(dict.fromkeys(provenance)),
            decision_trace=trace,
            requires_human_review=review,
        )
        return CandidateGenerationResult(
            status=status,
            available_candidates=tuple(
                item
                for item in candidates
                if item.availability is CandidateAvailability.AVAILABLE
            ),
            conditional_candidates=tuple(
                item
                for item in candidates
                if item.availability is CandidateAvailability.CONDITIONAL
            ),
            review_candidates=tuple(
                item
                for item in candidates
                if item.availability is CandidateAvailability.REVIEW_REQUIRED
            ),
            excluded_course_ids=tuple(excluded),
            source_coverage=source_coverage,
            metadata=metadata,
            trace=trace,
        )

    def _pool_allowed(self, pool: ElectivePool) -> bool:
        return self.eligibility_service.rule_evaluator.policy.assess(
            pool.approval_status,
            verification_status=pool.verification_status,
            critical=True,
        ).allowed

    def _concentration_allowed(self, concentration: Concentration) -> bool:
        return self.eligibility_service.rule_evaluator.policy.assess(
            concentration.approval_status,
            verification_status=concentration.verification_status,
            critical=True,
        ).allowed


def _requirement_satisfied(request, requirement_id: str, course):
    if request.degree_audit is not None:
        result = next(
            (
                item
                for item in request.degree_audit.requirement_results
                if item.requirement_id == requirement_id
            ),
            None,
        )
        if result is not None:
            return result.outcome is EvaluationOutcome.SATISFIED
    return (
        course is not None
        and request.student.pass_status(course) is FactStatus.KNOWN_TRUE
    )


def _find_pool(pools, pool_id):
    return next((item for item in pools if item.pool_id == pool_id), None)


def _find_concentration(concentrations, concentration_id):
    return next(
        (item for item in concentrations if item.concentration_id == concentration_id),
        None,
    )


def _intent_for(intents: tuple[CandidateIntent, ...], identity):
    for item in intents:
        if item.course == identity:
            return item.intent
    return RegistrationIntent.NORMAL


def _availability_for(decision):
    if decision is EligibilityDecision.ELIGIBLE:
        return CandidateAvailability.AVAILABLE
    if decision is EligibilityDecision.CONDITIONAL:
        return CandidateAvailability.CONDITIONAL
    if decision in {
        EligibilityDecision.REQUIRES_ADVISOR_REVIEW,
        EligibilityDecision.HUMAN_REVIEW_REQUIRED,
        EligibilityDecision.UNSUPPORTED,
    }:
        return CandidateAvailability.REVIEW_REQUIRED
    return None


def _coverage_for(
    request: CandidateGenerationRequest,
    *,
    catalog_gap: bool,
    requirements_gap: bool,
    dependency_gap: bool,
    candidate_identities: tuple[object, ...],
) -> CandidateSourceCoverage:
    supplied = request.source_coverage
    catalog = supplied.catalog
    if not request.courses and catalog is CandidateGenerationStatus.COMPLETE:
        catalog = CandidateGenerationStatus.UNAVAILABLE
    elif catalog_gap and catalog is CandidateGenerationStatus.COMPLETE:
        catalog = CandidateGenerationStatus.INCOMPLETE
    requirements = supplied.requirements
    if request.requirement_set is not None:
        requirements = {
            RequirementSetStatus.COMPLETE: CandidateGenerationStatus.COMPLETE,
            RequirementSetStatus.INCOMPLETE: CandidateGenerationStatus.INCOMPLETE,
            RequirementSetStatus.UNAVAILABLE: CandidateGenerationStatus.UNAVAILABLE,
        }[request.requirement_set.status]
    rules = supplied.eligibility_rules
    if request.rule_sets:
        supplied_rule_targets = {item.target_course for item in request.rule_sets}
        rules = (
            CandidateGenerationStatus.COMPLETE
            if all(item.status is RuleSetStatus.COMPLETE for item in request.rule_sets)
            and set(candidate_identities).issubset(supplied_rule_targets)
            else CandidateGenerationStatus.INCOMPLETE
        )
    elif candidate_identities and rules is CandidateGenerationStatus.COMPLETE:
        rules = CandidateGenerationStatus.INCOMPLETE
    dependency = supplied.dependency_graph
    if request.dependency_graph is not None:
        dependency = CandidateGenerationStatus.COMPLETE
    if requirements_gap and requirements is CandidateGenerationStatus.COMPLETE:
        requirements = CandidateGenerationStatus.INCOMPLETE
    return CandidateSourceCoverage(
        catalog=catalog,
        requirements=requirements,
        eligibility_rules=rules,
        dependency_graph=(
            CandidateGenerationStatus.INCOMPLETE
            if dependency_gap and dependency is CandidateGenerationStatus.COMPLETE
            else dependency
        ),
    )


def _candidate_trace(identity, availability, eligibility):
    status = {
        CandidateAvailability.AVAILABLE: DecisionStatus.SATISFIED,
        CandidateAvailability.CONDITIONAL: DecisionStatus.CONDITIONAL,
        CandidateAvailability.REVIEW_REQUIRED: DecisionStatus.ADVISOR_REVIEW,
    }[availability]
    children = ()
    if eligibility.metadata.decision_trace is not None:
        children = (eligibility.metadata.decision_trace.root,)
    return DecisionTrace(
        DecisionTraceNode(
            node_id=f"candidate:{identity.course_id}",
            code=TraceCode.CANDIDATE,
            node_type=TraceNodeType.REQUIREMENT_CHECK,
            status=status,
            subject=identity,
            expected_value="ACADEMICALLY_RELEVANT",
            actual_value=availability.value,
            reason_codes=eligibility.reason_codes,
            children=children,
        )
    )


def _generation_trace(status, candidates, source_coverage):
    trace_status = (
        DecisionStatus.SATISFIED
        if status is CandidateGenerationStatus.COMPLETE
        else DecisionStatus.INDETERMINATE
        if status is CandidateGenerationStatus.INCOMPLETE
        else DecisionStatus.NOT_EVALUATED
    )
    children = tuple(item.trace.root for item in candidates if item.trace is not None)
    return DecisionTrace(
        DecisionTraceNode(
            node_id="candidate-generation",
            code=TraceCode.CANDIDATE_GENERATION,
            node_type=TraceNodeType.ROOT,
            status=trace_status,
            expected_value=CandidateGenerationStatus.COMPLETE.value,
            actual_value=status.value,
            children=children,
            metadata=(TraceMetadata("coverage", source_coverage.overall.value),),
        )
    )


__all__ = ["CandidateGenerator"]
