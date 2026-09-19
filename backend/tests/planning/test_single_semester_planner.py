from __future__ import annotations

from backend.app.planning.candidates.service import CandidateGenerator
from backend.app.planning.domain.academic_state import (
    AcademicHistoryCoverage,
    RegistrationCoverage,
)
from backend.app.planning.domain.candidates import (
    CandidateGenerationContext,
    CandidateGenerationRequest,
    CandidateGenerationStatus,
    CandidateIntent,
    CandidateSourceCoverage,
)
from backend.app.planning.domain.context import EvaluationHorizon, RegistrationIntent
from backend.app.planning.domain.course import (
    Course,
    CourseIdentity,
    Program,
    Regulation,
)
from backend.app.planning.domain.eligibility import (
    CourseEligibilityRuleSet,
    RuleSetStatus,
)
from backend.app.planning.domain.expressions import (
    CourseConcurrentExpression,
    CoursePassedExpression,
    OrExpression,
)
from backend.app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from backend.app.planning.domain.requirements import (
    CourseCompletionRequirement,
    ProgramRequirement,
    ProgramRequirementSet,
    RequirementSetStatus,
)
from backend.app.planning.domain.rules import AcademicRule
from backend.app.planning.domain.semester import (
    LoadBand,
    SemesterLoadPolicy,
    TermType,
)
from backend.app.planning.domain.student import StudentState
from backend.app.planning.domain.version import DatasetVersion
from backend.app.planning.eligibility.service import EligibilityService
from backend.app.planning.policy import ExecutionPolicy
from backend.app.planning.planner.service import SingleSemesterPlanner
from backend.app.planning.ranking.service import PriorityRankingService
from backend.app.planning.semester.service import SemesterValidator
from backend.app.planning.rules.evaluator import RuleEvaluator
from backend.app.planning.domain.planning import (
    LoadPreference,
    PlanAlternativeType,
    PlanExclusionCode,
    PlanStatus,
    PlanningCoverageStatus,
    PlanningPreferences,
    PlanningSearchPolicy,
    SingleSemesterPlanningRequest,
)


R23 = Regulation.R23
CAIE = Program("CAIE")
VERSION = DatasetVersion("planner-test")


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
    gpa: float | None = 3.0,
) -> StudentState:
    return StudentState(
        "planner-student",
        R23,
        CAIE,
        passed_courses=frozenset(passed),
        current_courses=frozenset(current),
        failed_courses=frozenset(failed),
        gpa=gpa,
        history_coverage=AcademicHistoryCoverage.COMPLETE,
        registration_coverage=RegistrationCoverage.COMPLETE,
    )


def requirement(target: CourseIdentity, requirement_id: str) -> ProgramRequirement:
    return ProgramRequirement(
        requirement_id=requirement_id,
        regulation=R23,
        program=CAIE,
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        definition=CourseCompletionRequirement(target),
    )


def rule_set(
    target: CourseIdentity,
    expression=None,
    *,
    status: RuleSetStatus = RuleSetStatus.COMPLETE,
) -> CourseEligibilityRuleSet:
    rules = ()
    if expression is not None:
        from backend.app.planning.domain.rules import AcademicRule

        rules = (
            AcademicRule(
                rule_id=f"PR-{target.course_code}",
                regulation=R23,
                program=CAIE,
                approval_status=ApprovalStatus.APPROVED,
                verification_status=VerificationStatus.SOURCE_VERIFIED,
                critical_for_planner=True,
                expression=expression,
            ),
        )
    return CourseEligibilityRuleSet(target, status, rules)


def load_policy(max_credits: int | float = 21, max_courses: int = 8):
    return SemesterLoadPolicy(
        policy_id="PLANNER_LOAD_POLICY",
        regulation=R23,
        program=CAIE,
        main_bands=(LoadBand("MAIN", None, None, max_credits, max_courses),),
        summer_bands=(LoadBand("SUMMER", None, None, max_credits, max_courses),),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )


def planner() -> SingleSemesterPlanner:
    evaluator = RuleEvaluator(ExecutionPolicy.development(), VERSION)
    eligibility = EligibilityService(evaluator)
    return SingleSemesterPlanner(
        CandidateGenerator(eligibility, VERSION),
        PriorityRankingService(VERSION),
        SemesterValidator(eligibility),
    )


def request(
    courses: tuple[Course, ...],
    requirements: tuple[ProgramRequirement, ...],
    *,
    student_value: StudentState | None = None,
    rule_sets: tuple[CourseEligibilityRuleSet, ...] = (),
    horizon: EvaluationHorizon = EvaluationHorizon.CURRENT,
    preferences: PlanningPreferences | None = None,
    policy: SemesterLoadPolicy | None = None,
    source_coverage: CandidateSourceCoverage | None = None,
    search_policy: PlanningSearchPolicy | None = None,
    intents: tuple[CandidateIntent, ...] = (),
) -> SingleSemesterPlanningRequest:
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
        intents=intents,
        context=CandidateGenerationContext(horizon=horizon),
        source_coverage=source_coverage
        or CandidateSourceCoverage(
            catalog=CandidateGenerationStatus.COMPLETE,
            requirements=CandidateGenerationStatus.COMPLETE,
            eligibility_rules=CandidateGenerationStatus.COMPLETE,
            dependency_graph=CandidateGenerationStatus.COMPLETE,
        ),
    )
    return SingleSemesterPlanningRequest(
        student=actual_student,
        term_type=TermType.MAIN,
        load_policy=policy or load_policy(),
        candidate_request=candidate_request,
        preferences=preferences or PlanningPreferences(),
        search_policy=search_policy or PlanningSearchPolicy(),
    )


def test_default_preferences_are_balanced_and_deterministic() -> None:
    assert PlanningPreferences() == PlanningPreferences()
    assert PlanningPreferences().load_preference is LoadPreference.BALANCED
    assert PlanningPreferences().to_dict() == PlanningPreferences().to_dict()


def test_preferred_maximum_is_distinct_from_legal_maximum() -> None:
    preferences = PlanningPreferences(maximum_preferred_credit_hours=15)
    result = planner().plan(
        request(
            (course("CSE341"),),
            (requirement(cid("CSE341"), "REQ-1"),),
            preferences=preferences,
        )
    )

    assert result.preferences.maximum_preferred_credit_hours == 15
    assert result.validation_result is not None
    assert result.validation_result.load_result.max_credit_hours == 21


def test_one_required_eligible_course_is_selected_with_evidence() -> None:
    target = course("CSE341")
    result = planner().plan(
        request(
            (target,),
            (requirement(target.identity, "REQ-1"),),
            rule_sets=(rule_set(target.identity),),
        )
    )

    assert result.selected_courses[0].identity == target.identity
    assert result.selected_courses[0].candidate.requirement_ids == ("REQ-1",)
    assert result.selected_courses[0].priority_factors is not None
    assert result.validation_result is not None


def test_no_candidates_returns_structured_no_feasible_plan() -> None:
    result = planner().plan(request((), ()))

    assert result.status is PlanStatus.NO_FEASIBLE_PLAN
    assert result.selected_courses == ()
    assert result.validation_result is None
    assert result.coverage.candidate_generation is PlanningCoverageStatus.INCOMPLETE


def test_ineligible_candidate_is_excluded() -> None:
    target = course("CSE341")
    prerequisite = cid("CSE241")
    result = planner().plan(
        request(
            (target,),
            (requirement(target.identity, "REQ-1"),),
            rule_sets=(
                rule_set(target.identity, CoursePassedExpression(prerequisite)),
            ),
        )
    )

    assert result.selected_courses == ()
    assert result.status is PlanStatus.NO_FEASIBLE_PLAN
    assert result.exclusions[0].course == target.identity
    assert result.exclusions[0].code is PlanExclusionCode.ACADEMICALLY_INELIGIBLE


def test_two_valid_courses_are_selected_when_load_allows() -> None:
    first = course("CSE341")
    second = course("CSE342")
    result = planner().plan(
        request(
            (first, second),
            (
                requirement(first.identity, "REQ-1"),
                requirement(second.identity, "REQ-2"),
            ),
            rule_sets=(rule_set(first.identity), rule_set(second.identity)),
        )
    )

    assert {item.identity for item in result.selected_courses} == {
        first.identity,
        second.identity,
    }
    assert result.achieved_course_count == 2


def test_planner_search_recovers_from_invalid_greedy_pair() -> None:
    first = course("CSE341", 4)
    second = course("CSE342", 3)
    third = course("CSE343", 3)
    requirements = tuple(
        requirement(item.identity, f"REQ-{index}")
        for index, item in enumerate((first, second, third), start=1)
    )
    result = planner().plan(
        request(
            (first, second, third),
            requirements,
            rule_sets=tuple(rule_set(item.identity) for item in (first, second, third)),
            policy=load_policy(max_credits=6, max_courses=1),
            preferences=PlanningPreferences(target_credit_hours=6),
        )
    )

    assert {item.identity for item in result.selected_courses} == {
        second.identity,
        third.identity,
    }
    assert result.validation_result is not None
    assert result.validation_result.status.value == "VALID"


def test_projected_conditional_candidate_propagates_to_plan() -> None:
    target = course("CSE342")
    prerequisite = cid("CSE241")
    result = planner().plan(
        request(
            (target,),
            (requirement(target.identity, "REQ-1"),),
            student_value=student(current=(prerequisite,)),
            rule_sets=(
                rule_set(target.identity, CoursePassedExpression(prerequisite)),
            ),
            horizon=EvaluationHorizon.PROJECTED,
        )
    )

    assert result.status is PlanStatus.CONDITIONAL
    assert result.conditions
    assert result.selected_courses[0].conditions


def test_current_planning_does_not_use_projected_condition() -> None:
    target = course("CSE342")
    prerequisite = cid("CSE241")
    result = planner().plan(
        request(
            (target,),
            (requirement(target.identity, "REQ-1"),),
            student_value=student(current=(prerequisite,)),
            rule_sets=(
                rule_set(target.identity, CoursePassedExpression(prerequisite)),
            ),
            horizon=EvaluationHorizon.CURRENT,
        )
    )

    assert result.status is PlanStatus.NO_FEASIBLE_PLAN
    assert result.selected_courses == ()


def test_improvement_retake_is_not_selected_when_safe_course_exists() -> None:
    required = course("CSE341")
    improvement = course("CSE342")
    result = planner().plan(
        request(
            (required, improvement),
            (requirement(required.identity, "REQ-1"),),
            student_value=student(passed=(improvement.identity,)),
            rule_sets=(rule_set(required.identity), rule_set(improvement.identity)),
            intents=(
                CandidateIntent(
                    improvement.identity,
                    RegistrationIntent.RETAKE_FOR_IMPROVEMENT,
                ),
            ),
        )
    )

    assert [item.identity for item in result.selected_courses] == [required.identity]


def test_failure_retake_intent_is_preserved_in_selected_plan() -> None:
    target = course("CSE341")
    result = planner().plan(
        request(
            (target,),
            (),
            student_value=student(failed=(target.identity,)),
            rule_sets=(rule_set(target.identity),),
            intents=(
                CandidateIntent(
                    target.identity,
                    RegistrationIntent.RETAKE_AFTER_FAILURE,
                ),
            ),
            preferences=PlanningPreferences(target_credit_hours=3),
        )
    )

    assert result.selected_courses[0].registration_intent is (
        RegistrationIntent.RETAKE_AFTER_FAILURE
    )


def test_review_only_improvement_path_is_not_reported_as_valid() -> None:
    target = course("CSE341")
    result = planner().plan(
        request(
            (target,),
            (),
            student_value=student(passed=(target.identity,)),
            rule_sets=(rule_set(target.identity),),
            intents=(
                CandidateIntent(
                    target.identity,
                    RegistrationIntent.RETAKE_FOR_IMPROVEMENT,
                ),
            ),
            preferences=PlanningPreferences(target_credit_hours=3),
        )
    )

    assert result.status is PlanStatus.REVIEW_REQUIRED
    assert result.selected_courses[0].registration_intent is (
        RegistrationIntent.RETAKE_FOR_IMPROVEMENT
    )


def test_planner_uses_final_proposed_term_for_concurrent_prerequisites() -> None:
    prerequisite = course("CSE392")
    target = course("CSE493")
    concurrent_rule = CourseEligibilityRuleSet(
        target.identity,
        RuleSetStatus.COMPLETE,
        rules=(
            AcademicRule(
                rule_id="PR-CSE493",
                regulation=R23,
                program=CAIE,
                approval_status=ApprovalStatus.APPROVED,
                verification_status=VerificationStatus.SOURCE_VERIFIED,
                expression=OrExpression(
                    (
                        CoursePassedExpression(prerequisite.identity),
                        CourseConcurrentExpression(prerequisite.identity),
                    )
                ),
            ),
        ),
    )
    result = planner().plan(
        request(
            (prerequisite, target),
            (
                requirement(prerequisite.identity, "REQ-392"),
                requirement(target.identity, "REQ-493"),
            ),
            rule_sets=(rule_set(prerequisite.identity), concurrent_rule),
            preferences=PlanningPreferences(target_credit_hours=6),
        )
    )

    assert [item.identity for item in result.selected_courses] == [
        prerequisite.identity,
        target.identity,
    ]
    assert result.validation_result is not None
    assert result.validation_result.status.value == "VALID"


def test_zero_credit_required_course_counts_as_a_course() -> None:
    target = course("ASUx11", 0)
    result = planner().plan(
        request(
            (target,),
            (requirement(target.identity, "ZERO-1"),),
            rule_sets=(rule_set(target.identity),),
        )
    )

    assert result.achieved_credit_hours == 0
    assert result.achieved_course_count == 1
    assert result.validation_result is not None
    assert result.validation_result.load_result.course_count == 1


def test_target_deviation_is_structured_when_exact_target_is_unreachable() -> None:
    target = course("CSE341")
    result = planner().plan(
        request(
            (target,),
            (requirement(target.identity, "REQ-1"),),
            rule_sets=(rule_set(target.identity),),
            preferences=PlanningPreferences(target_credit_hours=15),
        )
    )

    assert result.status is PlanStatus.PARTIAL
    assert result.deviation is not None
    assert result.deviation.requested_credit_hours == 15
    assert result.deviation.achieved_credit_hours == 3


def test_alternatives_are_validated_and_deterministic() -> None:
    courses = tuple(course(f"CSE{341 + index}") for index in range(3))
    requirements = tuple(
        requirement(item.identity, f"REQ-{index}")
        for index, item in enumerate(courses, start=1)
    )
    preferences = PlanningPreferences(target_credit_hours=3)
    search = PlanningSearchPolicy(max_alternatives=2)
    first = planner().plan(
        request(
            courses,
            requirements,
            rule_sets=tuple(rule_set(item.identity) for item in courses),
            preferences=preferences,
            search_policy=search,
        )
    )
    reverse = planner().plan(
        request(
            tuple(reversed(courses)),
            tuple(reversed(requirements)),
            rule_sets=tuple(
                reversed(tuple(rule_set(item.identity) for item in courses))
            ),
            preferences=preferences,
            search_policy=search,
        )
    )

    assert len(first.alternatives) <= 2
    assert all(
        item.validation_result.status.value != "INVALID" for item in first.alternatives
    )
    assert first.to_dict() == reverse.to_dict()
    assert all(
        item.alternative_type is not PlanAlternativeType.PRIMARY
        for item in first.alternatives
    )


def test_missing_offering_and_timetable_are_explicitly_unavailable() -> None:
    target = course("CSE341")
    result = planner().plan(
        request(
            (target,),
            (requirement(target.identity, "REQ-1"),),
            rule_sets=(rule_set(target.identity),),
            preferences=PlanningPreferences(target_credit_hours=3),
        )
    )

    assert result.coverage.offering is PlanningCoverageStatus.UNAVAILABLE
    assert result.coverage.timetable is PlanningCoverageStatus.UNAVAILABLE
    assert result.status is PlanStatus.VALID
    assert result.registration_ready is False
    assert result.diagnostics == result.review_items
