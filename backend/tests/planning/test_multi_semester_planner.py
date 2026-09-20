from __future__ import annotations

from app.planning.candidates.service import CandidateGenerator
from app.planning.domain.academic_state import (
    AcademicHistoryCoverage,
    RegistrationCoverage,
)
from app.planning.domain.candidates import (
    CandidateGenerationContext,
    CandidateGenerationRequest,
    CandidateGenerationStatus,
    CandidateSourceCoverage,
)
from app.planning.domain.context import EvaluationHorizon
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
from app.planning.domain.expressions import CoursePassedExpression
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.domain.multi_semester import (
    MultiSemesterPlanStatus,
    MultiSemesterPlanningRequest,
)
from app.planning.domain.requirements import (
    CourseCompletionRequirement,
    ProgramRequirement,
    ProgramRequirementSet,
    RequirementSetStatus,
)
from app.planning.domain.rules import AcademicRule
from app.planning.domain.semester import LoadBand, SemesterLoadPolicy
from app.planning.domain.student import StudentState
from app.planning.domain.version import DatasetVersion
from app.planning.eligibility.service import EligibilityService
from app.planning.multi_semester.service import MultiSemesterPlanner
from app.planning.planner.service import SingleSemesterPlanner
from app.planning.policy import ExecutionPolicy
from app.planning.ranking.service import PriorityRankingService
from app.planning.rules.evaluator import RuleEvaluator
from app.planning.semester.service import SemesterValidator


R23 = Regulation.R23
CAIE = Program("CAIE")
VERSION = DatasetVersion("multi-planner-test")


def cid(code: str) -> CourseIdentity:
    return CourseIdentity(R23, CAIE, code)


def course(code: str) -> Course:
    return Course(
        cid(code),
        code,
        3,
        ApprovalStatus.APPROVED,
        VerificationStatus.SOURCE_VERIFIED,
    )


def student(*, passed: tuple[CourseIdentity, ...] = ()) -> StudentState:
    return StudentState(
        "multi-planner-student",
        R23,
        CAIE,
        earned_credit_hours=90,
        passed_courses=frozenset(passed),
        completed_courses=frozenset(passed),
        gpa=3.0,
        history_coverage=AcademicHistoryCoverage.COMPLETE,
        registration_coverage=RegistrationCoverage.COMPLETE,
    )


def requirement(identity: CourseIdentity, number: int) -> ProgramRequirement:
    return ProgramRequirement(
        f"REQ-{number}",
        R23,
        CAIE,
        ApprovalStatus.APPROVED,
        VerificationStatus.SOURCE_VERIFIED,
        definition=CourseCompletionRequirement(identity),
    )


def rule_set(identity: CourseIdentity, expression=None) -> CourseEligibilityRuleSet:
    rules = ()
    if expression is not None:
        rules = (
            AcademicRule(
                rule_id=f"RULE-{identity.course_code}",
                regulation=R23,
                program=CAIE,
                approval_status=ApprovalStatus.APPROVED,
                verification_status=VerificationStatus.SOURCE_VERIFIED,
                critical_for_planner=True,
                expression=expression,
            ),
        )
    return CourseEligibilityRuleSet(identity, RuleSetStatus.COMPLETE, rules)


def planner() -> MultiSemesterPlanner:
    evaluator = RuleEvaluator(ExecutionPolicy.development(), VERSION)
    eligibility = EligibilityService(evaluator)
    single = SingleSemesterPlanner(
        CandidateGenerator(eligibility, VERSION),
        PriorityRankingService(VERSION),
        SemesterValidator(eligibility),
    )
    return MultiSemesterPlanner(single)


def request(
    courses: tuple[Course, ...],
    requirements: tuple[ProgramRequirement, ...],
    *,
    student_value: StudentState | None = None,
    rule_sets: tuple[CourseEligibilityRuleSet, ...] = (),
    max_semesters: int = 3,
) -> MultiSemesterPlanningRequest:
    actual_student = student_value or student()
    candidate_request = CandidateGenerationRequest(
        student=actual_student,
        courses=courses,
        requirement_set=ProgramRequirementSet(
            R23,
            CAIE,
            requirements,
            RequirementSetStatus.COMPLETE,
            dataset_version=VERSION,
        ),
        rule_sets=rule_sets,
        context=CandidateGenerationContext(horizon=EvaluationHorizon.PROJECTED),
        source_coverage=CandidateSourceCoverage(
            catalog=CandidateGenerationStatus.COMPLETE,
            requirements=CandidateGenerationStatus.COMPLETE,
            eligibility_rules=CandidateGenerationStatus.COMPLETE,
            dependency_graph=CandidateGenerationStatus.COMPLETE,
        ),
    )
    load_policy = SemesterLoadPolicy(
        "MULTI-LOAD",
        R23,
        CAIE,
        (LoadBand("MAIN", None, None, 21, 8),),
        (LoadBand("SUMMER", None, None, 21, 8),),
        ApprovalStatus.APPROVED,
        VerificationStatus.SOURCE_VERIFIED,
    )
    return MultiSemesterPlanningRequest(
        initial_student=actual_student,
        candidate_request=candidate_request,
        load_policy=load_policy,
        max_semesters=max_semesters,
    )


def test_one_semester_path_stops_after_modeled_requirements_are_satisfied() -> None:
    target = course("CSE341")
    result = planner().plan(
        request(
            (target,),
            (requirement(target.identity, 1),),
            rule_sets=(rule_set(target.identity),),
        )
    )

    assert result.status is MultiSemesterPlanStatus.COMPLETION_PATH_FOUND
    assert len(result.steps) == 1
    assert result.final_state.pass_status(target.identity).value == "KNOWN_TRUE"


def test_prerequisite_chain_is_replanned_after_projected_pass() -> None:
    first = course("CSE341")
    second = course("CSE342")
    result = planner().plan(
        request(
            (first, second),
            (requirement(first.identity, 1), requirement(second.identity, 2)),
            rule_sets=(
                rule_set(first.identity),
                rule_set(second.identity, CoursePassedExpression(first.identity)),
            ),
        )
    )

    assert result.status is MultiSemesterPlanStatus.COMPLETION_PATH_FOUND
    assert len(result.steps) == 2
    assert result.steps[0].plan.selected_courses[0].identity == first.identity
    assert result.steps[1].plan.selected_courses[0].identity == second.identity


def test_horizon_reached_returns_partial_path_without_mutating_observed_state() -> None:
    first = course("CSE341")
    second = course("CSE342")
    original = student()
    result = planner().plan(
        request(
            (first, second),
            (requirement(first.identity, 1), requirement(second.identity, 2)),
            student_value=original,
            rule_sets=(
                rule_set(first.identity),
                rule_set(second.identity, CoursePassedExpression(first.identity)),
            ),
            max_semesters=1,
        )
    )

    assert result.status is MultiSemesterPlanStatus.PARTIAL_PATH
    assert original.pass_status(first.identity).value == "KNOWN_FALSE"
    assert result.final_state.fact_layer.value == "PROJECTED"


def test_multi_semester_serialization_is_deterministic_and_not_registration_ready() -> (
    None
):
    target = course("CSE341")
    request_value = request(
        (target,),
        (requirement(target.identity, 1),),
        rule_sets=(rule_set(target.identity),),
    )

    first = planner().plan(request_value)
    second = planner().plan(request_value)

    assert first.to_dict() == second.to_dict()
    assert first.coverage.offering.value == "UNAVAILABLE"
    assert first.coverage.timetable.value == "UNAVAILABLE"
    assert first.registration_ready is False
