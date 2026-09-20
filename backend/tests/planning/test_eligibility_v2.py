from __future__ import annotations

from app.planning.domain.course import (
    Course,
    CourseIdentity,
    Program,
    Regulation,
)
from app.planning.domain.eligibility import (
    CourseEligibilityRuleSet,
    EligibilityContext,
    EligibilityDecision,
    EligibilityRequest,
    EvaluationHorizon,
    ProposedTermContext,
    RegistrationIntent,
    RuleSetStatus,
)
from app.planning.domain.expressions import (
    CourseConcurrentExpression,
    CoursePassedExpression,
    OrExpression,
)
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.domain.rules import AcademicRule
from app.planning.domain.student import (
    AcademicHistoryCoverage,
    RegistrationCoverage,
    StudentState,
)
from app.planning.domain.conditions import CourseMustBePassedCondition
from app.planning.domain.conditions import AllConditions, AnyConditions
from app.planning.domain.version import DatasetVersion
from app.planning.eligibility.service import EligibilityService
from app.planning.policy import ExecutionPolicy
from app.planning.rules.evaluator import RuleEvaluator


TARGET = CourseIdentity.parse("R23:CAIE:CSE493")
PREREQUISITE = CourseIdentity.parse("R23:CAIE:CSE392")


def _course(identity: CourseIdentity = TARGET) -> Course:
    return Course(
        identity=identity,
        course_name="Planning test course",
        credit_hours=3,
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )


def _student(
    *,
    passed: frozenset[CourseIdentity] = frozenset(),
    current: frozenset[CourseIdentity] = frozenset(),
    failed: frozenset[CourseIdentity] = frozenset(),
    history_coverage: AcademicHistoryCoverage | None = None,
    registration_coverage: RegistrationCoverage | None = None,
) -> StudentState:
    return StudentState(
        student_id="student-v2",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        passed_courses=passed,
        current_courses=current,
        failed_courses=failed,
        history_coverage=history_coverage,
        registration_coverage=registration_coverage,
    )


def _rule(expression: object, rule_id: str = "PR-493") -> AcademicRule:
    return AcademicRule(
        rule_id=rule_id,
        regulation=Regulation.R23,
        program=Program("CAIE"),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        expression=expression,  # type: ignore[arg-type]
    )


def _request(
    student: StudentState,
    expression: object,
    *,
    context: EligibilityContext | None = None,
    rule_id: str = "PR-493",
) -> EligibilityRequest:
    rule = _rule(expression, rule_id)
    return EligibilityRequest(
        student=student,
        course=_course(),
        rule_set=CourseEligibilityRuleSet(
            target_course=TARGET,
            status=RuleSetStatus.COMPLETE,
            rules=(rule,),
        ),
        context=context or EligibilityContext(),
    )


def _service() -> EligibilityService:
    return EligibilityService(
        RuleEvaluator(
            ExecutionPolicy.development(),
            DatasetVersion("eligibility-v2-test"),
        )
    )


def test_eligibility_context_defaults_to_normal_current() -> None:
    request = _request(_student(), CoursePassedExpression(PREREQUISITE))

    assert request.context.intent is RegistrationIntent.NORMAL
    assert request.context.horizon is EvaluationHorizon.CURRENT
    assert request.context.proposed_term is None


def test_eligibility_context_serializes_deterministically() -> None:
    context = EligibilityContext(
        horizon=EvaluationHorizon.PROJECTED,
        proposed_term=ProposedTermContext(
            target_course=TARGET,
            proposed_courses=(PREREQUISITE, TARGET),
            term_id="2027-Spring",
        ),
    )

    assert context.to_dict() == {
        "intent": "NORMAL",
        "horizon": "PROJECTED",
        "proposed_term": {
            "target_course": TARGET.course_id,
            "proposed_courses": [PREREQUISITE.course_id, TARGET.course_id],
            "term_id": "2027-Spring",
        },
    }


def test_projected_in_progress_prerequisite_returns_typed_condition() -> None:
    context = EligibilityContext(
        horizon=EvaluationHorizon.PROJECTED,
        proposed_term=ProposedTermContext(
            target_course=TARGET,
            proposed_courses=(TARGET,),
            term_id="2027-Spring",
        ),
    )
    result = _service().check(
        _request(
            _student(
                current=frozenset({PREREQUISITE}),
                history_coverage=AcademicHistoryCoverage.COMPLETE,
                registration_coverage=RegistrationCoverage.COMPLETE,
            ),
            CoursePassedExpression(PREREQUISITE),
            context=context,
        )
    )

    assert result.decision is EligibilityDecision.CONDITIONAL
    assert result.eligible is None
    assert result.conditions == (
        CourseMustBePassedCondition(
            course=PREREQUISITE,
            rule_id="PR-493",
            expression_path="root",
        ),
    )
    assert result.metadata.decision_trace.root.status.value == "CONDITIONAL"


def test_future_conditions_compose_and_serialize_without_prose() -> None:
    first = CourseMustBePassedCondition(PREREQUISITE, "PR-1", "root.0")
    second = CourseMustBePassedCondition(TARGET, "PR-2", "root.1")

    all_conditions = AllConditions((first, second))
    any_conditions = AnyConditions((first, second))

    assert all_conditions.to_dict()["type"] == "ALL"
    assert any_conditions.to_dict()["type"] == "ANY"
    assert all_conditions == AllConditions((first, second))


def test_partial_history_does_not_fabricate_projected_pass_condition() -> None:
    context = EligibilityContext(
        horizon=EvaluationHorizon.PROJECTED,
        proposed_term=ProposedTermContext(
            target_course=TARGET,
            proposed_courses=(TARGET,),
        ),
    )
    result = _service().check(
        _request(
            _student(
                current=frozenset({PREREQUISITE}),
                history_coverage=AcademicHistoryCoverage.PARTIAL,
                registration_coverage=RegistrationCoverage.COMPLETE,
            ),
            CoursePassedExpression(PREREQUISITE),
            context=context,
        )
    )

    assert result.decision is EligibilityDecision.HUMAN_REVIEW_REQUIRED
    assert result.conditions == ()


def test_current_in_progress_prerequisite_is_not_treated_as_passed() -> None:
    result = _service().check(
        _request(
            _student(
                current=frozenset({PREREQUISITE}),
                history_coverage=AcademicHistoryCoverage.COMPLETE,
                registration_coverage=RegistrationCoverage.COMPLETE,
            ),
            CoursePassedExpression(PREREQUISITE),
        )
    )

    assert result.decision is EligibilityDecision.INELIGIBLE
    assert result.eligible is False


def test_proposed_same_term_concurrency_satisfies_concurrent_branch() -> None:
    expression = OrExpression(
        (
            CoursePassedExpression(PREREQUISITE),
            CourseConcurrentExpression(PREREQUISITE),
        )
    )
    context = EligibilityContext(
        horizon=EvaluationHorizon.PROJECTED,
        proposed_term=ProposedTermContext(
            target_course=TARGET,
            proposed_courses=(PREREQUISITE, TARGET),
        ),
    )

    result = _service().check(_request(_student(), expression, context=context))

    assert result.decision is EligibilityDecision.ELIGIBLE
    assert result.eligible is True


def test_passed_prerequisite_satisfies_the_prior_pass_branch() -> None:
    expression = OrExpression(
        (
            CoursePassedExpression(PREREQUISITE),
            CourseConcurrentExpression(PREREQUISITE),
        )
    )

    result = _service().check(
        _request(
            _student(
                passed=frozenset({PREREQUISITE}),
                history_coverage=AcademicHistoryCoverage.COMPLETE,
            ),
            expression,
        )
    )

    assert result.decision is EligibilityDecision.ELIGIBLE


def test_current_registration_does_not_satisfy_concurrency() -> None:
    expression = CourseConcurrentExpression(PREREQUISITE)
    context = EligibilityContext(
        horizon=EvaluationHorizon.PROJECTED,
        proposed_term=ProposedTermContext(
            target_course=TARGET,
            proposed_courses=(TARGET,),
        ),
    )

    result = _service().check(
        _request(
            _student(
                current=frozenset({PREREQUISITE}),
                history_coverage=AcademicHistoryCoverage.COMPLETE,
                registration_coverage=RegistrationCoverage.COMPLETE,
            ),
            expression,
            context=context,
        )
    )

    assert result.decision is EligibilityDecision.INELIGIBLE
    assert result.eligible is False


def test_malformed_proposed_term_without_target_is_not_concurrency_truth() -> None:
    context = EligibilityContext(
        horizon=EvaluationHorizon.PROJECTED,
        proposed_term=ProposedTermContext(
            target_course=TARGET,
            proposed_courses=(PREREQUISITE,),
        ),
    )

    result = _service().check(
        _request(_student(), CourseConcurrentExpression(PREREQUISITE), context=context)
    )

    assert result.decision is EligibilityDecision.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None


def test_proposed_context_bound_to_another_target_is_not_reused() -> None:
    other_target = CourseIdentity.parse("R23:CAIE:CSE494")
    context = EligibilityContext(
        horizon=EvaluationHorizon.PROJECTED,
        proposed_term=ProposedTermContext(
            target_course=other_target,
            proposed_courses=(other_target, PREREQUISITE),
        ),
    )

    result = _service().check(
        _request(_student(), CourseConcurrentExpression(PREREQUISITE), context=context)
    )

    assert result.decision is EligibilityDecision.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None


def test_passed_course_normal_intent_is_not_eligible_but_improvement_requires_review() -> (
    None
):
    student = _student(
        passed=frozenset({TARGET}),
        history_coverage=AcademicHistoryCoverage.COMPLETE,
        registration_coverage=RegistrationCoverage.COMPLETE,
    )
    normal = _service().check(
        EligibilityRequest(
            student=student,
            course=_course(),
            rule_set=CourseEligibilityRuleSet(TARGET, RuleSetStatus.COMPLETE),
        )
    )
    improvement = _service().check(
        EligibilityRequest(
            student=student,
            course=_course(),
            rule_set=CourseEligibilityRuleSet(TARGET, RuleSetStatus.COMPLETE),
            context=EligibilityContext(
                intent=RegistrationIntent.RETAKE_FOR_IMPROVEMENT,
            ),
        )
    )

    assert normal.decision is EligibilityDecision.INELIGIBLE
    assert improvement.decision is EligibilityDecision.REQUIRES_ADVISOR_REVIEW
    assert improvement.eligible is None


def test_failed_target_can_be_requested_as_retake_after_failure() -> None:
    student = _student(
        failed=frozenset({TARGET}),
        history_coverage=AcademicHistoryCoverage.COMPLETE,
        registration_coverage=RegistrationCoverage.COMPLETE,
    )
    result = _service().check(
        EligibilityRequest(
            student=student,
            course=_course(),
            rule_set=CourseEligibilityRuleSet(TARGET, RuleSetStatus.COMPLETE),
            context=EligibilityContext(
                intent=RegistrationIntent.RETAKE_AFTER_FAILURE,
            ),
        )
    )

    assert result.decision is EligibilityDecision.ELIGIBLE
    assert result.eligible is True


def test_student_state_exposes_course_attempt_facts_as_queries() -> None:
    student = _student(
        failed=frozenset({TARGET}),
        history_coverage=AcademicHistoryCoverage.COMPLETE,
        registration_coverage=RegistrationCoverage.COMPLETE,
    )

    assert student.has_failed_attempt(TARGET) is True
    assert student.has_withdrawn_attempt(TARGET) is False
    assert student.has_incomplete_attempt(TARGET) is False


def test_retake_after_failure_without_failure_in_complete_history_is_ineligible() -> (
    None
):
    result = _service().check(
        EligibilityRequest(
            student=_student(
                history_coverage=AcademicHistoryCoverage.COMPLETE,
                registration_coverage=RegistrationCoverage.COMPLETE,
            ),
            course=_course(),
            rule_set=CourseEligibilityRuleSet(TARGET, RuleSetStatus.COMPLETE),
            context=EligibilityContext(
                intent=RegistrationIntent.RETAKE_AFTER_FAILURE,
            ),
        )
    )

    assert result.decision is EligibilityDecision.INELIGIBLE
    assert result.eligible is False


def test_retake_after_failure_with_incomplete_history_requires_review() -> None:
    result = _service().check(
        EligibilityRequest(
            student=_student(history_coverage=AcademicHistoryCoverage.PARTIAL),
            course=_course(),
            rule_set=CourseEligibilityRuleSet(TARGET, RuleSetStatus.COMPLETE),
            context=EligibilityContext(
                intent=RegistrationIntent.RETAKE_AFTER_FAILURE,
            ),
        )
    )

    assert result.decision is EligibilityDecision.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None


def test_improvement_intent_with_unknown_effective_pass_requires_review() -> None:
    result = _service().check(
        EligibilityRequest(
            student=_student(history_coverage=AcademicHistoryCoverage.PARTIAL),
            course=_course(),
            rule_set=CourseEligibilityRuleSet(TARGET, RuleSetStatus.COMPLETE),
            context=EligibilityContext(
                intent=RegistrationIntent.RETAKE_FOR_IMPROVEMENT,
            ),
        )
    )

    assert result.decision is EligibilityDecision.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None
