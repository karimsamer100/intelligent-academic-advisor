"""Pure evaluation of one typed program requirement."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.academic_state import FactStatus
from ..domain.audit import (
    ConcentrationRequirementEvidence,
    CourseRequirementEvidence,
    FieldTrainingRequirementEvidence,
    NumericRequirementEvidence,
    PoolRequirementEvidence,
    RequirementEvaluation,
    SlotRequirementEvidence,
    UnsupportedRequirementEvidence,
)
from ..domain.electives import Concentration, ElectivePool
from ..domain.evaluation import EvaluationOutcome
from ..domain.lifecycle import ApprovalStatus
from ..domain.program_facts import ProgramFactCoverage, StudentProgramFacts
from ..domain.program_progress import (
    ConcentrationProgress,
    FieldTrainingProgress,
)
from ..domain.requirements import (
    ConcentrationRequirement,
    CourseCompletionRequirement,
    CourseCountFromPoolRequirement,
    ElectiveSlotRequirement,
    EarnedCreditThresholdRequirement,
    FieldTrainingRequirement,
    MinimumGPARequirement,
    ProgramRequirement,
    TotalProgramCreditsRequirement,
    ZeroCreditCourseRequirement,
)
from ..domain.results import ResultMetadata
from ..domain.reasons import ReasonCode
from ..domain.student import StudentState
from ..domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceNodeType,
)
from ..domain.version import DatasetVersion
from ..policy import ExecutionPolicy


@dataclass(frozen=True, slots=True)
class RequirementEvaluator:
    """Evaluate governed requirement definitions without repository access."""

    policy: ExecutionPolicy
    dataset_version: DatasetVersion

    def __post_init__(self) -> None:
        if not isinstance(self.policy, ExecutionPolicy):
            raise TypeError("policy must be an ExecutionPolicy")
        if not isinstance(self.dataset_version, DatasetVersion):
            raise TypeError("dataset_version must be a DatasetVersion")

    def evaluate(
        self,
        requirement: ProgramRequirement,
        student: StudentState,
        *,
        pools: tuple[ElectivePool, ...] = (),
        concentrations: tuple[Concentration, ...] = (),
        program_facts: StudentProgramFacts | None = None,
        allocated_course=None,
        slot_outcome: EvaluationOutcome | None = None,
    ) -> RequirementEvaluation:
        """Evaluate one requirement from already-loaded typed facts."""

        if not isinstance(requirement, ProgramRequirement):
            raise TypeError("requirement must be a ProgramRequirement")
        if not isinstance(student, StudentState):
            raise TypeError("student must be a StudentState")
        if program_facts is None:
            program_facts = StudentProgramFacts()

        policy_decision = self.policy.assess(
            requirement.approval_status,
            verification_status=requirement.verification_status,
            critical=requirement.critical_for_planner,
        )
        if not policy_decision.allowed:
            return self._result(
                requirement,
                EvaluationOutcome.INDETERMINATE,
                self._trace(
                    requirement,
                    TraceCode.REQUIREMENT,
                    DecisionStatus.BLOCKED
                    if requirement.approval_status is ApprovalStatus.BLOCKED
                    else DecisionStatus.CONFLICTED
                    if requirement.approval_status is ApprovalStatus.CONFLICTED
                    else DecisionStatus.INDETERMINATE,
                    reasons=policy_decision.reason_codes,
                ),
                evidence=UnsupportedRequirementEvidence(
                    requirement.definition.definition_type
                    if requirement.definition is not None
                    else None
                ),
                extra_reasons=policy_decision.reason_codes,
                force_review=True,
                policy_decision=policy_decision,
            )

        definition = requirement.definition
        if definition is None:
            return self._result(
                requirement,
                EvaluationOutcome.INDETERMINATE,
                self._trace(
                    requirement,
                    TraceCode.REQUIREMENT,
                    DecisionStatus.UNSUPPORTED,
                    reasons=(ReasonCode.UNSUPPORTED_RULE,),
                ),
                evidence=UnsupportedRequirementEvidence(None),
                extra_reasons=(ReasonCode.UNSUPPORTED_RULE,),
                force_review=True,
                policy_decision=policy_decision,
            )

        if isinstance(
            definition, (CourseCompletionRequirement, ZeroCreditCourseRequirement)
        ):
            return self._evaluate_course_requirement(
                requirement, student, definition, policy_decision
            )
        if isinstance(
            definition,
            (EarnedCreditThresholdRequirement, TotalProgramCreditsRequirement),
        ):
            return self._evaluate_numeric_requirement(
                requirement, student, definition, policy_decision
            )
        if isinstance(definition, MinimumGPARequirement):
            return self._evaluate_gpa_requirement(
                requirement, student, definition, policy_decision
            )
        if isinstance(definition, CourseCountFromPoolRequirement):
            return self._evaluate_pool_requirement(
                requirement, student, definition, pools, policy_decision
            )
        if isinstance(definition, ConcentrationRequirement):
            return self._evaluate_concentration_requirement(
                requirement,
                student,
                definition,
                pools,
                concentrations,
                policy_decision,
            )
        if isinstance(definition, ElectiveSlotRequirement):
            return self._evaluate_slot_requirement(
                requirement,
                student,
                definition,
                pools,
                allocated_course,
                slot_outcome,
                policy_decision,
            )
        if isinstance(definition, FieldTrainingRequirement):
            return self._evaluate_field_training(
                requirement, definition, program_facts, policy_decision
            )

        return self._result(
            requirement,
            EvaluationOutcome.INDETERMINATE,
            self._trace(
                requirement,
                TraceCode.REQUIREMENT,
                DecisionStatus.UNSUPPORTED,
                reasons=(ReasonCode.UNSUPPORTED_RULE,),
            ),
            evidence=UnsupportedRequirementEvidence(definition.definition_type),
            extra_reasons=(ReasonCode.UNSUPPORTED_RULE,),
            force_review=True,
            policy_decision=policy_decision,
        )

    def _evaluate_course_requirement(
        self,
        requirement: ProgramRequirement,
        student: StudentState,
        definition: CourseCompletionRequirement | ZeroCreditCourseRequirement,
        policy_decision,
    ) -> RequirementEvaluation:
        pass_status = student.pass_status(definition.course)
        registration_status = student.registration_status(definition.course)
        outcome = _fact_outcome(pass_status)
        reasons: tuple[ReasonCode, ...] = ()
        if (
            outcome is EvaluationOutcome.UNSATISFIED
            and registration_status is FactStatus.KNOWN_TRUE
        ):
            reasons = (ReasonCode.CURRENTLY_REGISTERED,)
        if outcome is EvaluationOutcome.INDETERMINATE:
            reasons = (ReasonCode.MISSING_REQUIRED_DATA,)
        evidence = CourseRequirementEvidence(
            course=definition.course,
            pass_status=pass_status,
            registration_status=registration_status,
        )
        return self._result(
            requirement,
            outcome,
            self._trace(
                requirement,
                TraceCode.REQUIREMENT_COMPLETED,
                _trace_status(outcome),
                subject=definition.course,
                expected_value="KNOWN_TRUE",
                actual_value=pass_status.value,
                reasons=reasons,
            ),
            evidence=evidence,
            extra_reasons=reasons,
            force_review=outcome is EvaluationOutcome.INDETERMINATE,
            policy_decision=policy_decision,
        )

    def _evaluate_numeric_requirement(
        self,
        requirement: ProgramRequirement,
        student: StudentState,
        definition: EarnedCreditThresholdRequirement | TotalProgramCreditsRequirement,
        policy_decision,
    ) -> RequirementEvaluation:
        required = (
            definition.minimum_earned_credit_hours
            if isinstance(definition, EarnedCreditThresholdRequirement)
            else definition.required_credit_hours
        )
        observed = student.earned_credit_hours
        if observed is None:
            outcome = EvaluationOutcome.INDETERMINATE
            reasons = (ReasonCode.MISSING_REQUIRED_DATA,)
        else:
            outcome = (
                EvaluationOutcome.SATISFIED
                if observed >= required
                else EvaluationOutcome.UNSATISFIED
            )
            reasons = ()
        code = (
            TraceCode.MIN_EARNED_CREDITS
            if isinstance(definition, EarnedCreditThresholdRequirement)
            else TraceCode.TOTAL_PROGRAM_CREDITS
        )
        return self._result(
            requirement,
            outcome,
            self._trace(
                requirement,
                code,
                _trace_status(outcome),
                expected_value=required,
                actual_value=observed,
                reasons=reasons,
            ),
            evidence=NumericRequirementEvidence(observed, required),
            extra_reasons=reasons,
            force_review=outcome is EvaluationOutcome.INDETERMINATE,
            policy_decision=policy_decision,
        )

    def _evaluate_gpa_requirement(
        self,
        requirement: ProgramRequirement,
        student: StudentState,
        definition: MinimumGPARequirement,
        policy_decision,
    ) -> RequirementEvaluation:
        observed = student.gpa
        if observed is None:
            outcome = EvaluationOutcome.INDETERMINATE
            reasons = (ReasonCode.MISSING_REQUIRED_DATA,)
        else:
            outcome = (
                EvaluationOutcome.SATISFIED
                if observed >= definition.minimum_gpa
                else EvaluationOutcome.UNSATISFIED
            )
            reasons = ()
        return self._result(
            requirement,
            outcome,
            self._trace(
                requirement,
                TraceCode.MIN_GPA,
                _trace_status(outcome),
                expected_value=definition.minimum_gpa,
                actual_value=observed,
                reasons=reasons,
            ),
            evidence=NumericRequirementEvidence(observed, definition.minimum_gpa),
            extra_reasons=reasons,
            force_review=outcome is EvaluationOutcome.INDETERMINATE,
            policy_decision=policy_decision,
        )

    def _evaluate_pool_requirement(
        self,
        requirement: ProgramRequirement,
        student: StudentState,
        definition: CourseCountFromPoolRequirement,
        pools: tuple[ElectivePool, ...],
        policy_decision,
    ) -> RequirementEvaluation:
        pool = next(
            (item for item in pools if item.pool_id == definition.pool_id), None
        )
        if pool is None:
            return self._missing_pool_result(
                requirement, definition.pool_id.identifier, policy_decision
            )
        pool_policy = self.policy.assess(
            pool.approval_status,
            verification_status=pool.verification_status,
            critical=True,
        )
        if not pool_policy.allowed:
            return self._result(
                requirement,
                EvaluationOutcome.INDETERMINATE,
                self._trace(
                    requirement,
                    TraceCode.POOL_COUNT,
                    DecisionStatus.BLOCKED,
                    subject=definition.pool_id.identifier,
                    reasons=pool_policy.reason_codes,
                ),
                evidence=PoolRequirementEvidence(
                    definition.pool_id,
                    definition.required_count,
                    0,
                    0,
                    None,
                ),
                extra_reasons=pool_policy.reason_codes,
                force_review=True,
                policy_decision=policy_decision,
                extra_provenance=(pool.provenance,) if pool.provenance else (),
            )

        known = tuple(
            item
            for item in pool.allowed_courses
            if student.pass_status(item) is FactStatus.KNOWN_TRUE
        )
        unknown = tuple(
            item
            for item in pool.allowed_courses
            if student.pass_status(item) is FactStatus.UNKNOWN
        )
        potential = len(known) + len(unknown)
        maximum = len(pool.allowed_courses)
        if len(known) >= definition.required_count:
            outcome = EvaluationOutcome.SATISFIED
        elif potential < definition.required_count:
            outcome = EvaluationOutcome.UNSATISFIED
        else:
            outcome = EvaluationOutcome.INDETERMINATE
        reasons = (
            (ReasonCode.MISSING_REQUIRED_DATA,)
            if outcome is EvaluationOutcome.INDETERMINATE
            else ()
        )
        evidence = PoolRequirementEvidence(
            pool_id=definition.pool_id,
            required_count=definition.required_count,
            known_passed_count=len(known),
            unknown_count=len(unknown),
            maximum_possible_count=maximum,
            known_passed_courses=known,
            unknown_courses=unknown,
        )
        return self._result(
            requirement,
            outcome,
            self._trace(
                requirement,
                TraceCode.POOL_COUNT,
                _trace_status(outcome),
                subject=definition.pool_id.identifier,
                expected_value=definition.required_count,
                actual_value=len(known),
                reasons=reasons,
            ),
            evidence=evidence,
            extra_reasons=reasons,
            force_review=outcome is EvaluationOutcome.INDETERMINATE,
            policy_decision=policy_decision,
            extra_provenance=(pool.provenance,) if pool.provenance else (),
        )

    def _evaluate_concentration_requirement(
        self,
        requirement: ProgramRequirement,
        student: StudentState,
        definition: ConcentrationRequirement,
        pools: tuple[ElectivePool, ...],
        concentrations: tuple[Concentration, ...],
        policy_decision,
    ) -> RequirementEvaluation:
        if not definition.concentrations:
            return self._missing_pool_result(
                requirement, "concentrations", policy_decision
            )
        values: list[ConcentrationProgress] = []
        provenance = []
        lifecycle_reasons: list[ReasonCode] = []
        technical_pool = next(
            (item for item in pools if item.pool_id == definition.technical_pool_id),
            None,
        )
        if technical_pool is not None:
            technical_pool_policy = self.policy.assess(
                technical_pool.approval_status,
                verification_status=technical_pool.verification_status,
                critical=True,
            )
            if not technical_pool_policy.allowed:
                return self._result(
                    requirement,
                    EvaluationOutcome.INDETERMINATE,
                    self._trace(
                        requirement,
                        TraceCode.CONCENTRATION,
                        DecisionStatus.BLOCKED,
                        subject=definition.technical_pool_id.identifier,
                        reasons=technical_pool_policy.reason_codes,
                    ),
                    evidence=ConcentrationRequirementEvidence(()),
                    extra_reasons=technical_pool_policy.reason_codes,
                    force_review=True,
                    policy_decision=policy_decision,
                    extra_provenance=(technical_pool.provenance,)
                    if technical_pool.provenance
                    else (),
                )
        for concentration_id in definition.concentrations:
            concentration = next(
                (
                    item
                    for item in concentrations
                    if item.concentration_id == concentration_id
                ),
                None,
            )
            if concentration is None:
                values.append(
                    ConcentrationProgress(
                        concentration_id,
                        0,
                        definition.minimum_count,
                        0,
                        None,
                        EvaluationOutcome.INDETERMINATE,
                    )
                )
                continue
            concentration_policy = self.policy.assess(
                concentration.approval_status,
                verification_status=concentration.verification_status,
                critical=True,
            )
            if not concentration_policy.allowed:
                lifecycle_reasons.extend(concentration_policy.reason_codes)
                values.append(
                    ConcentrationProgress(
                        concentration_id,
                        0,
                        definition.minimum_count,
                        0,
                        None,
                        EvaluationOutcome.INDETERMINATE,
                    )
                )
                continue
            known = tuple(
                item
                for item in concentration.allowed_courses
                if student.pass_status(item) is FactStatus.KNOWN_TRUE
            )
            unknown = tuple(
                item
                for item in concentration.allowed_courses
                if student.pass_status(item) is FactStatus.UNKNOWN
            )
            potential = len(known) + len(unknown)
            maximum = len(concentration.allowed_courses)
            values.append(
                ConcentrationProgress(
                    concentration_id,
                    len(known),
                    definition.minimum_count,
                    len(unknown),
                    maximum,
                    (
                        EvaluationOutcome.SATISFIED
                        if len(known) >= definition.minimum_count
                        else EvaluationOutcome.INDETERMINATE
                        if potential >= definition.minimum_count
                        else EvaluationOutcome.UNSATISFIED
                    ),
                )
            )
            if concentration.provenance:
                provenance.append(concentration.provenance)
        if any(item.outcome is EvaluationOutcome.SATISFIED for item in values):
            outcome = EvaluationOutcome.SATISFIED
        elif any(item.outcome is EvaluationOutcome.INDETERMINATE for item in values):
            outcome = EvaluationOutcome.INDETERMINATE
        else:
            outcome = EvaluationOutcome.UNSATISFIED
        reasons = (
            tuple(dict.fromkeys((*lifecycle_reasons, ReasonCode.MISSING_REQUIRED_DATA)))
            if outcome is EvaluationOutcome.INDETERMINATE
            else ()
        )
        return self._result(
            requirement,
            outcome,
            self._trace(
                requirement,
                TraceCode.CONCENTRATION,
                _trace_status(outcome),
                expected_value=definition.minimum_count,
                actual_value=max(
                    (item.known_passed_count for item in values), default=0
                ),
                reasons=reasons,
            ),
            evidence=ConcentrationRequirementEvidence(tuple(values)),
            extra_reasons=reasons,
            force_review=outcome is EvaluationOutcome.INDETERMINATE,
            policy_decision=policy_decision,
            extra_provenance=tuple(provenance),
        )

    def _evaluate_slot_requirement(
        self,
        requirement: ProgramRequirement,
        student: StudentState,
        definition: ElectiveSlotRequirement,
        pools: tuple[ElectivePool, ...],
        allocated_course,
        slot_outcome: EvaluationOutcome | None,
        policy_decision,
    ) -> RequirementEvaluation:
        evidence = SlotRequirementEvidence(
            definition.slot_id,
            definition.pool_id,
            allocated_course,
        )
        pool = (
            next((item for item in pools if item.pool_id == definition.pool_id), None)
            if definition.pool_id is not None
            else None
        )
        pool_policy = (
            self.policy.assess(
                pool.approval_status,
                verification_status=pool.verification_status,
                critical=True,
            )
            if pool is not None
            else None
        )
        if (
            definition.pool_id is not None
            and pool is not None
            and not pool_policy.allowed
        ):
            outcome = EvaluationOutcome.INDETERMINATE
            reasons = pool_policy.reason_codes
        elif definition.pool_id is None:
            outcome = EvaluationOutcome.INDETERMINATE
            reasons = (ReasonCode.MISSING_REQUIRED_DATA,)
        elif pool is None:
            outcome = EvaluationOutcome.INDETERMINATE
            reasons = (ReasonCode.MISSING_REQUIRED_DATA,)
        elif slot_outcome is not None:
            outcome = slot_outcome
            reasons = (
                (ReasonCode.MISSING_REQUIRED_DATA,)
                if outcome is EvaluationOutcome.INDETERMINATE
                else ()
            )
        else:
            candidates = tuple(
                item
                for item in pool.allowed_courses
                if student.pass_status(item) is FactStatus.KNOWN_TRUE
            )
            unknown = tuple(
                item
                for item in pool.allowed_courses
                if student.pass_status(item) is FactStatus.UNKNOWN
            )
            outcome = (
                EvaluationOutcome.SATISFIED
                if candidates
                else EvaluationOutcome.INDETERMINATE
                if unknown
                else EvaluationOutcome.UNSATISFIED
            )
            reasons = (
                (ReasonCode.MISSING_REQUIRED_DATA,)
                if outcome is EvaluationOutcome.INDETERMINATE
                else ()
            )
        return self._result(
            requirement,
            outcome,
            self._trace(
                requirement,
                TraceCode.ELECTIVE_SLOT,
                _trace_status(outcome),
                subject=definition.slot_id.identifier,
                actual_value=(allocated_course.course_id if allocated_course else None),
                reasons=reasons,
            ),
            evidence=evidence,
            extra_reasons=reasons,
            force_review=outcome is EvaluationOutcome.INDETERMINATE,
            policy_decision=policy_decision,
            extra_provenance=(pool.provenance,) if pool and pool.provenance else (),
        )

    def _evaluate_field_training(
        self,
        requirement: ProgramRequirement,
        definition: FieldTrainingRequirement,
        facts: StudentProgramFacts,
        policy_decision,
    ) -> RequirementEvaluation:
        record = facts.field_training
        if record is None:
            if facts.coverage is ProgramFactCoverage.COMPLETE:
                outcome = EvaluationOutcome.UNSATISFIED
                reasons = ()
            else:
                outcome = EvaluationOutcome.INDETERMINATE
                reasons = (ReasonCode.MISSING_REQUIRED_DATA,)
            progress = FieldTrainingProgress(
                None,
                None,
                definition.minimum_weeks,
                outcome,
            )
        elif record.passed is False:
            outcome = EvaluationOutcome.UNSATISFIED
            reasons = ()
            progress = FieldTrainingProgress(
                record.passed,
                record.completed_weeks,
                definition.minimum_weeks,
                outcome,
            )
        elif record.passed is None or record.completed_weeks is None:
            outcome = EvaluationOutcome.INDETERMINATE
            reasons = (ReasonCode.MISSING_REQUIRED_DATA,)
            progress = FieldTrainingProgress(
                record.passed,
                record.completed_weeks,
                definition.minimum_weeks,
                outcome,
            )
        else:
            outcome = (
                EvaluationOutcome.SATISFIED
                if record.completed_weeks >= definition.minimum_weeks
                else EvaluationOutcome.UNSATISFIED
            )
            reasons = ()
            progress = FieldTrainingProgress(
                record.passed,
                record.completed_weeks,
                definition.minimum_weeks,
                outcome,
            )
        return self._result(
            requirement,
            outcome,
            self._trace(
                requirement,
                TraceCode.FIELD_TRAINING,
                _trace_status(outcome),
                expected_value=definition.minimum_weeks,
                actual_value=record.completed_weeks if record else None,
                reasons=reasons,
            ),
            evidence=FieldTrainingRequirementEvidence(progress),
            extra_reasons=reasons,
            force_review=outcome is EvaluationOutcome.INDETERMINATE,
            policy_decision=policy_decision,
        )

    def _missing_pool_result(self, requirement, subject, policy_decision):
        reasons = (ReasonCode.MISSING_REQUIRED_DATA,)
        return self._result(
            requirement,
            EvaluationOutcome.INDETERMINATE,
            self._trace(
                requirement,
                TraceCode.REQUIREMENT,
                DecisionStatus.INDETERMINATE,
                subject=subject,
                reasons=reasons,
            ),
            evidence=UnsupportedRequirementEvidence(subject),
            extra_reasons=reasons,
            force_review=True,
            policy_decision=policy_decision,
        )

    def _result(
        self,
        requirement: ProgramRequirement,
        outcome: EvaluationOutcome,
        trace: DecisionTrace,
        *,
        evidence,
        extra_reasons: tuple[ReasonCode, ...] = (),
        force_review: bool = False,
        policy_decision,
        extra_provenance=(),
    ) -> RequirementEvaluation:
        reasons = tuple(
            dict.fromkeys(policy_decision.reason_codes + tuple(extra_reasons))
        )
        requires_review = policy_decision.requires_human_review or force_review
        authoritative = (
            policy_decision.authoritative
            and outcome is not EvaluationOutcome.INDETERMINATE
            and not requires_review
        )
        metadata = ResultMetadata(
            dataset_version=self.dataset_version,
            execution_mode=policy_decision.mode,
            authoritative=authoritative,
            approval_status=policy_decision.approval_status,
            verification_status=policy_decision.verification_status,
            reason_codes=reasons,
            provenance=tuple(
                item
                for item in (requirement.provenance, *extra_provenance)
                if item is not None
            ),
            decision_trace=trace,
            requires_human_review=requires_review,
        )
        return RequirementEvaluation(
            requirement_id=requirement.requirement_id,
            definition_type=(
                requirement.definition.definition_type
                if requirement.definition is not None
                else None
            ),
            outcome=outcome,
            metadata=metadata,
            evidence=evidence,
        )

    def _trace(
        self,
        requirement: ProgramRequirement,
        code: TraceCode,
        status: DecisionStatus,
        *,
        subject=None,
        expected_value=None,
        actual_value=None,
        reasons=(),
    ) -> DecisionTrace:
        return DecisionTrace(
            DecisionTraceNode(
                node_id=f"requirement:{requirement.requirement_id}",
                code=code,
                node_type=TraceNodeType.REQUIREMENT_CHECK,
                status=status,
                subject=subject or requirement.requirement_id,
                expected_value=expected_value,
                actual_value=actual_value,
                reason_codes=tuple(reasons),
                provenance=(requirement.provenance,)
                if requirement.provenance is not None
                else (),
            )
        )


def _fact_outcome(status: FactStatus) -> EvaluationOutcome:
    if status is FactStatus.KNOWN_TRUE:
        return EvaluationOutcome.SATISFIED
    if status is FactStatus.KNOWN_FALSE:
        return EvaluationOutcome.UNSATISFIED
    return EvaluationOutcome.INDETERMINATE


def _trace_status(outcome: EvaluationOutcome) -> DecisionStatus:
    if outcome is EvaluationOutcome.SATISFIED:
        return DecisionStatus.SATISFIED
    if outcome is EvaluationOutcome.UNSATISFIED:
        return DecisionStatus.FAILED
    return DecisionStatus.INDETERMINATE
