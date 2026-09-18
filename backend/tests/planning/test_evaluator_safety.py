from __future__ import annotations

import inspect

import pytest

from backend.app.planning.domain.course import Program, Regulation
from backend.app.planning.domain.evaluation import EvaluationOutcome
from backend.app.planning.domain.expressions import (
    MinEarnedCreditsExpression,
    RuleExpression,
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


def _student() -> StudentState:
    return StudentState(
        student_id="student-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        earned_credit_hours=60,
    )


def _rule(
    expression: RuleExpression | None,
    *,
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED,
    verification_status: VerificationStatus = VerificationStatus.SOURCE_VERIFIED,
    critical: bool = True,
    provenance: Provenance | None = None,
) -> AcademicRule:
    return AcademicRule(
        rule_id="R23-PR-CSE341",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        approval_status=approval_status,
        verification_status=verification_status,
        critical_for_planner=critical,
        provenance=provenance,
        expression=expression,
    )


def test_approved_verified_critical_rule_can_produce_authoritative_evaluation() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.authoritative(),
        DatasetVersion("academic-2023-v1"),
        engine_version="planning-engine-0.1",
        ruleset_version="ruleset-1",
    ).evaluate(_rule(MinEarnedCreditsExpression(60)), _student())

    assert result.outcome is EvaluationOutcome.SATISFIED
    assert result.authoritative is True
    assert result.requires_human_review is False
    assert result.approval_status is ApprovalStatus.APPROVED
    assert result.verification_status is VerificationStatus.SOURCE_VERIFIED
    assert result.metadata.engine_version == "planning-engine-0.1"
    assert result.metadata.ruleset_version == "ruleset-1"
    assert result.reason_codes == ()


def test_authoritative_unsafe_critical_rule_fails_closed_before_evaluation() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.authoritative(), DatasetVersion("academic-2023-v1")
    ).evaluate(
        _rule(
            MinEarnedCreditsExpression(60),
            approval_status=ApprovalStatus.SOURCE_VERIFIED,
        ),
        _student(),
    )

    assert result.outcome is EvaluationOutcome.INDETERMINATE
    assert result.authoritative is False
    assert result.requires_human_review is True
    assert ReasonCode.UNAPPROVED_RULE in result.reason_codes
    assert result.decision_trace.root.code is TraceCode.RULE
    assert result.decision_trace.root.status is DecisionStatus.NOT_EVALUATED


def test_development_evaluation_remains_non_authoritative() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-2023-dev")
    ).evaluate(
        _rule(
            MinEarnedCreditsExpression(60),
            approval_status=ApprovalStatus.SOURCE_VERIFIED,
        ),
        _student(),
    )

    assert result.outcome is EvaluationOutcome.SATISFIED
    assert result.authoritative is False
    assert result.requires_human_review is False
    assert ReasonCode.UNAPPROVED_RULE in result.reason_codes
    assert result.approval_status is ApprovalStatus.SOURCE_VERIFIED


@pytest.mark.parametrize(
    ("approval_status", "reason_code", "trace_status"),
    [
        (
            ApprovalStatus.BLOCKED,
            ReasonCode.BLOCKED_RULE,
            DecisionStatus.BLOCKED,
        ),
        (
            ApprovalStatus.CONFLICTED,
            ReasonCode.CONFLICTED_RULE,
            DecisionStatus.CONFLICTED,
        ),
        (
            ApprovalStatus.SUPERSEDED,
            ReasonCode.UNAPPROVED_RULE,
            DecisionStatus.NOT_EVALUATED,
        ),
    ],
)
def test_unsafe_lifecycle_states_fail_closed_in_development(
    approval_status: ApprovalStatus,
    reason_code: ReasonCode,
    trace_status: DecisionStatus,
) -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-2023-dev")
    ).evaluate(
        _rule(MinEarnedCreditsExpression(0), approval_status=approval_status),
        _student(),
    )

    assert result.outcome is EvaluationOutcome.INDETERMINATE
    assert result.authoritative is False
    assert result.requires_human_review is True
    assert reason_code in result.reason_codes
    assert result.decision_trace.root.status is trace_status


def test_provenance_survives_rule_evaluation_and_is_attached_to_trace() -> None:
    provenance = Provenance(
        rule_id="R23-PR-CSE341",
        source_id="regulations-2023",
        source_page=42,
        approval_status=ApprovalStatus.SOURCE_VERIFIED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )

    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-2023-dev")
    ).evaluate(
        _rule(
            MinEarnedCreditsExpression(60),
            approval_status=ApprovalStatus.SOURCE_VERIFIED,
            provenance=provenance,
        ),
        _student(),
    )

    assert result.provenance == (provenance,)
    assert result.decision_trace.root.provenance == (provenance,)


def test_rule_without_expression_is_structured_indeterminate() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-2023-dev")
    ).evaluate(_rule(None), _student())

    assert result.outcome is EvaluationOutcome.INDETERMINATE
    assert result.authoritative is False
    assert result.requires_human_review is True
    assert ReasonCode.UNSUPPORTED_RULE in result.reason_codes
    assert result.decision_trace.root.code is TraceCode.RULE
    assert result.decision_trace.root.status is DecisionStatus.UNSUPPORTED


class _UnsupportedExpression(RuleExpression):
    pass


def test_unsupported_expression_is_structured_indeterminate() -> None:
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-2023-dev")
    ).evaluate(_rule(_UnsupportedExpression()), _student())

    assert result.outcome is EvaluationOutcome.INDETERMINATE
    assert result.authoritative is False
    assert result.requires_human_review is True
    assert ReasonCode.UNSUPPORTED_RULE in result.reason_codes
    assert result.decision_trace.root.status is DecisionStatus.UNSUPPORTED


def test_evaluator_is_pure_and_has_no_repository_dependency() -> None:
    parameters = tuple(inspect.signature(RuleEvaluator.evaluate).parameters)

    assert parameters == ("self", "rule", "student")
    result = RuleEvaluator(
        ExecutionPolicy.development(), DatasetVersion("academic-2023-dev")
    ).evaluate(_rule(MinEarnedCreditsExpression(60)), _student())
    assert result.outcome is EvaluationOutcome.SATISFIED
