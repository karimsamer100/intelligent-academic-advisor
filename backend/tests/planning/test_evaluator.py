from app.planning.domain.course import CourseIdentity, Program, Regulation
from app.planning.domain.evaluation import EvaluationOutcome
from app.planning.domain.expressions import (
    AndExpression,
    CourseCompletedExpression,
    CourseCurrentlyRegisteredExpression,
    CoursePassedExpression,
    MaxEarnedCreditsExpression,
    MaxGpaExpression,
    MinEarnedCreditsExpression,
    MinGpaExpression,
    NotExpression,
    OrExpression,
    UnsupportedExpression,
)
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.domain.reasons import ReasonCode
from app.planning.domain.rules import AcademicRule
from app.planning.domain.student import StudentState
from app.planning.domain.trace import DecisionStatus, TraceCode
from app.planning.domain.version import DatasetVersion
from app.planning.policy import ExecutionPolicy
from app.planning.rules.evaluator import RuleEvaluator


def _student(
    *,
    completed_courses: frozenset[CourseIdentity] = frozenset(),
    passed_courses: frozenset[CourseIdentity] | None = None,
    current_courses: frozenset[CourseIdentity] = frozenset(),
    gpa: float | None = None,
    earned_credit_hours: int | float | None = 0,
    unknown_pass_status_courses: frozenset[CourseIdentity] = frozenset(),
    unknown_completion_status_courses: frozenset[CourseIdentity] = frozenset(),
) -> StudentState:
    return StudentState(
        student_id="student-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        completed_courses=completed_courses,
        passed_courses=passed_courses,
        current_courses=current_courses,
        gpa=gpa,
        earned_credit_hours=earned_credit_hours,
        unknown_pass_status_courses=unknown_pass_status_courses,
        unknown_completion_status_courses=unknown_completion_status_courses,
    )


def _rule(expression: object, *, critical: bool = False) -> AcademicRule:
    return AcademicRule(
        rule_id="R23-PR-CSE341",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        critical_for_planner=critical,
        expression=expression,  # type: ignore[arg-type]
    )


def test_course_passed_is_satisfied_from_explicit_passed_courses() -> None:
    course = CourseIdentity.parse("R23:CAIE:CSE241")
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(CoursePassedExpression(course)),
        _student(passed_courses=frozenset({course})),
    )

    assert result.outcome is EvaluationOutcome.SATISFIED
    assert result.decision_trace.root.code is TraceCode.COURSE_PASSED
    assert result.decision_trace.root.status is DecisionStatus.SATISFIED
    assert result.decision_trace.root.expected_value is True
    assert result.decision_trace.root.actual_value is True


def test_course_passed_is_unsatisfied_when_explicit_passed_courses_exclude_course() -> (
    None
):
    course = CourseIdentity.parse("R23:CAIE:CSE241")
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(CoursePassedExpression(course)),
        _student(passed_courses=frozenset()),
    )

    assert result.outcome is EvaluationOutcome.UNSATISFIED
    assert result.decision_trace.root.actual_value is False


def test_course_passed_is_indeterminate_when_passed_data_is_unavailable() -> None:
    course = CourseIdentity.parse("R23:CAIE:CSE241")
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(CoursePassedExpression(course)),
        _student(completed_courses=frozenset({course}), passed_courses=None),
    )

    assert result.outcome is EvaluationOutcome.INDETERMINATE
    assert result.requires_human_review is True
    assert ReasonCode.MISSING_REQUIRED_DATA in result.reason_codes
    assert result.decision_trace.root.status is DecisionStatus.INDETERMINATE
    assert result.decision_trace.root.expected_value is True
    assert result.decision_trace.root.actual_value is None


def test_course_passed_unknown_is_local_to_one_course() -> None:
    known_course = CourseIdentity.parse("R23:CAIE:CSE111")
    unknown_course = CourseIdentity.parse("R23:CAIE:CSE999")
    absent_course = CourseIdentity.parse("R23:CAIE:CSE500")
    evaluator = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    )
    student = _student(
        passed_courses=frozenset({known_course}),
        unknown_pass_status_courses=frozenset({unknown_course}),
    )

    known_result = evaluator.evaluate(
        _rule(CoursePassedExpression(known_course)), student
    )
    unknown_result = evaluator.evaluate(
        _rule(CoursePassedExpression(unknown_course)), student
    )
    absent_result = evaluator.evaluate(
        _rule(CoursePassedExpression(absent_course)), student
    )

    assert known_result.outcome is EvaluationOutcome.SATISFIED
    assert unknown_result.outcome is EvaluationOutcome.INDETERMINATE
    assert ReasonCode.MISSING_REQUIRED_DATA in unknown_result.reason_codes
    assert unknown_result.decision_trace.root.actual_value is None
    assert absent_result.outcome is EvaluationOutcome.UNSATISFIED


def test_course_completed_unknown_is_local_to_one_course() -> None:
    known_course = CourseIdentity.parse("R23:CAIE:CSE111")
    unknown_course = CourseIdentity.parse("R23:CAIE:CSE999")
    evaluator = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    )
    student = _student(
        completed_courses=frozenset({known_course}),
        unknown_completion_status_courses=frozenset({unknown_course}),
    )

    known_result = evaluator.evaluate(
        _rule(CourseCompletedExpression(known_course)), student
    )
    unknown_result = evaluator.evaluate(
        _rule(CourseCompletedExpression(unknown_course)), student
    )

    assert known_result.outcome is EvaluationOutcome.SATISFIED
    assert unknown_result.outcome is EvaluationOutcome.INDETERMINATE
    assert ReasonCode.MISSING_REQUIRED_DATA in unknown_result.reason_codes


def test_course_completed_uses_completed_courses_without_inference_from_passed_courses() -> (
    None
):
    course = CourseIdentity.parse("R23:CAIE:CSE241")
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(CourseCompletedExpression(course)),
        _student(completed_courses=frozenset({course}), passed_courses=frozenset()),
    )

    assert result.outcome is EvaluationOutcome.SATISFIED


def test_course_currently_registered_checks_current_courses() -> None:
    course = CourseIdentity.parse("R23:CAIE:CSE341")
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(CourseCurrentlyRegisteredExpression(course)),
        _student(current_courses=frozenset({course})),
    )

    assert result.outcome is EvaluationOutcome.SATISFIED


def test_min_earned_credits_is_satisfied_at_threshold() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(MinEarnedCreditsExpression(60)),
        _student(earned_credit_hours=60),
    )

    assert result.outcome is EvaluationOutcome.SATISFIED
    assert result.decision_trace.root.expected_value == 60
    assert result.decision_trace.root.actual_value == 60


def test_min_earned_credits_is_unsatisfied_below_threshold() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(MinEarnedCreditsExpression(60)),
        _student(earned_credit_hours=54),
    )

    assert result.outcome is EvaluationOutcome.UNSATISFIED


def test_min_earned_credits_with_missing_total_is_indeterminate() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(MinEarnedCreditsExpression(60)),
        _student(earned_credit_hours=None),
    )

    assert result.outcome is EvaluationOutcome.INDETERMINATE
    assert result.requires_human_review is True
    assert ReasonCode.MISSING_REQUIRED_DATA in result.reason_codes
    assert result.decision_trace.root.actual_value is None


def test_max_earned_credits_is_unsatisfied_above_threshold() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(MaxEarnedCreditsExpression(60)),
        _student(earned_credit_hours=61),
    )

    assert result.outcome is EvaluationOutcome.UNSATISFIED
    assert result.decision_trace.root.code is TraceCode.MAX_EARNED_CREDITS


def test_min_gpa_is_satisfied_at_threshold_without_assuming_a_scale() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(MinGpaExpression(5.5)),
        _student(gpa=5.5),
    )

    assert result.outcome is EvaluationOutcome.SATISFIED
    assert result.decision_trace.root.code is TraceCode.MIN_GPA


def test_min_gpa_with_missing_gpa_is_indeterminate() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(MinGpaExpression(2.0)),
        _student(gpa=None),
    )

    assert result.outcome is EvaluationOutcome.INDETERMINATE
    assert result.requires_human_review is True
    assert ReasonCode.MISSING_REQUIRED_DATA in result.reason_codes


def test_max_gpa_is_unsatisfied_above_threshold() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(MaxGpaExpression(3.0)),
        _student(gpa=3.1),
    )

    assert result.outcome is EvaluationOutcome.UNSATISFIED
    assert result.decision_trace.root.code is TraceCode.MAX_GPA


def test_and_is_satisfied_when_all_children_are_satisfied() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(
            AndExpression(
                (MinEarnedCreditsExpression(60), MaxEarnedCreditsExpression(100))
            )
        ),
        _student(earned_credit_hours=80),
    )

    assert result.outcome is EvaluationOutcome.SATISFIED
    assert result.decision_trace.root.code is TraceCode.AND
    assert [child.status for child in result.decision_trace.root.children] == [
        DecisionStatus.SATISFIED,
        DecisionStatus.SATISFIED,
    ]


def test_or_is_satisfied_when_any_child_is_satisfied() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(
            OrExpression(
                (MinEarnedCreditsExpression(90), MaxEarnedCreditsExpression(100))
            )
        ),
        _student(earned_credit_hours=80),
    )

    assert result.outcome is EvaluationOutcome.SATISFIED
    assert [child.status for child in result.decision_trace.root.children] == [
        DecisionStatus.FAILED,
        DecisionStatus.SATISFIED,
    ]


def test_not_inverts_satisfied_child_to_unsatisfied() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(NotExpression(MinEarnedCreditsExpression(60))),
        _student(earned_credit_hours=80),
    )

    assert result.outcome is EvaluationOutcome.UNSATISFIED
    assert result.decision_trace.root.code is TraceCode.NOT
    assert result.decision_trace.root.children[0].status is DecisionStatus.SATISFIED


def test_nested_and_or_expression_mirrors_expression_tree() -> None:
    course = CourseIdentity.parse("R23:CAIE:CSE241")
    expression = AndExpression(
        (
            CoursePassedExpression(course),
            OrExpression(
                (
                    CourseCompletedExpression(CourseIdentity.parse("R23:CAIE:CSE281")),
                    MinEarnedCreditsExpression(90),
                )
            ),
        )
    )

    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(expression),
        _student(passed_courses=frozenset({course}), earned_credit_hours=90),
    )

    root = result.decision_trace.root
    assert result.outcome is EvaluationOutcome.SATISFIED
    assert root.code is TraceCode.AND
    assert root.children[0].code is TraceCode.COURSE_PASSED
    assert root.children[1].code is TraceCode.OR
    assert [child.code for child in root.children[1].children] == [
        TraceCode.COURSE_COMPLETED,
        TraceCode.MIN_EARNED_CREDITS,
    ]


def test_nested_not_expression_is_deterministic() -> None:
    expression = NotExpression(
        AndExpression((MinEarnedCreditsExpression(60), MaxEarnedCreditsExpression(100)))
    )
    evaluator = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    )
    first = evaluator.evaluate(_rule(expression), _student(earned_credit_hours=80))
    second = evaluator.evaluate(_rule(expression), _student(earned_credit_hours=80))

    assert first.outcome is EvaluationOutcome.UNSATISFIED
    assert first.decision_trace == second.decision_trace
    assert first.decision_trace.to_json() == second.decision_trace.to_json()


def test_and_with_indeterminate_child_is_indeterminate_when_no_child_fails() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(AndExpression((MinGpaExpression(2.0), MinEarnedCreditsExpression(60)))),
        _student(gpa=None, earned_credit_hours=60),
    )

    assert result.outcome is EvaluationOutcome.INDETERMINATE
    assert result.decision_trace.root.status is DecisionStatus.INDETERMINATE


def test_or_with_indeterminate_child_is_indeterminate_when_no_child_succeeds() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(OrExpression((MinGpaExpression(2.0), MinEarnedCreditsExpression(60)))),
        _student(gpa=None, earned_credit_hours=0),
    )

    assert result.outcome is EvaluationOutcome.INDETERMINATE
    assert result.decision_trace.root.status is DecisionStatus.INDETERMINATE


def test_not_preserves_indeterminate_outcome() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(NotExpression(MinGpaExpression(2.0))),
        _student(gpa=None),
    )

    assert result.outcome is EvaluationOutcome.INDETERMINATE
    assert result.decision_trace.root.children[0].status is DecisionStatus.INDETERMINATE


def test_evaluator_keeps_child_traces_after_aggregate_outcome_is_known() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(AndExpression((MinEarnedCreditsExpression(90), MinGpaExpression(2.0)))),
        _student(earned_credit_hours=50, gpa=None),
    )

    assert result.outcome is EvaluationOutcome.UNSATISFIED
    assert len(result.decision_trace.root.children) == 2
    assert result.decision_trace.root.children[1].status is DecisionStatus.INDETERMINATE


def test_failed_and_indeterminate_children_require_review() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(
        _rule(
            AndExpression(
                (
                    CoursePassedExpression(CourseIdentity.parse("R23:CAIE:CSE241")),
                    MinGpaExpression(2.0),
                )
            )
        ),
        _student(passed_courses=frozenset(), gpa=None),
    )

    assert result.outcome is EvaluationOutcome.UNSATISFIED
    assert result.requires_human_review is True
    assert result.authoritative is False


def test_unsupported_expression_is_explicitly_indeterminate_with_trace_metadata() -> (
    None
):
    rule = _rule(
        UnsupportedExpression(
            source_type="ENTRY_REQUIREMENT",
            code="Eng/Math",
        )
    )

    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(rule, _student())

    assert result.outcome is EvaluationOutcome.INDETERMINATE
    assert ReasonCode.UNSUPPORTED_RULE in result.reason_codes
    assert result.requires_human_review is True
    root = result.decision_trace.root
    assert root.status is DecisionStatus.UNSUPPORTED
    metadata = {item.key: item.value for item in root.metadata}
    assert metadata["expression_type"] == "ENTRY_REQUIREMENT"


def test_unsupported_child_is_preserved_inside_logical_trace() -> None:
    rule = _rule(
        AndExpression(
            (
                CoursePassedExpression(CourseIdentity.parse("R23:CAIE:CSE241")),
                UnsupportedExpression(
                    source_type="UNRESOLVED_CONDITION",
                    reason="missing condition",
                ),
            )
        )
    )

    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-dev-1")
    ).evaluate(rule, _student())

    assert result.outcome is EvaluationOutcome.INDETERMINATE
    assert len(result.decision_trace.root.children) == 2
    assert result.decision_trace.root.children[1].status is DecisionStatus.UNSUPPORTED
