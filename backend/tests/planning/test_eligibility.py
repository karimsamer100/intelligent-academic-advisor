from __future__ import annotations

import inspect

import pytest

from backend.app.planning.domain.course import (
    Course,
    CourseIdentity,
    Program,
    Regulation,
)
from backend.app.planning.domain.eligibility import (
    CourseEligibilityRuleSet,
    EligibilityRequest,
    EligibilityStatus,
    RuleSetStatus,
)
from backend.app.planning.domain.evaluation import EvaluationOutcome
from backend.app.planning.domain.expressions import (
    AndExpression,
    CoursePassedExpression,
    MinEarnedCreditsExpression,
    MinGpaExpression,
    OrExpression,
)
from backend.app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from backend.app.planning.domain.provenance import Provenance
from backend.app.planning.domain.reasons import ReasonCode
from backend.app.planning.domain.rules import AcademicRule
from backend.app.planning.domain.student import StudentState
from backend.app.planning.domain.trace import DecisionStatus, TraceCode
from backend.app.planning.domain.version import DatasetVersion
from backend.app.planning.policy import ExecutionPolicy
from backend.app.planning.rules.evaluator import RuleEvaluator
from backend.app.planning.eligibility.service import EligibilityService


TARGET = CourseIdentity.parse("R23:CAIE:CSE341")
PREREQUISITE = CourseIdentity.parse("R23:CAIE:CSE241")
ALTERNATIVE = CourseIdentity.parse("R23:CAIE:CSE281")


def _course(
    identity: CourseIdentity = TARGET,
    *,
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED,
    verification_status: VerificationStatus = VerificationStatus.SOURCE_VERIFIED,
) -> Course:
    return Course(
        identity=identity,
        course_name="Target course",
        credit_hours=3,
        approval_status=approval_status,
        verification_status=verification_status,
    )


def _student(
    *,
    regulation: Regulation = Regulation.R23,
    program: Program = Program("CAIE"),
    completed_courses: frozenset[CourseIdentity] = frozenset(),
    passed_courses: frozenset[CourseIdentity] | None = frozenset(),
    current_courses: frozenset[CourseIdentity] = frozenset(),
    earned_credit_hours: int | float | None = 60,
    gpa: int | float | None = 3.0,
    unknown_completion_status_courses: frozenset[CourseIdentity] = frozenset(),
    unknown_pass_status_courses: frozenset[CourseIdentity] = frozenset(),
) -> StudentState:
    return StudentState(
        student_id="student-001",
        regulation=regulation,
        program=program,
        completed_courses=completed_courses,
        passed_courses=passed_courses,
        current_courses=current_courses,
        earned_credit_hours=earned_credit_hours,
        gpa=gpa,
        unknown_completion_status_courses=unknown_completion_status_courses,
        unknown_pass_status_courses=unknown_pass_status_courses,
    )


def _rule(
    rule_id: str,
    expression: object | None,
    *,
    regulation: Regulation = Regulation.R23,
    program: Program = Program("CAIE"),
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED,
    verification_status: VerificationStatus = VerificationStatus.SOURCE_VERIFIED,
    critical_for_planner: bool = True,
    provenance: Provenance | None = None,
) -> AcademicRule:
    return AcademicRule(
        rule_id=rule_id,
        regulation=regulation,
        program=program,
        approval_status=approval_status,
        verification_status=verification_status,
        critical_for_planner=critical_for_planner,
        provenance=provenance,
        expression=expression,  # type: ignore[arg-type]
    )


def _rule_set(
    *rules: AcademicRule,
    target_course: CourseIdentity = TARGET,
    status: RuleSetStatus = RuleSetStatus.COMPLETE,
    reason_codes: tuple[ReasonCode, ...] = (),
) -> CourseEligibilityRuleSet:
    return CourseEligibilityRuleSet(
        target_course=target_course,
        status=status,
        rules=rules,
        reason_codes=reason_codes,
    )


def _service(
    policy: ExecutionPolicy | None = None,
) -> EligibilityService:
    return EligibilityService(
        RuleEvaluator(
            policy or ExecutionPolicy.development(),
            DatasetVersion("academic-2023-v1"),
            engine_version="planning-engine-test",
            ruleset_version="ruleset-test",
        )
    )


def _request(
    student: StudentState,
    course: Course = _course(),
    rule_set: CourseEligibilityRuleSet | None = None,
) -> EligibilityRequest:
    return EligibilityRequest(
        student=student,
        course=course,
        rule_set=rule_set or _rule_set(),
    )


def test_complete_empty_rule_set_can_produce_eligible_result() -> None:
    result = _service().check(_request(_student()))

    assert result.status is EligibilityStatus.ELIGIBLE
    assert result.eligible is True
    assert result.rule_results == ()
    assert result.metadata.requires_human_review is False


def test_unavailable_empty_rule_set_never_produces_eligible_result() -> None:
    rule_set = _rule_set(status=RuleSetStatus.UNAVAILABLE)

    result = _service().check(_request(_student(), rule_set=rule_set))

    assert result.status is EligibilityStatus.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None
    assert result.metadata.requires_human_review is True
    assert ReasonCode.MISSING_REQUIRED_DATA in result.metadata.reason_codes


def test_incomplete_empty_rule_set_never_produces_eligible_result() -> None:
    rule_set = _rule_set(status=RuleSetStatus.INCOMPLETE)

    result = _service().check(_request(_student(), rule_set=rule_set))

    assert result.status is EligibilityStatus.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None


def test_wrong_regulation_is_not_eligible_without_evaluating_rules() -> None:
    course_identity = CourseIdentity.parse("R18:CAIE:CSE341")
    rule_set = _rule_set(
        _rule("unsupported-rule", None),
        target_course=course_identity,
    )

    result = _service().check(_request(_student(), _course(course_identity), rule_set))

    assert result.status is EligibilityStatus.NOT_ELIGIBLE
    assert result.eligible is False
    assert ReasonCode.WRONG_REGULATION in result.metadata.reason_codes
    assert result.rule_results == ()


def test_wrong_program_is_not_eligible_without_evaluating_rules() -> None:
    course_identity = CourseIdentity(
        regulation=Regulation.R23,
        program=Program("CESS"),
        course_code="CSE341",
    )
    rule_set = _rule_set(
        _rule("unsupported-rule", None),
        target_course=course_identity,
    )

    result = _service().check(_request(_student(), _course(course_identity), rule_set))

    assert result.status is EligibilityStatus.NOT_ELIGIBLE
    assert result.eligible is False
    assert ReasonCode.WRONG_PROGRAM in result.metadata.reason_codes
    assert result.rule_results == ()


def test_completed_target_is_terminal_and_does_not_require_rule_evaluation() -> None:
    rule_set = _rule_set(_rule("unsupported-rule", None))

    result = _service().check(
        _request(_student(completed_courses=frozenset({TARGET})), rule_set=rule_set)
    )

    assert result.status is EligibilityStatus.ALREADY_COMPLETED
    assert result.eligible is False
    assert result.rule_results == ()
    assert ReasonCode.ALREADY_COMPLETED in result.metadata.reason_codes


def test_completed_and_current_target_keeps_completed_as_primary_status() -> None:
    student = _student(
        completed_courses=frozenset({TARGET}),
        current_courses=frozenset({TARGET}),
    )

    result = _service().check(_request(student))

    assert result.status is EligibilityStatus.ALREADY_COMPLETED
    assert ReasonCode.ALREADY_COMPLETED in result.metadata.reason_codes
    assert ReasonCode.CURRENTLY_REGISTERED in result.metadata.reason_codes


def test_currently_registered_target_is_terminal_when_not_completed() -> None:
    result = _service().check(_request(_student(current_courses=frozenset({TARGET}))))

    assert result.status is EligibilityStatus.CURRENTLY_REGISTERED
    assert result.eligible is False
    assert result.rule_results == ()


def test_unknown_target_completion_requires_human_review() -> None:
    result = _service().check(
        _request(
            _student(unknown_completion_status_courses=frozenset({TARGET})),
            rule_set=_rule_set(_rule("unsupported-rule", None)),
        )
    )

    assert result.status is EligibilityStatus.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None
    assert result.rule_results == ()
    assert ReasonCode.MISSING_REQUIRED_DATA in result.metadata.reason_codes


def test_satisfied_prerequisite_produces_eligible_result() -> None:
    rule = _rule("PR-001", CoursePassedExpression(PREREQUISITE))
    student = _student(passed_courses=frozenset({PREREQUISITE}))

    result = _service().check(_request(student, rule_set=_rule_set(rule)))

    assert result.status is EligibilityStatus.ELIGIBLE
    assert result.eligible is True
    assert result.satisfied_rule_ids == ("PR-001",)


def test_authoritative_safe_rules_produce_authoritative_eligibility() -> None:
    rule = _rule("PR-001", CoursePassedExpression(PREREQUISITE))
    student = _student(passed_courses=frozenset({PREREQUISITE}))

    result = _service(ExecutionPolicy.authoritative()).check(
        _request(student, rule_set=_rule_set(rule))
    )

    assert result.status is EligibilityStatus.ELIGIBLE
    assert result.eligible is True
    assert result.authoritative is True
    assert result.satisfied_rules[0].rule_id == "PR-001"


def test_unsatisfied_prerequisite_produces_not_eligible_result() -> None:
    rule = _rule("PR-001", CoursePassedExpression(PREREQUISITE))

    result = _service().check(_request(_student(), rule_set=_rule_set(rule)))

    assert result.status is EligibilityStatus.NOT_ELIGIBLE
    assert result.eligible is False
    assert result.failed_rule_ids == ("PR-001",)


def test_nested_rule_is_delegated_and_trace_is_preserved() -> None:
    rule = _rule(
        "PR-001",
        AndExpression(
            (
                CoursePassedExpression(PREREQUISITE),
                OrExpression(
                    (
                        CoursePassedExpression(ALTERNATIVE),
                        MinEarnedCreditsExpression(90),
                    )
                ),
            )
        ),
    )
    student = _student(
        passed_courses=frozenset({PREREQUISITE}),
        earned_credit_hours=90,
    )

    result = _service().check(_request(student, rule_set=_rule_set(rule)))

    assert result.status is EligibilityStatus.ELIGIBLE
    rule_trace = result.rule_results[0].decision_trace.root
    assert rule_trace.code is TraceCode.AND
    assert rule_trace.children[1].code is TraceCode.OR
    assert rule_trace.children[1].children[1].actual_value == 90


def test_minimum_credits_rule_is_aggregated() -> None:
    rule = _rule("CR-001", MinEarnedCreditsExpression(60))

    result = _service().check(
        _request(_student(earned_credit_hours=60), rule_set=_rule_set(rule))
    )

    assert result.status is EligibilityStatus.ELIGIBLE
    assert result.rule_results[0].outcome is EvaluationOutcome.SATISFIED


def test_unsatisfied_minimum_credits_rule_is_not_eligible() -> None:
    rule = _rule("CR-001", MinEarnedCreditsExpression(60))

    result = _service().check(
        _request(_student(earned_credit_hours=54), rule_set=_rule_set(rule))
    )

    assert result.status is EligibilityStatus.NOT_ELIGIBLE
    assert result.eligible is False


def test_missing_gpa_rule_requires_human_review() -> None:
    rule = _rule("GPA-001", MinGpaExpression(2.0))

    result = _service().check(_request(_student(gpa=None), rule_set=_rule_set(rule)))

    assert result.status is EligibilityStatus.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None
    assert result.indeterminate_rule_ids == ("GPA-001",)


def test_unsatisfied_and_indeterminate_rules_are_not_eligible_but_require_review() -> (
    None
):
    failed = _rule("PR-001", CoursePassedExpression(PREREQUISITE))
    indeterminate = _rule("GPA-001", MinGpaExpression(2.0))

    result = _service().check(
        _request(
            _student(gpa=None),
            rule_set=_rule_set(failed, indeterminate),
        )
    )

    assert result.status is EligibilityStatus.NOT_ELIGIBLE
    assert result.eligible is False
    assert result.metadata.requires_human_review is True
    assert result.failed_rule_ids == ("PR-001",)
    assert result.indeterminate_rule_ids == ("GPA-001",)


def test_unsupported_required_rule_is_structured_unsupported() -> None:
    result = _service().check(
        _request(_student(), rule_set=_rule_set(_rule("UNSUPPORTED", None)))
    )

    assert result.status is EligibilityStatus.UNSUPPORTED
    assert result.eligible is None
    assert result.metadata.requires_human_review is True
    assert ReasonCode.UNSUPPORTED_RULE in result.metadata.reason_codes


@pytest.mark.parametrize(
    ("approval_status", "expected_reason"),
    [
        (ApprovalStatus.BLOCKED, ReasonCode.BLOCKED_RULE),
        (ApprovalStatus.CONFLICTED, ReasonCode.CONFLICTED_RULE),
    ],
)
def test_blocked_or_conflicted_rules_require_review_in_development(
    approval_status: ApprovalStatus,
    expected_reason: ReasonCode,
) -> None:
    rule = _rule(
        "PR-001",
        CoursePassedExpression(PREREQUISITE),
        approval_status=approval_status,
    )

    result = _service().check(_request(_student(), rule_set=_rule_set(rule)))

    assert result.status is EligibilityStatus.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None
    assert expected_reason in result.metadata.reason_codes


def test_authoritative_unapproved_critical_rule_is_blocked_by_unverified_rule() -> None:
    rule = _rule(
        "PR-001",
        CoursePassedExpression(PREREQUISITE),
        approval_status=ApprovalStatus.ACADEMICALLY_REVIEWED,
    )
    service = _service(ExecutionPolicy.authoritative())

    result = service.check(_request(_student(), rule_set=_rule_set(rule)))

    assert result.status is EligibilityStatus.BLOCKED_BY_UNVERIFIED_RULE
    assert result.eligible is None
    assert result.metadata.authoritative is False
    assert result.metadata.requires_human_review is True


def test_authoritative_unverified_target_course_is_blocked_by_unverified_rule() -> None:
    service = _service(ExecutionPolicy.authoritative())
    course = _course(verification_status=VerificationStatus.NEEDS_VERIFICATION)

    result = service.check(_request(_student(), course=course))

    assert result.status is EligibilityStatus.BLOCKED_BY_UNVERIFIED_RULE
    assert result.eligible is None
    assert ReasonCode.UNVERIFIED_RULE in result.metadata.reason_codes


def test_conflicted_target_course_requires_human_review_in_development() -> None:
    course = _course(approval_status=ApprovalStatus.CONFLICTED)

    result = _service().check(_request(_student(), course=course))

    assert result.status is EligibilityStatus.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None
    assert ReasonCode.CONFLICTED_RULE in result.metadata.reason_codes


def test_development_evaluation_can_be_eligible_but_is_non_authoritative() -> None:
    rule = _rule(
        "PR-001",
        CoursePassedExpression(PREREQUISITE),
        approval_status=ApprovalStatus.SOURCE_VERIFIED,
    )
    student = _student(passed_courses=frozenset({PREREQUISITE}))

    result = _service().check(_request(student, rule_set=_rule_set(rule)))

    assert result.status is EligibilityStatus.ELIGIBLE
    assert result.eligible is True
    assert result.metadata.authoritative is False
    assert result.rule_results[0].authoritative is False


def test_unknown_prerequisite_pass_status_requires_human_review() -> None:
    rule = _rule("PR-001", CoursePassedExpression(PREREQUISITE))
    student = _student(unknown_pass_status_courses=frozenset({PREREQUISITE}))

    result = _service().check(_request(student, rule_set=_rule_set(rule)))

    assert result.status is EligibilityStatus.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None
    assert result.indeterminate_rule_ids == ("PR-001",)
    assert ReasonCode.MISSING_REQUIRED_DATA in result.metadata.reason_codes


def test_incomplete_rule_set_with_unsupported_reason_is_unsupported() -> None:
    rule_set = _rule_set(
        status=RuleSetStatus.INCOMPLETE,
        reason_codes=(ReasonCode.UNSUPPORTED_RULE,),
    )

    result = _service().check(_request(_student(), rule_set=rule_set))

    assert result.status is EligibilityStatus.UNSUPPORTED
    assert result.eligible is None
    assert result.metadata.requires_human_review is True


def test_complete_rule_set_rejects_unsupported_reason_code() -> None:
    with pytest.raises(ValueError, match="COMPLETE"):
        _rule_set(reason_codes=(ReasonCode.UNSUPPORTED_RULE,))


def test_blocked_target_course_fails_closed_before_student_facts() -> None:
    service = _service(ExecutionPolicy.development())

    result = service.check(
        _request(
            _student(completed_courses=frozenset({TARGET})),
            course=_course(approval_status=ApprovalStatus.BLOCKED),
        )
    )

    assert result.status is EligibilityStatus.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None
    assert result.metadata.authoritative is False


def test_rule_provenance_survives_into_result_and_composed_trace() -> None:
    provenance = Provenance(
        rule_id="PR-001",
        source_id="regulations-2023",
        source_page=42,
        approval_status=ApprovalStatus.SOURCE_VERIFIED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    rule = _rule(
        "PR-001",
        CoursePassedExpression(PREREQUISITE),
        approval_status=ApprovalStatus.SOURCE_VERIFIED,
        provenance=provenance,
        critical_for_planner=False,
    )
    student = _student(passed_courses=frozenset({PREREQUISITE}))

    result = _service().check(_request(student, rule_set=_rule_set(rule)))

    assert result.rule_results[0].provenance == (provenance,)
    assert provenance in result.metadata.provenance
    assert provenance in result.metadata.decision_trace.root.provenance


def test_eligibility_trace_has_requirement_semantics_and_aligned_root_status() -> None:
    rule = _rule("PR-001", CoursePassedExpression(PREREQUISITE))
    student = _student(passed_courses=frozenset({PREREQUISITE}))

    result = _service().check(_request(student, rule_set=_rule_set(rule)))
    root = result.metadata.decision_trace.root

    assert result.status is EligibilityStatus.ELIGIBLE
    assert root.code is TraceCode.ELIGIBILITY
    assert root.status is DecisionStatus.SATISFIED
    assert [child.code for child in root.children] == [
        TraceCode.SCOPE_CHECK,
        TraceCode.COURSE_LIFECYCLE,
        TraceCode.NOT_ALREADY_COMPLETED,
        TraceCode.NOT_CURRENTLY_REGISTERED,
        TraceCode.RULE_SET_AVAILABILITY,
        TraceCode.COURSE_PASSED,
    ]
    assert root.children[2].expected_value is False
    assert root.children[2].actual_value is False


def test_not_eligible_trace_root_is_unsatisfied() -> None:
    rule = _rule("PR-001", CoursePassedExpression(PREREQUISITE))

    result = _service().check(_request(_student(), rule_set=_rule_set(rule)))

    assert result.status is EligibilityStatus.NOT_ELIGIBLE
    assert result.metadata.decision_trace.root.status is DecisionStatus.FAILED


def test_equivalent_rule_input_order_produces_identical_result_and_trace() -> None:
    first_rule = _rule("A-RULE", MinEarnedCreditsExpression(60))
    second_rule = _rule("B-RULE", MinGpaExpression(2.0))
    student = _student()

    first = _service().check(
        _request(student, rule_set=_rule_set(first_rule, second_rule))
    )
    second = _service().check(
        _request(student, rule_set=_rule_set(second_rule, first_rule))
    )

    assert first == second
    assert (
        first.metadata.decision_trace.to_json()
        == second.metadata.decision_trace.to_json()
    )


def test_rule_set_target_binding_is_required() -> None:
    other_course = CourseIdentity.parse("R23:CAIE:CSE342")
    rule_set = _rule_set(target_course=other_course)

    with pytest.raises(ValueError, match="target_course"):
        _service().check(_request(_student(), rule_set=rule_set))


def test_duplicate_rule_ids_fail_safely() -> None:
    first = _rule("DUPLICATE", MinEarnedCreditsExpression(60))
    second = _rule("DUPLICATE", MinGpaExpression(2.0))

    with pytest.raises(ValueError, match="unique"):
        _rule_set(first, second)


def test_rule_scope_mismatch_requires_review_without_evaluating_rule() -> None:
    rule = _rule(
        "WRONG-SCOPE",
        CoursePassedExpression(PREREQUISITE),
        program=Program("CESS"),
    )

    result = _service().check(_request(_student(), rule_set=_rule_set(rule)))

    assert result.status is EligibilityStatus.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None
    assert result.rule_results == ()
    assert ReasonCode.WRONG_PROGRAM in result.metadata.reason_codes


def test_service_has_only_typed_request_dependency_and_no_repository_parameter() -> (
    None
):
    parameters = tuple(inspect.signature(EligibilityService.check).parameters)

    assert parameters == ("self", "request")
