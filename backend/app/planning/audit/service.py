"""Deterministic Degree Audit orchestration over typed requirement facts."""

from __future__ import annotations

from collections.abc import Iterable

from ..domain.academic_state import FactStatus
from ..domain.audit import (
    ConcentrationRequirementEvidence,
    DegreeAuditRequest,
    DegreeAuditResult,
    DegreeAuditStatus,
    PoolRequirementEvidence,
    RequirementEvaluation,
)
from ..domain.electives import ElectivePool
from ..domain.evaluation import EvaluationOutcome
from ..domain.program_progress import (
    ConcentrationProgress,
    NumericProgress,
    PoolProgress,
    ProgramProgress,
    RequirementCountProgress,
)
from ..domain.requirements import (
    CourseCompletionRequirement,
    ElectiveSlotRequirement,
    FieldTrainingRequirement,
    MinimumGPARequirement,
    ProgramRequirement,
    RequirementSetStatus,
    TotalProgramCreditsRequirement,
    ZeroCreditCourseRequirement,
)
from ..domain.results import ResultMetadata
from ..domain.reasons import ReasonCode
from ..domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceNodeType,
)
from ..domain.version import DatasetVersion
from ..policy import ExecutionMode, ExecutionPolicy
from .evaluator import RequirementEvaluator


class DegreeAuditService:
    """Audit a supplied requirement set without fetching or parsing data."""

    def __init__(
        self,
        policy: ExecutionPolicy,
        dataset_version: DatasetVersion,
        *,
        evaluator: RequirementEvaluator | None = None,
    ) -> None:
        if not isinstance(policy, ExecutionPolicy):
            raise TypeError("policy must be an ExecutionPolicy")
        if not isinstance(dataset_version, DatasetVersion):
            raise TypeError("dataset_version must be a DatasetVersion")
        if evaluator is not None and not isinstance(evaluator, RequirementEvaluator):
            raise TypeError("evaluator must be a RequirementEvaluator or None")
        self._policy = policy
        self._dataset_version = dataset_version
        self._evaluator = evaluator or RequirementEvaluator(policy, dataset_version)

    def audit(self, request: DegreeAuditRequest) -> DegreeAuditResult:
        """Evaluate all requirements applicable to the requested audit stage."""

        if not isinstance(request, DegreeAuditRequest):
            raise TypeError("request must be a DegreeAuditRequest")
        requirements = request.requirement_set.requirements_for_stage(request.stage)
        slot_requirements = tuple(
            item
            for item in requirements
            if isinstance(item.definition, ElectiveSlotRequirement)
        )
        ordinary_requirements = tuple(
            item for item in requirements if item not in slot_requirements
        )
        results = [
            self._evaluator.evaluate(
                requirement,
                request.student,
                pools=request.pools,
                concentrations=request.concentrations,
                program_facts=request.program_facts,
            )
            for requirement in ordinary_requirements
        ]
        results.extend(self._evaluate_slots(slot_requirements, request))
        results = sorted(results, key=lambda item: item.requirement_id)
        status = self._aggregate_status(request, results)
        progress = self._build_progress(request, requirements, results)
        return self._build_result(request, status, results, progress)

    check = audit

    def _evaluate_slots(
        self,
        requirements: tuple[ProgramRequirement, ...],
        request: DegreeAuditRequest,
    ) -> list[RequirementEvaluation]:
        if not requirements:
            return []
        pool_by_id = {pool.pool_id: pool for pool in request.pools}
        valid: list[ProgramRequirement] = []
        candidates: dict[str, tuple] = {}
        possible: dict[str, tuple] = {}
        for requirement in requirements:
            definition = requirement.definition
            assert isinstance(definition, ElectiveSlotRequirement)
            pool = pool_by_id.get(definition.pool_id) if definition.pool_id else None
            if pool is None or not self._pool_allowed(pool):
                continue
            valid.append(requirement)
            candidates[requirement.requirement_id] = tuple(
                item
                for item in pool.allowed_courses
                if request.student.pass_status(item) is FactStatus.KNOWN_TRUE
            )
            possible[requirement.requirement_id] = tuple(
                item
                for item in pool.allowed_courses
                if request.student.pass_status(item)
                in {FactStatus.KNOWN_TRUE, FactStatus.UNKNOWN}
            )

        results: list[RequirementEvaluation] = []
        invalid_ids = {
            item.requirement_id for item in requirements if item not in valid
        }
        for requirement in requirements:
            if requirement.requirement_id in invalid_ids:
                results.append(
                    self._evaluator.evaluate(
                        requirement,
                        request.student,
                        pools=request.pools,
                        program_facts=request.program_facts,
                    )
                )

        if not valid:
            return results

        known_matching = _maximum_matching(candidates)
        possible_matching = _maximum_matching(possible)
        if len(known_matching) == len(valid):
            for requirement in valid:
                results.append(
                    self._evaluator.evaluate(
                        requirement,
                        request.student,
                        pools=request.pools,
                        program_facts=request.program_facts,
                        allocated_course=known_matching[requirement.requirement_id],
                        slot_outcome=EvaluationOutcome.SATISFIED,
                    )
                )
        elif len(possible_matching) == len(valid):
            for requirement in valid:
                results.append(
                    self._evaluator.evaluate(
                        requirement,
                        request.student,
                        pools=request.pools,
                        program_facts=request.program_facts,
                        slot_outcome=EvaluationOutcome.INDETERMINATE,
                    )
                )
        else:
            for requirement in valid:
                assigned = known_matching.get(requirement.requirement_id)
                results.append(
                    self._evaluator.evaluate(
                        requirement,
                        request.student,
                        pools=request.pools,
                        program_facts=request.program_facts,
                        allocated_course=assigned,
                        slot_outcome=(
                            EvaluationOutcome.SATISFIED
                            if assigned is not None
                            else EvaluationOutcome.UNSATISFIED
                        ),
                    )
                )
        return results

    def _pool_allowed(self, pool: ElectivePool) -> bool:
        return self._policy.assess(
            pool.approval_status,
            verification_status=pool.verification_status,
            critical=True,
        ).allowed

    def _aggregate_status(
        self,
        request: DegreeAuditRequest,
        results: list[RequirementEvaluation],
    ) -> DegreeAuditStatus:
        if any(item.outcome is EvaluationOutcome.UNSATISFIED for item in results):
            return DegreeAuditStatus.ACADEMIC_REQUIREMENTS_NOT_SATISFIED
        if any(ReasonCode.UNSUPPORTED_RULE in item.reason_codes for item in results):
            return DegreeAuditStatus.UNSUPPORTED
        if request.requirement_set.status is not RequirementSetStatus.COMPLETE:
            return DegreeAuditStatus.HUMAN_REVIEW_REQUIRED
        if any(item.requires_human_review for item in results):
            return DegreeAuditStatus.HUMAN_REVIEW_REQUIRED
        if any(item.outcome is EvaluationOutcome.INDETERMINATE for item in results):
            return DegreeAuditStatus.INDETERMINATE
        return DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED

    def _build_result(
        self,
        request: DegreeAuditRequest,
        status: DegreeAuditStatus,
        results: list[RequirementEvaluation],
        progress: ProgramProgress,
    ) -> DegreeAuditResult:
        reasons = list(request.requirement_set.reason_codes)
        if request.requirement_set.status is not RequirementSetStatus.COMPLETE:
            reasons.append(ReasonCode.MISSING_REQUIRED_DATA)
        for item in results:
            reasons.extend(item.reason_codes)
        reasons = list(dict.fromkeys(reasons))
        review = (
            request.requirement_set.status is not RequirementSetStatus.COMPLETE
            or any(item.requires_human_review for item in results)
        )
        authoritative = (
            self._policy.mode is ExecutionMode.AUTHORITATIVE
            and request.requirement_set.status is RequirementSetStatus.COMPLETE
            and not review
            and all(item.authoritative for item in results)
            and status
            in {
                DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED,
                DegreeAuditStatus.ACADEMIC_REQUIREMENTS_NOT_SATISFIED,
            }
        )
        children = [
            DecisionTraceNode(
                node_id="requirement-set-coverage",
                code=TraceCode.REQUIREMENT_SET_COVERAGE,
                node_type=TraceNodeType.VALUE_CHECK,
                status=(
                    DecisionStatus.SATISFIED
                    if request.requirement_set.status is RequirementSetStatus.COMPLETE
                    else DecisionStatus.INDETERMINATE
                ),
                subject=request.requirement_set.status.value,
                reason_codes=(
                    ()
                    if request.requirement_set.status is RequirementSetStatus.COMPLETE
                    else (ReasonCode.MISSING_REQUIRED_DATA,)
                ),
            )
        ]
        children.extend(item.decision_trace.root for item in results)
        root = DecisionTraceNode(
            node_id="degree-audit",
            code=TraceCode.DEGREE_AUDIT,
            node_type=TraceNodeType.ROOT,
            status=_audit_trace_status(status),
            subject=f"{request.student.regulation}:{request.student.program}",
            reason_codes=tuple(reasons),
            children=tuple(children),
        )
        metadata = ResultMetadata(
            dataset_version=(
                request.requirement_set.dataset_version or self._dataset_version
            ),
            execution_mode=self._policy.mode,
            authoritative=authoritative,
            reason_codes=tuple(reasons),
            provenance=request.requirement_set.provenance,
            decision_trace=DecisionTrace(root),
            requires_human_review=review,
        )
        return DegreeAuditResult(
            status=status,
            requirement_set_status=request.requirement_set.status,
            metadata=metadata,
            requirement_results=tuple(results),
            progress=progress,
        )

    def _build_progress(
        self,
        request: DegreeAuditRequest,
        requirements: tuple[ProgramRequirement, ...],
        results: list[RequirementEvaluation],
    ) -> ProgramProgress:
        by_id = {item.requirement_id: item for item in results}
        core_ids = tuple(
            item.requirement_id
            for item in requirements
            if isinstance(item.definition, CourseCompletionRequirement)
        )
        zero_ids = tuple(
            item.requirement_id
            for item in requirements
            if isinstance(item.definition, ZeroCreditCourseRequirement)
        )
        core = _count_progress(core_ids, by_id)
        zero = _count_progress(zero_ids, by_id)
        pool_progress = tuple(
            _pool_progress(item.evidence, item.outcome)
            for item in results
            if isinstance(item.evidence, PoolRequirementEvidence)
        )
        concentration_progress: list[ConcentrationProgress] = []
        for item in results:
            evidence = item.evidence
            if isinstance(evidence, ConcentrationRequirementEvidence):
                concentration_progress.extend(evidence.progress)
        gpa = None
        field_training = None
        for requirement in requirements:
            result = by_id.get(requirement.requirement_id)
            if result is None:
                continue
            if isinstance(requirement.definition, MinimumGPARequirement):
                evidence = result.evidence
                if hasattr(evidence, "observed"):
                    gpa = NumericProgress(
                        evidence.observed,
                        evidence.required,
                        result.outcome,
                    )
            if isinstance(requirement.definition, FieldTrainingRequirement):
                evidence = result.evidence
                if hasattr(evidence, "progress"):
                    field_training = evidence.progress

        required_program_credits = None
        for requirement in requirements:
            definition = requirement.definition
            if isinstance(definition, TotalProgramCreditsRequirement):
                required_program_credits = definition.required_credit_hours
                break
        earned = request.student.earned_credit_hours
        remaining = (
            max(required_program_credits - earned, 0)
            if required_program_credits is not None and earned is not None
            else None
        )
        satisfied = tuple(
            item.requirement_id
            for item in results
            if item.outcome is EvaluationOutcome.SATISFIED
        )
        outstanding = tuple(
            item.requirement_id
            for item in results
            if item.outcome is EvaluationOutcome.UNSATISFIED
        )
        unknown = tuple(
            item.requirement_id
            for item in results
            if item.outcome is EvaluationOutcome.INDETERMINATE
        )
        in_progress = tuple(
            item.requirement_id for item in results if _is_in_progress(item)
        )
        review = tuple(
            item.requirement_id for item in results if item.requires_human_review
        )
        return ProgramProgress(
            earned_credit_hours=earned,
            required_program_credits=required_program_credits,
            remaining_known_credits=remaining,
            core_requirements=core,
            zero_credit_requirements=zero,
            technical_electives=tuple(pool_progress),
            concentrations=tuple(concentration_progress),
            gpa=gpa,
            field_training=field_training,
            satisfied_requirement_ids=satisfied,
            outstanding_requirement_ids=outstanding,
            in_progress_requirement_ids=in_progress,
            unknown_requirement_ids=unknown,
            review_requirement_ids=review,
            blocking_requirement_ids=tuple(sorted(set(outstanding) | set(review))),
        )


def _maximum_matching(candidates: dict[str, tuple]) -> dict[str, object]:
    """Return a deterministic maximum matching slot -> course.

    Slot counts are small program-requirement collections.  Bounded
    backtracking gives a stable lexicographically-small allocation and avoids
    the surprising reassignment that a conventional augmenting-path order can
    produce when pools overlap.
    """

    slots = tuple(sorted(candidates))
    best: dict[str, object] = {}

    def search(index: int, used: set[object], assigned: dict[str, object]) -> None:
        nonlocal best
        if index == len(slots):
            if len(assigned) > len(best) or (
                len(assigned) == len(best)
                and _assignment_key(assigned) < _assignment_key(best)
            ):
                best = dict(assigned)
            return
        slot = slots[index]
        search(index + 1, used, assigned)
        for course in sorted(candidates.get(slot, ()), key=lambda item: item.course_id):
            if course in used:
                continue
            used.add(course)
            assigned[slot] = course
            search(index + 1, used, assigned)
            assigned.pop(slot)
            used.remove(course)

    search(0, set(), {})
    return best


def _assignment_key(assignment: dict[str, object]) -> tuple[str, ...]:
    return tuple(
        getattr(assignment.get(slot), "course_id", "~") for slot in sorted(assignment)
    )


def _count_progress(ids: Iterable[str], results: dict[str, RequirementEvaluation]):
    ids = tuple(ids)
    satisfied = sum(
        results[item].outcome is EvaluationOutcome.SATISFIED for item in ids
    )
    unknown = sum(
        results[item].outcome is EvaluationOutcome.INDETERMINATE for item in ids
    )
    in_progress = sum(_is_in_progress(results[item]) for item in ids)
    return RequirementCountProgress(
        satisfied_count=satisfied,
        total_known_count=len(ids),
        in_progress_count=in_progress,
        unknown_count=unknown,
    )


def _pool_progress(evidence, outcome: EvaluationOutcome):
    return PoolProgress(
        pool_id=evidence.pool_id,
        known_passed_count=evidence.known_passed_count,
        required_count=evidence.required_count,
        unknown_count=evidence.unknown_count,
        maximum_possible_count=evidence.maximum_possible_count,
        outcome=outcome,
        remaining_count=(
            0
            if outcome is EvaluationOutcome.SATISFIED
            else max(evidence.required_count - evidence.known_passed_count, 0)
            if outcome is EvaluationOutcome.UNSATISFIED
            else None
        ),
        known_passed_courses=tuple(
            item.course_id for item in evidence.known_passed_courses
        ),
        unknown_courses=tuple(item.course_id for item in evidence.unknown_courses),
    )


def _is_in_progress(result: RequirementEvaluation) -> bool:
    evidence = result.evidence
    return (
        evidence is not None
        and hasattr(evidence, "registration_status")
        and evidence.registration_status.value == "KNOWN_TRUE"
        and evidence.pass_status.value != "KNOWN_TRUE"
    )


def _audit_trace_status(status: DegreeAuditStatus) -> DecisionStatus:
    if status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED:
        return DecisionStatus.SATISFIED
    if status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_NOT_SATISFIED:
        return DecisionStatus.FAILED
    if status is DegreeAuditStatus.UNSUPPORTED:
        return DecisionStatus.UNSUPPORTED
    return DecisionStatus.INDETERMINATE
