from __future__ import annotations

import ast
import json

import pytest

from backend.app.planning.audit.service import DegreeAuditService
from backend.app.planning.builders.student_state_builder import (
    StudentStateBuildInput,
    StudentStateBuilder,
)
from backend.app.planning.candidates.service import CandidateGenerator
from backend.app.planning.domain.academic_state import (
    AcademicHistoryCoverage,
    RegistrationCoverage,
)
from backend.app.planning.domain.audit import DegreeAuditRequest
from backend.app.planning.domain.candidates import (
    CandidateGenerationContext,
    CandidateGenerationRequest,
    CandidateGenerationStatus,
    CandidateSourceCoverage,
)
from backend.app.planning.domain.context import EvaluationHorizon
from backend.app.planning.domain.course import (
    Course,
    CourseIdentity,
    Program,
    Regulation,
)
from backend.app.planning.domain.eligibility import (
    CourseEligibilityRuleSet,
    EligibilityContext,
    EligibilityDecision,
    EligibilityRequest,
    RuleSetStatus,
)
from backend.app.planning.domain.electives import (
    Concentration,
    ConcentrationId,
    ElectivePool,
    ElectivePoolId,
    ElectivePoolType,
)
from backend.app.planning.domain.evaluation import EvaluationOutcome
from backend.app.planning.domain.expressions import (
    CourseConcurrentExpression,
    CoursePassedExpression,
    OrExpression,
)
from backend.app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from backend.app.planning.domain.multi_semester import (
    MultiSemesterPlanStatus,
    MultiSemesterPlanningRequest,
)
from backend.app.planning.domain.planning import (
    PlanningCoverageStatus,
    PlanningSearchPolicy,
    SingleSemesterPlanningRequest,
)
from backend.app.planning.domain.program_facts import (
    FieldTrainingRecord,
    ProgramFactCoverage,
    StudentProgramFacts,
)
from backend.app.planning.domain.requirements import (
    ConcentrationRequirement,
    CourseCompletionRequirement,
    CourseCountFromPoolRequirement,
    EarnedCreditThresholdRequirement,
    FieldTrainingRequirement,
    ProgramRequirement,
    ProgramRequirementSet,
    RequirementSetStatus,
    RequirementStage,
    TotalProgramCreditsRequirement,
    ZeroCreditCourseRequirement,
)
from backend.app.planning.domain.rules import AcademicRule
from backend.app.planning.domain.scenario import (
    CourseOutcomeScenario,
    WhatIfPlanningRequest,
)
from backend.app.planning.domain.semester import (
    SemesterLoadPolicy,
    TermType,
)
from backend.app.planning.domain.student import StudentState
from backend.app.planning.domain.student_history import (
    AttemptOutcome,
    AttemptPurpose,
    CourseAttempt,
)
from backend.app.planning.domain.uel import (
    UELMapping,
    UELMappingSet,
    UELModuleId,
    UELModuleResult,
    UELModuleStatus,
    UELProgressCoverage,
    UELStudentProgress,
)
from backend.app.planning.domain.version import DatasetVersion
from backend.app.planning.engine import PlanningEngine
from backend.app.planning.eligibility.service import EligibilityService
from backend.app.planning.multi_semester.service import MultiSemesterPlanner
from backend.app.planning.planner.service import SingleSemesterPlanner
from backend.app.planning.policy import ExecutionPolicy
from backend.app.planning.ranking.service import PriorityRankingService
from backend.app.planning.rules.evaluator import RuleEvaluator
from backend.app.planning.scenario.service import WhatIfEvaluationService
from backend.app.planning.semester.service import SemesterValidator
from backend.app.planning.uel.service import UELProgressService


R23 = Regulation.R23
CAIE = Program("CAIE")
VERSION = DatasetVersion("planning-v1-hardening")


def cid(code: str) -> CourseIdentity:
    return CourseIdentity(R23, CAIE, code)


def course(code: str, credits: int | float = 3) -> Course:
    return Course(
        cid(code),
        code,
        credits,
        ApprovalStatus.APPROVED,
        VerificationStatus.SOURCE_VERIFIED,
    )


def student(
    *,
    passed: tuple[CourseIdentity, ...] = (),
    current: tuple[CourseIdentity, ...] = (),
    failed: tuple[CourseIdentity, ...] = (),
    earned: int | float | None = 0,
    gpa: int | float | None = 3.0,
    history: AcademicHistoryCoverage = AcademicHistoryCoverage.COMPLETE,
    registrations: RegistrationCoverage = RegistrationCoverage.COMPLETE,
) -> StudentState:
    return StudentState(
        "v1-hardening-student",
        R23,
        CAIE,
        earned_credit_hours=earned,
        passed_courses=frozenset(passed),
        completed_courses=frozenset(passed),
        current_courses=frozenset(current),
        failed_courses=frozenset(failed),
        gpa=gpa,
        history_coverage=history,
        registration_coverage=registrations,
    )


def build_attempt_state(
    attempts: tuple[CourseAttempt, ...],
    *,
    history: AcademicHistoryCoverage = AcademicHistoryCoverage.COMPLETE,
) -> StudentState:
    result = StudentStateBuilder().build(
        StudentStateBuildInput(
            student_id="v1-history-student",
            regulation=R23,
            program=CAIE,
            course_attempts=attempts,
            history_coverage=history,
            registration_coverage=RegistrationCoverage.COMPLETE,
        )
    )
    assert result.student_state is not None, result.diagnostics
    return result.student_state


def attempt(
    identity: CourseIdentity,
    number: int,
    outcome: AttemptOutcome,
    *,
    purpose: AttemptPurpose | None = None,
    credits: int | float | None = None,
) -> CourseAttempt:
    return CourseAttempt(
        student_id="v1-history-student",
        course=identity,
        attempt_number=number,
        term="MAIN",
        academic_year=2020 + number,
        status="RECORDED",
        outcome=outcome,
        purpose=purpose,
        credits_earned=credits,
    )


def rule_set(
    identity: CourseIdentity,
    expression=None,
    *,
    status: RuleSetStatus = RuleSetStatus.COMPLETE,
) -> CourseEligibilityRuleSet:
    rules = ()
    if expression is not None:
        rules = (
            AcademicRule(
                rule_id=f"RULE-{identity.course_code}",
                regulation=R23,
                program=CAIE,
                approval_status=ApprovalStatus.APPROVED,
                verification_status=VerificationStatus.SOURCE_VERIFIED,
                expression=expression,
            ),
        )
    return CourseEligibilityRuleSet(identity, status, rules)


def requirement(requirement_id: str, definition) -> ProgramRequirement:
    return ProgramRequirement(
        requirement_id,
        R23,
        CAIE,
        ApprovalStatus.APPROVED,
        VerificationStatus.SOURCE_VERIFIED,
        definition=definition,
    )


def requirement_set(
    requirements: tuple[ProgramRequirement, ...],
    status: RequirementSetStatus = RequirementSetStatus.COMPLETE,
) -> ProgramRequirementSet:
    return ProgramRequirementSet(
        R23,
        CAIE,
        requirements,
        status,
        dataset_version=VERSION,
    )


def load_policy() -> SemesterLoadPolicy:
    return SemesterLoadPolicy.regulation_23(
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )


def services() -> tuple[
    EligibilityService,
    DegreeAuditService,
    SingleSemesterPlanner,
    MultiSemesterPlanner,
]:
    evaluator = RuleEvaluator(ExecutionPolicy.development(), VERSION)
    eligibility = EligibilityService(evaluator)
    audit = DegreeAuditService(ExecutionPolicy.development(), VERSION)
    single = SingleSemesterPlanner(
        CandidateGenerator(eligibility, VERSION),
        PriorityRankingService(VERSION),
        SemesterValidator(eligibility),
    )
    return (
        eligibility,
        audit,
        single,
        MultiSemesterPlanner(single, degree_audit_service=audit),
    )


def candidate_request(
    state: StudentState,
    courses: tuple[Course, ...],
    requirements: tuple[ProgramRequirement, ...],
    *,
    rule_sets: tuple[CourseEligibilityRuleSet, ...] = (),
    horizon: EvaluationHorizon = EvaluationHorizon.PROJECTED,
    requirement_status: RequirementSetStatus = RequirementSetStatus.COMPLETE,
) -> CandidateGenerationRequest:
    return CandidateGenerationRequest(
        student=state,
        courses=courses,
        requirement_set=requirement_set(requirements, requirement_status),
        rule_sets=rule_sets,
        context=CandidateGenerationContext(horizon=horizon),
        source_coverage=CandidateSourceCoverage(
            catalog=CandidateGenerationStatus.COMPLETE,
            requirements=CandidateGenerationStatus.COMPLETE,
            eligibility_rules=CandidateGenerationStatus.COMPLETE,
            dependency_graph=CandidateGenerationStatus.COMPLETE,
        ),
    )


def multi_request(
    state: StudentState,
    courses: tuple[Course, ...],
    requirements: tuple[ProgramRequirement, ...],
    *,
    rule_sets: tuple[CourseEligibilityRuleSet, ...] = (),
    max_semesters: int = 3,
    requirement_status: RequirementSetStatus = RequirementSetStatus.COMPLETE,
) -> MultiSemesterPlanningRequest:
    return MultiSemesterPlanningRequest(
        initial_student=state,
        candidate_request=candidate_request(
            state,
            courses,
            requirements,
            rule_sets=rule_sets,
            requirement_status=requirement_status,
        ),
        load_policy=load_policy(),
        max_semesters=max_semesters,
    )


def test_failed_then_passed_golden_flow_preserves_history_and_counts_once() -> None:
    identity = cid("CSE141")
    state = build_attempt_state(
        (
            attempt(identity, 1, AttemptOutcome.FAILED, credits=0),
            attempt(
                identity,
                2,
                AttemptOutcome.PASSED,
                purpose=AttemptPurpose.REPEAT,
                credits=3,
            ),
        )
    )
    eligibility, _, _, _ = services()
    result = eligibility.check(
        EligibilityRequest(
            student=state,
            course=course("CSE242"),
            rule_set=rule_set(cid("CSE242"), CoursePassedExpression(identity)),
            context=EligibilityContext(),
        )
    )

    assert state.pass_status(identity).value == "KNOWN_TRUE"
    assert len(state.attempts_for(identity)) == 2
    assert state.earned_credit_hours == 3
    assert result.decision is EligibilityDecision.ELIGIBLE


def test_improvement_failure_golden_flow_is_effective_without_gpa_replacement() -> None:
    identity = cid("CSE141")
    state = build_attempt_state(
        (
            attempt(identity, 1, AttemptOutcome.PASSED, credits=3),
            attempt(
                identity,
                2,
                AttemptOutcome.FAILED,
                purpose=AttemptPurpose.IMPROVEMENT,
                credits=0,
            ),
        )
    )

    assert state.pass_status(identity).value == "KNOWN_FALSE"
    assert state.effective_course_status(identity).value == "FAILED"
    assert len(state.attempts_for(identity)) == 2
    assert state.gpa is None


def test_partial_history_keeps_failed_evidence_but_is_not_definitive() -> None:
    identity = cid("CSE141")
    state = build_attempt_state(
        (attempt(identity, 1, AttemptOutcome.FAILED),),
        history=AcademicHistoryCoverage.PARTIAL,
    )
    eligibility, _, _, _ = services()
    result = eligibility.check(
        EligibilityRequest(
            student=state,
            course=course("CSE242"),
            rule_set=rule_set(cid("CSE242"), CoursePassedExpression(identity)),
        )
    )

    assert state.has_failed_attempt(identity) is True
    assert state.pass_status(identity).value == "UNKNOWN"
    assert result.decision is EligibilityDecision.HUMAN_REVIEW_REQUIRED


def test_projected_prerequisite_condition_survives_candidate_and_plan() -> None:
    prerequisite = cid("PHM111")
    target = course("PHM112")
    state = student(current=(prerequisite,))
    eligibility, _, single, _ = services()
    request = candidate_request(
        state,
        (target,),
        (requirement("REQ-PHM112", CourseCompletionRequirement(target.identity)),),
        rule_sets=(rule_set(target.identity, CoursePassedExpression(prerequisite)),),
    )
    candidates = CandidateGenerator(eligibility, VERSION).generate(request)
    plan = single.plan(
        __import__(
            "backend.app.planning.domain.planning",
            fromlist=["SingleSemesterPlanningRequest"],
        ).SingleSemesterPlanningRequest(
            student=state,
            term_type=TermType.MAIN,
            load_policy=load_policy(),
            candidate_request=request,
        )
    )

    assert (
        candidates.conditional_candidates[0].eligibility.conditions[0].course
        == prerequisite
    )
    assert plan.conditions[0].course == prerequisite
    assert plan.status.value == "CONDITIONAL"


def test_concurrent_fixture_requires_target_aware_same_term_context() -> None:
    prerequisite = course("CSE392")
    target = course("CSE493")
    expression = OrExpression(
        (
            CoursePassedExpression(prerequisite.identity),
            CourseConcurrentExpression(prerequisite.identity),
        )
    )
    eligibility, _, _, _ = services()
    rule = rule_set(target.identity, expression)
    state = student()
    same_term = eligibility.check(
        EligibilityRequest(
            student=state,
            course=target,
            rule_set=rule,
            context=EligibilityContext(
                proposed_term=__import__(
                    "backend.app.planning.domain.context",
                    fromlist=["ProposedTermContext"],
                ).ProposedTermContext(
                    target_course=target.identity,
                    proposed_courses=(prerequisite.identity, target.identity),
                )
            ),
        )
    )
    alone = eligibility.check(
        EligibilityRequest(
            student=state,
            course=target,
            rule_set=rule,
            context=EligibilityContext(
                proposed_term=__import__(
                    "backend.app.planning.domain.context",
                    fromlist=["ProposedTermContext"],
                ).ProposedTermContext(
                    target_course=target.identity, proposed_courses=(target.identity,)
                )
            ),
        )
    )

    assert same_term.decision is EligibilityDecision.ELIGIBLE
    assert alone.decision is EligibilityDecision.INELIGIBLE


def test_stage_separation_keeps_101_gate_out_of_144_completion_audit() -> None:
    gate = requirement(
        "GATE-101",
        EarnedCreditThresholdRequirement(101, RequirementStage.REGISTRATION_GATE),
    )
    total = requirement(
        "TOTAL-144",
        TotalProgramCreditsRequirement(144, RequirementStage.PROGRAM_COMPLETION),
    )
    _, audit, _, _ = services()
    state = student(earned=101)
    result = audit.audit(
        __import__(
            "backend.app.planning.domain.audit", fromlist=["DegreeAuditRequest"]
        ).DegreeAuditRequest(
            student=state,
            requirement_set=requirement_set((gate, total)),
        )
    )
    total_result = next(
        item
        for item in result.requirement_results
        if item.requirement_id == "TOTAL-144"
    )
    gate_audit = audit.audit(
        __import__(
            "backend.app.planning.domain.audit", fromlist=["DegreeAuditRequest"]
        ).DegreeAuditRequest(
            student=state,
            requirement_set=requirement_set((gate, total)),
            stage=RequirementStage.REGISTRATION_GATE,
        )
    )
    gate_result = next(
        item
        for item in gate_audit.requirement_results
        if item.requirement_id == "GATE-101"
    )

    assert gate_result.outcome is EvaluationOutcome.SATISFIED
    assert total_result.outcome is EvaluationOutcome.UNSATISFIED
    assert [item.requirement_id for item in result.requirement_results] == ["TOTAL-144"]


def test_technical_elective_and_concentration_golden_fixture() -> None:
    pool_id = ElectivePoolId(R23, CAIE, "TECHNICAL")
    concentration_id = ConcentrationId(R23, CAIE, "DATA_SCIENCE")
    passed = tuple(cid(f"CSE{300 + index}") for index in range(1, 8))
    pool = ElectivePool(
        pool_id=pool_id,
        pool_name="Technical",
        pool_type=ElectivePoolType.PROGRAM_TECHNICAL_ELECTIVES,
        allowed_courses=passed,
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    concentration = Concentration(
        concentration_id,
        "Data Science",
        passed[:5],
        ApprovalStatus.APPROVED,
        VerificationStatus.SOURCE_VERIFIED,
    )
    requirements = (
        requirement(
            "TECH-7",
            CourseCountFromPoolRequirement(pool_id, 7, course_credit_hours=3),
        ),
        requirement(
            "CONC-5",
            ConcentrationRequirement(pool_id, 5, (concentration_id,)),
        ),
    )
    _, audit, _, _ = services()
    result = audit.audit(
        __import__(
            "backend.app.planning.domain.audit", fromlist=["DegreeAuditRequest"]
        ).DegreeAuditRequest(
            student=student(passed=passed, earned=21),
            requirement_set=requirement_set(requirements),
            pools=(pool,),
            concentrations=(concentration,),
        )
    )

    assert result.status.value == "ACADEMIC_REQUIREMENTS_SATISFIED"
    assert all(
        item.outcome is EvaluationOutcome.SATISFIED
        for item in result.requirement_results
    )


def test_zero_credit_and_field_training_require_explicit_facts() -> None:
    zero = cid("ASUx11")
    zero_requirement = requirement("ZERO-ASUX11", ZeroCreditCourseRequirement(zero))
    training_requirement = requirement("FIELD-8", FieldTrainingRequirement(8))
    _, audit, _, _ = services()
    missing = audit.audit(
        __import__(
            "backend.app.planning.domain.audit", fromlist=["DegreeAuditRequest"]
        ).DegreeAuditRequest(
            student=student(earned=144),
            requirement_set=requirement_set((zero_requirement, training_requirement)),
            program_facts=StudentProgramFacts(coverage=ProgramFactCoverage.UNAVAILABLE),
        )
    )
    complete = audit.audit(
        __import__(
            "backend.app.planning.domain.audit", fromlist=["DegreeAuditRequest"]
        ).DegreeAuditRequest(
            student=student(passed=(zero,), earned=144),
            requirement_set=requirement_set((zero_requirement, training_requirement)),
            program_facts=StudentProgramFacts(
                coverage=ProgramFactCoverage.COMPLETE,
                field_training=FieldTrainingRecord(True, 8),
            ),
        )
    )

    assert missing.status.value == "ACADEMIC_REQUIREMENTS_NOT_SATISFIED"
    field_result = next(
        item for item in missing.requirement_results if item.requirement_id == "FIELD-8"
    )
    assert field_result.outcome is EvaluationOutcome.INDETERMINATE
    assert complete.status.value == "ACADEMIC_REQUIREMENTS_SATISFIED"
    assert complete.progress.earned_credit_hours == 144


@pytest.mark.parametrize(
    ("term", "gpa", "credit_cap", "course_cap"),
    [
        (TermType.MAIN, 3.0, 21, 8),
        (TermType.MAIN, 2.999, 18, 7),
        (TermType.MAIN, 2.0, 18, 7),
        (TermType.MAIN, 1.999, 14, 5),
        (TermType.SUMMER, 3.0, 9, 3),
        (TermType.SUMMER, 2.999, 8, 2),
    ],
)
def test_reg23_load_policy_boundaries_are_explicit(
    term: TermType,
    gpa: float,
    credit_cap: int,
    course_cap: int,
) -> None:
    policy = load_policy()
    band = policy.band_for(term, gpa)

    assert band is not None
    assert band.max_credit_hours == credit_cap
    assert band.max_course_count == course_cap
    assert band.allows(credit_cap + 1, course_cap)
    assert band.allows(credit_cap, course_cap + 1)
    assert not band.allows(credit_cap + 1, course_cap + 1)


def test_uel_independence_preserves_asu_truth_and_priority_evidence() -> None:
    module = UELModuleId.parse("R23:UEL:CN3308")
    identity = cid("PHM112")
    mapping = UELMapping(
        "MAP-CN3308-PHM112",
        module,
        identity,
        "WEIGHTED_COMPONENT",
        60,
    )
    evaluation = UELProgressService(VERSION).evaluate(
        student=student(passed=(identity,)),
        progress=UELStudentProgress(
            module_results=(UELModuleResult(module, UELModuleStatus.FAILED),),
            known_modules=(module,),
            coverage=UELProgressCoverage.COMPLETE,
        ),
        mappings=UELMappingSet((mapping,), UELProgressCoverage.COMPLETE),
    )

    assert student(passed=(identity,)).pass_status(identity).value == "KNOWN_TRUE"
    assert evaluation.progress.failed_modules == (module,)
    assert evaluation.risks[0].mapped_courses == (identity,)


def test_multi_semester_chain_reaudits_and_regenerates_candidates() -> None:
    first, second, third = course("CSE341"), course("CSE342"), course("CSE343")
    state = student()
    _, _, _, multi = services()
    result = multi.plan(
        multi_request(
            state,
            (first, second, third),
            (
                requirement("REQ-A", CourseCompletionRequirement(first.identity)),
                requirement("REQ-B", CourseCompletionRequirement(second.identity)),
                requirement("REQ-C", CourseCompletionRequirement(third.identity)),
            ),
            rule_sets=(
                rule_set(first.identity),
                rule_set(second.identity, CoursePassedExpression(first.identity)),
                rule_set(third.identity, CoursePassedExpression(second.identity)),
            ),
        )
    )

    assert result.status is MultiSemesterPlanStatus.COMPLETION_PATH_FOUND
    assert [step.plan.selected_courses[0].identity for step in result.steps] == [
        first.identity,
        second.identity,
        third.identity,
    ]
    assert result.initial_state.pass_status(first.identity).value == "KNOWN_FALSE"


def test_what_if_failure_changes_path_without_mutating_baseline_state() -> None:
    first, second = course("CSE341"), course("CSE342")
    state = student()
    _, _, _, multi = services()
    baseline_request = multi_request(
        state,
        (first, second),
        (
            requirement("REQ-A", CourseCompletionRequirement(first.identity)),
            requirement("REQ-B", CourseCompletionRequirement(second.identity)),
        ),
        rule_sets=(
            rule_set(first.identity),
            rule_set(second.identity, CoursePassedExpression(first.identity)),
        ),
    )
    result = WhatIfEvaluationService(multi).evaluate(
        WhatIfPlanningRequest(
            baseline=baseline_request,
            scenarios=(CourseOutcomeScenario(first.identity, AttemptOutcome.FAILED),),
        )
    )

    assert state.pass_status(first.identity).value == "KNOWN_FALSE"
    assert result.baseline.final_state.pass_status(first.identity).value == "KNOWN_TRUE"
    assert result.scenario.final_state.pass_status(first.identity).value != "KNOWN_TRUE"
    assert result.delta.removed_courses or result.delta.newly_blocking_requirements


def test_incomplete_requirement_set_never_claims_full_success() -> None:
    identity = cid("CSE341")
    _, audit, _, _ = services()
    result = audit.audit(
        __import__(
            "backend.app.planning.domain.audit", fromlist=["DegreeAuditRequest"]
        ).DegreeAuditRequest(
            student=student(passed=(identity,)),
            requirement_set=requirement_set(
                (requirement("REQ-A", CourseCompletionRequirement(identity)),),
                RequirementSetStatus.INCOMPLETE,
            ),
        )
    )

    assert result.requirement_results[0].outcome is EvaluationOutcome.SATISFIED
    assert result.status.value == "HUMAN_REVIEW_REQUIRED"
    assert result.metadata.authoritative is False


def test_facade_exposes_program_progress_and_stable_json_contracts() -> None:
    identity = cid("CSE341")
    _, audit, single, multi = services()
    request = __import__(
        "backend.app.planning.domain.audit", fromlist=["DegreeAuditRequest"]
    ).DegreeAuditRequest(
        student=student(passed=(identity,)),
        requirement_set=requirement_set(
            (requirement("REQ-A", CourseCompletionRequirement(identity)),)
        ),
    )
    engine = PlanningEngine(
        eligibility_service=single.semester_validator.eligibility_service,
        degree_audit_service=audit,
        single_semester_planner=single,
        multi_semester_planner=multi,
    )
    audit_result = engine.audit(request)
    progress = engine.program_progress(request)

    assert progress.to_dict() == audit_result.progress.to_dict()
    payload = audit_result.to_dict()
    assert json.dumps(payload, sort_keys=True) == json.dumps(
        audit_result.to_dict(), sort_keys=True
    )
    assert not any(
        key.lower() in {"prompt", "chat", "llm", "confidence"} for key in payload
    )


def test_facade_end_to_end_chain_delegates_typed_operations() -> None:
    first, second = course("CSE341"), course("CSE342")
    state = student()
    eligibility, audit, single, multi = services()
    candidate_input = candidate_request(
        state,
        (first, second),
        (
            requirement("REQ-A", CourseCompletionRequirement(first.identity)),
            requirement("REQ-B", CourseCompletionRequirement(second.identity)),
        ),
        rule_sets=(
            rule_set(first.identity),
            rule_set(second.identity, CoursePassedExpression(first.identity)),
        ),
    )
    audit_input = DegreeAuditRequest(
        student=state,
        requirement_set=candidate_input.requirement_set,
    )
    multi_input = multi_request(
        state,
        (first, second),
        (
            requirement("REQ-A", CourseCompletionRequirement(first.identity)),
            requirement("REQ-B", CourseCompletionRequirement(second.identity)),
        ),
        rule_sets=candidate_input.rule_sets,
    )
    engine = PlanningEngine(
        eligibility_service=eligibility,
        degree_audit_service=audit,
        semester_validator=single.semester_validator,
        candidate_generator=single.candidate_generator,
        priority_ranker=single.priority_ranker,
        single_semester_planner=single,
        multi_semester_planner=multi,
        what_if_service=WhatIfEvaluationService(multi),
    )

    audit_result = engine.audit(audit_input)
    candidates = engine.generate_candidates(candidate_input)
    ranking = engine.rank_candidates(candidates)
    eligibility_result = engine.check_eligibility(
        EligibilityRequest(
            student=state,
            course=first,
            rule_set=rule_set(first.identity),
        )
    )
    semester_plan = engine.plan_semester(
        SingleSemesterPlanningRequest(
            student=state,
            term_type=TermType.MAIN,
            load_policy=load_policy(),
            candidate_request=candidate_input,
        )
    )
    multi_plan = engine.plan_multi_semester(multi_input)
    what_if = engine.evaluate_what_if(
        WhatIfPlanningRequest(
            baseline=multi_input,
            scenarios=(CourseOutcomeScenario(first.identity, AttemptOutcome.FAILED),),
        )
    )

    assert audit_result.requirement_results
    assert candidates.available_candidates
    assert ranking.items
    assert eligibility_result.decision is EligibilityDecision.ELIGIBLE
    assert semester_plan.selected_courses
    assert multi_plan.steps
    assert what_if.delta.removed_courses or what_if.delta.newly_blocking_requirements
    assert json.dumps(multi_plan.to_dict(), sort_keys=True) == json.dumps(
        multi_plan.to_dict(), sort_keys=True
    )


def test_search_limit_is_disclosed_and_deterministic() -> None:
    courses = tuple(course(f"CSE{340 + index}") for index in range(5))
    requirements = tuple(
        requirement(f"REQ-{index}", CourseCompletionRequirement(item.identity))
        for index, item in enumerate(courses)
    )
    _, _, single, _ = services()
    request = __import__(
        "backend.app.planning.domain.planning",
        fromlist=["SingleSemesterPlanningRequest"],
    ).SingleSemesterPlanningRequest(
        student=student(),
        term_type=TermType.MAIN,
        load_policy=load_policy(),
        candidate_request=candidate_request(
            student(),
            courses,
            requirements,
            rule_sets=tuple(rule_set(item.identity) for item in courses),
        ),
        search_policy=PlanningSearchPolicy(
            max_candidates_considered=2,
            max_combinations_evaluated=1,
            max_alternatives=0,
        ),
    )
    first = single.plan(request)
    second = single.plan(request)

    assert first.to_dict() == second.to_dict()
    assert first.coverage.search is PlanningCoverageStatus.INCOMPLETE
    assert any(item.code.value == "SEARCH_LIMIT_REACHED" for item in first.diagnostics)


def test_planning_modules_have_no_framework_or_llm_imports() -> None:
    forbidden = {"fastapi", "sqlalchemy", "openai", "langchain", "rag"}
    root = __import__("pathlib").Path("backend/app/planning")
    violations: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [item.name.lower() for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").lower()]
            else:
                continue
            if any(
                any(
                    item == value or item.startswith(f"{value}.") for value in forbidden
                )
                for item in names
            ):
                violations.append(str(path))

    assert violations == []
