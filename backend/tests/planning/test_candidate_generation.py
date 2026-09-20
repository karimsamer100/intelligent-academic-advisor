from __future__ import annotations

from app.planning.candidates.service import CandidateGenerator
from app.planning.domain.academic_state import (
    AcademicHistoryCoverage,
    RegistrationCoverage,
)
from app.planning.domain.context import EvaluationHorizon, RegistrationIntent
from app.planning.domain.candidates import (
    CandidateAvailability,
    CandidateGenerationRequest,
    CandidateGenerationStatus,
    CandidateReasonCode,
    CandidateGenerationContext,
    CandidateIntent,
    CandidateSourceCoverage,
)
from app.planning.domain.course import (
    Course,
    CourseIdentity,
    Program,
    Regulation,
)
from app.planning.domain.eligibility import (
    CourseEligibilityRuleSet,
    RuleSetStatus,
)
from app.planning.domain.dependency import (
    DependencyConstraint,
    DependencyCoverageStatus,
    DependencyDefinition,
    DependencyGraph,
    DependencyGraphScope,
    DependencyNode,
    DependencyReference,
    DependencyRelationKind,
)
from app.planning.domain.electives import (
    Concentration,
    ConcentrationId,
    ElectivePool,
    ElectivePoolId,
    ElectivePoolType,
    ElectiveSlotId,
)
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.domain.expressions import CoursePassedExpression
from app.planning.domain.requirements import (
    ConcentrationRequirement,
    CourseCompletionRequirement,
    CourseCountFromPoolRequirement,
    ElectiveSlotRequirement,
    ProgramRequirement,
    ProgramRequirementSet,
    RequirementSetStatus,
    ZeroCreditCourseRequirement,
)
from app.planning.domain.rules import AcademicRule
from app.planning.domain.student import StudentState
from app.planning.domain.version import DatasetVersion
from app.planning.eligibility.service import EligibilityService
from app.planning.policy import ExecutionPolicy
from app.planning.rules.evaluator import RuleEvaluator


R23 = Regulation.R23
CAIE = Program("CAIE")
VERSION = DatasetVersion("candidate-test")


def cid(code: str) -> CourseIdentity:
    return CourseIdentity(R23, CAIE, code)


def course(code: str) -> Course:
    identity = cid(code)
    return Course(
        identity, code, 3, ApprovalStatus.APPROVED, VerificationStatus.SOURCE_VERIFIED
    )


def student(
    *,
    passed: tuple[CourseIdentity, ...] = (),
    current: tuple[CourseIdentity, ...] = (),
    failed: tuple[CourseIdentity, ...] = (),
) -> StudentState:
    return StudentState(
        "candidate-student",
        R23,
        CAIE,
        passed_courses=frozenset(passed),
        current_courses=frozenset(current),
        failed_courses=frozenset(failed),
        history_coverage=AcademicHistoryCoverage.COMPLETE,
        registration_coverage=RegistrationCoverage.COMPLETE,
    )


def requirement(course_id: CourseIdentity, requirement_id: str) -> ProgramRequirement:
    return ProgramRequirement(
        requirement_id=requirement_id,
        regulation=R23,
        program=CAIE,
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        definition=CourseCompletionRequirement(course_id),
    )


def generator() -> CandidateGenerator:
    evaluator = RuleEvaluator(ExecutionPolicy.development(), VERSION)
    return CandidateGenerator(EligibilityService(evaluator), VERSION)


def request(
    courses: tuple[Course, ...],
    requirements: tuple[ProgramRequirement, ...],
    *,
    passed: tuple[CourseIdentity, ...] = (),
    current: tuple[CourseIdentity, ...] = (),
    failed: tuple[CourseIdentity, ...] = (),
    rule_sets: tuple[CourseEligibilityRuleSet, ...] = (),
    context: CandidateGenerationContext | None = None,
    intents: tuple[CandidateIntent, ...] = (),
) -> CandidateGenerationRequest:
    return CandidateGenerationRequest(
        student=student(passed=passed, current=current, failed=failed),
        courses=courses,
        requirement_set=ProgramRequirementSet(
            R23,
            CAIE,
            requirements,
            RequirementSetStatus.COMPLETE,
            dataset_version=VERSION,
        ),
        rule_sets=rule_sets,
        context=context or CandidateGenerationContext(),
        intents=intents,
    )


def test_outstanding_required_course_becomes_available_candidate() -> None:
    target = course("CSE341")
    result = generator().generate(
        request(
            (target,),
            (requirement(target.identity, "REQ-1"),),
            rule_sets=(
                CourseEligibilityRuleSet(target.identity, RuleSetStatus.COMPLETE),
            ),
        )
    )

    assert result.status is CandidateGenerationStatus.INCOMPLETE
    assert result.available_candidates[0].course.identity == target.identity
    assert (
        CandidateReasonCode.REQUIRED_FOR_PROGRAM
        in result.available_candidates[0].reason_codes
    )
    assert (
        result.available_candidates[0].availability is CandidateAvailability.AVAILABLE
    )


def test_satisfied_required_course_is_not_generated() -> None:
    target = course("CSE341")
    result = generator().generate(
        request(
            (target,),
            (requirement(target.identity, "REQ-1"),),
            passed=(target.identity,),
            rule_sets=(
                CourseEligibilityRuleSet(target.identity, RuleSetStatus.COMPLETE),
            ),
        )
    )

    assert result.available_candidates == ()
    assert result.conditional_candidates == ()
    assert result.review_candidates == ()


def test_projected_dependency_candidate_is_conditional() -> None:
    target = course("CSE342")
    prerequisite = course("CSE241")
    result = generator().generate(
        request(
            (target, prerequisite),
            (requirement(target.identity, "REQ-1"),),
            current=(prerequisite.identity,),
            rule_sets=(
                CourseEligibilityRuleSet(
                    target.identity,
                    RuleSetStatus.COMPLETE,
                    rules=(
                        AcademicRule(
                            rule_id="PR-CSE342",
                            regulation=R23,
                            program=CAIE,
                            approval_status=ApprovalStatus.APPROVED,
                            verification_status=VerificationStatus.SOURCE_VERIFIED,
                            expression=CoursePassedExpression(prerequisite.identity),
                        ),
                    ),
                ),
            ),
            context=CandidateGenerationContext(
                horizon=EvaluationHorizon.PROJECTED,
                proposed_courses=(target.identity,),
            ),
        )
    )

    assert result.conditional_candidates[0].course.identity == target.identity
    assert result.conditional_candidates[0].eligibility is not None


def test_missing_rule_set_is_review_candidate_and_coverage_is_incomplete() -> None:
    target = course("CSE341")

    result = generator().generate(
        request((target,), (requirement(target.identity, "REQ-1"),))
    )

    assert result.status is CandidateGenerationStatus.INCOMPLETE
    assert result.review_candidates[0].course.identity == target.identity
    assert result.metadata.authoritative is False


def test_missing_rule_set_for_one_candidate_keeps_rule_coverage_incomplete() -> None:
    first = course("CSE341")
    second = course("CSE342")

    result = generator().generate(
        request(
            (first, second),
            (
                requirement(first.identity, "REQ-1"),
                requirement(second.identity, "REQ-2"),
            ),
            rule_sets=(
                CourseEligibilityRuleSet(first.identity, RuleSetStatus.COMPLETE),
            ),
        )
    )

    assert (
        result.source_coverage.eligibility_rules is CandidateGenerationStatus.INCOMPLETE
    )


def test_explicit_retake_intents_produce_distinct_candidate_reasons() -> None:
    failed = course("CSE341")
    improved = course("CSE342")
    result = generator().generate(
        request(
            (failed, improved),
            (),
            passed=(improved.identity,),
            failed=(failed.identity,),
            rule_sets=(
                CourseEligibilityRuleSet(failed.identity, RuleSetStatus.COMPLETE),
                CourseEligibilityRuleSet(improved.identity, RuleSetStatus.COMPLETE),
            ),
            intents=(
                CandidateIntent(
                    failed.identity, RegistrationIntent.RETAKE_AFTER_FAILURE
                ),
                CandidateIntent(
                    improved.identity, RegistrationIntent.RETAKE_FOR_IMPROVEMENT
                ),
            ),
        )
    )

    by_identity = {item.identity: item for item in result.candidates}
    assert (
        CandidateReasonCode.RETAKE_AFTER_FAILURE
        in by_identity[failed.identity].reason_codes
    )
    assert by_identity[failed.identity].availability is CandidateAvailability.AVAILABLE
    assert (
        CandidateReasonCode.RETAKE_FOR_IMPROVEMENT
        in by_identity[improved.identity].reason_codes
    )
    assert (
        by_identity[improved.identity].availability
        is CandidateAvailability.REVIEW_REQUIRED
    )


def test_zero_credit_requirement_does_not_fabricate_missing_course() -> None:
    missing = cid("ASUx11")
    requirement_value = ProgramRequirement(
        requirement_id="ZERO-1",
        regulation=R23,
        program=CAIE,
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        definition=ZeroCreditCourseRequirement(missing),
    )

    result = generator().generate(request((), (requirement_value,)))

    assert missing not in result.excluded_course_ids
    assert result.available_candidates == ()
    assert result.status is CandidateGenerationStatus.INCOMPLETE


def test_governed_elective_pool_members_become_candidates() -> None:
    first = course("CSE441")
    second = course("CSE442")
    pool_id = ElectivePoolId(R23, CAIE, "TECHNICAL")
    pool = ElectivePool(
        pool_id=pool_id,
        pool_name="Technical",
        pool_type=ElectivePoolType.PROGRAM_TECHNICAL_ELECTIVES,
        allowed_courses=(first.identity, second.identity),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    requirement_value = ProgramRequirement(
        requirement_id="POOL-1",
        regulation=R23,
        program=CAIE,
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        definition=CourseCountFromPoolRequirement(pool_id, 1),
    )
    result = generator().generate(
        CandidateGenerationRequest(
            student=student(),
            courses=(first, second),
            requirement_set=ProgramRequirementSet(
                R23,
                CAIE,
                (requirement_value,),
                RequirementSetStatus.COMPLETE,
                dataset_version=VERSION,
            ),
            rule_sets=(
                CourseEligibilityRuleSet(first.identity, RuleSetStatus.COMPLETE),
                CourseEligibilityRuleSet(second.identity, RuleSetStatus.COMPLETE),
            ),
            pools=(pool,),
        )
    )

    assert {item.identity for item in result.available_candidates} == {
        first.identity,
        second.identity,
    }
    assert all(
        CandidateReasonCode.ELECTIVE_REQUIREMENT in item.reason_codes
        for item in result.available_candidates
    )


def test_unknown_elective_slot_binding_does_not_fabricate_candidates() -> None:
    slot = ElectiveSlotRequirement(slot_id=ElectiveSlotId(R23, CAIE, "ASU_ELECTIVE_1"))
    requirement_value = ProgramRequirement(
        requirement_id="SLOT-1",
        regulation=R23,
        program=CAIE,
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        definition=slot,
    )

    result = generator().generate(request((), (requirement_value,)))

    assert result.available_candidates == ()
    assert result.status is CandidateGenerationStatus.INCOMPLETE


def test_metadata_only_requirement_makes_candidate_coverage_incomplete() -> None:
    requirement_value = ProgramRequirement(
        requirement_id="LEGACY-1",
        regulation=R23,
        program=CAIE,
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        definition=None,
    )

    result = generator().generate(request((), (requirement_value,)))

    assert result.status is CandidateGenerationStatus.INCOMPLETE
    assert result.source_coverage.requirements is CandidateGenerationStatus.INCOMPLETE


def test_concentration_progress_has_a_structured_reason() -> None:
    candidate_course = course("CSE451")
    concentration_id = ConcentrationId(R23, CAIE, "DATA_SCIENCE")
    concentration = Concentration(
        concentration_id=concentration_id,
        name="Data Science",
        allowed_courses=(candidate_course.identity,),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    pool_id = ElectivePoolId(R23, CAIE, "TECHNICAL")
    requirement_value = ProgramRequirement(
        requirement_id="CONC-1",
        regulation=R23,
        program=CAIE,
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        definition=ConcentrationRequirement(pool_id, 5, (concentration_id,)),
    )
    result = generator().generate(
        CandidateGenerationRequest(
            student=student(),
            courses=(candidate_course,),
            requirement_set=ProgramRequirementSet(
                R23,
                CAIE,
                (requirement_value,),
                RequirementSetStatus.COMPLETE,
                dataset_version=VERSION,
            ),
            rule_sets=(
                CourseEligibilityRuleSet(
                    candidate_course.identity, RuleSetStatus.COMPLETE
                ),
            ),
            pools=(),
            concentrations=(concentration,),
        )
    )

    assert (
        CandidateReasonCode.CONCENTRATION_PROGRESS
        in result.available_candidates[0].reason_codes
    )


def test_dependency_reference_is_an_unlock_reason_not_a_requirement_claim() -> None:
    target = course("CSE341")
    prerequisite = course("CSE241")
    constraint = DependencyConstraint(
        target_course=target.identity,
        rule_id="PR-341",
        expression=CoursePassedExpression(prerequisite.identity),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        critical_for_planner=True,
    )
    graph = DependencyGraph(
        scope=DependencyGraphScope(R23, CAIE),
        dataset_version=VERSION,
        nodes=(DependencyNode(target), DependencyNode(prerequisite)),
        definitions=(
            DependencyDefinition(
                target.identity,
                DependencyCoverageStatus.COMPLETE,
                RuleSetStatus.COMPLETE,
                (constraint,),
            ),
        ),
        references=(
            DependencyReference(
                target_course=target.identity,
                dependency=prerequisite.identity,
                rule_id="PR-341",
                relation_kind=DependencyRelationKind.REQUIRED,
                expression_path=(0,),
                traversable=True,
                node_present=True,
                approval_status=ApprovalStatus.APPROVED,
                verification_status=VerificationStatus.SOURCE_VERIFIED,
                critical_for_planner=True,
            ),
        ),
    )
    result = generator().generate(
        CandidateGenerationRequest(
            student=student(),
            courses=(target, prerequisite),
            requirement_set=ProgramRequirementSet(
                R23,
                CAIE,
                (requirement(target.identity, "REQ-1"),),
                RequirementSetStatus.COMPLETE,
                dataset_version=VERSION,
            ),
            rule_sets=(
                CourseEligibilityRuleSet(target.identity, RuleSetStatus.COMPLETE),
                CourseEligibilityRuleSet(prerequisite.identity, RuleSetStatus.COMPLETE),
            ),
            dependency_graph=graph,
        )
    )

    unlocked = next(
        item
        for item in result.available_candidates
        if item.identity == prerequisite.identity
    )
    assert CandidateReasonCode.UNLOCKS_REQUIRED_COURSE in unlocked.reason_codes
    assert CandidateReasonCode.REQUIRED_FOR_PROGRAM not in unlocked.reason_codes


def test_incomplete_dependency_definition_preserves_dependency_coverage_gap() -> None:
    target = course("CSE341")
    prerequisite = course("CSE241")
    constraint = DependencyConstraint(
        target_course=target.identity,
        rule_id="PR-341",
        expression=CoursePassedExpression(prerequisite.identity),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        critical_for_planner=True,
    )
    graph = DependencyGraph(
        scope=DependencyGraphScope(R23, CAIE),
        dataset_version=VERSION,
        nodes=(DependencyNode(target), DependencyNode(prerequisite)),
        definitions=(
            DependencyDefinition(
                target.identity,
                DependencyCoverageStatus.INCOMPLETE,
                RuleSetStatus.COMPLETE,
                (constraint,),
            ),
        ),
        references=(),
    )

    result = generator().generate(
        CandidateGenerationRequest(
            student=student(),
            courses=(target, prerequisite),
            dependency_graph=graph,
            source_coverage=CandidateSourceCoverage(
                catalog=CandidateGenerationStatus.COMPLETE,
                requirements=CandidateGenerationStatus.COMPLETE,
                eligibility_rules=CandidateGenerationStatus.COMPLETE,
                dependency_graph=CandidateGenerationStatus.COMPLETE,
            ),
        )
    )

    assert (
        result.source_coverage.dependency_graph is CandidateGenerationStatus.INCOMPLETE
    )
