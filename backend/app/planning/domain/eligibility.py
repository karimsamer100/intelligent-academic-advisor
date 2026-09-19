"""Typed contracts for framework-independent course eligibility decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .conditions import FutureCondition
from .context import (
    EligibilityContext,
    EvaluationHorizon,
    ProposedTermContext,
    RegistrationIntent,
)
from .course import Course, CourseIdentity
from .evaluation import EvaluationOutcome, RuleEvaluationResult
from .reasons import ReasonCode
from .results import ResultMetadata
from .rules import AcademicRule
from .student import StudentState


class RuleSetStatus(StrEnum):
    """Completeness of the eligibility rules supplied by an upstream caller."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


class EligibilityStatus(StrEnum):
    """Top-level status of a target-course eligibility decision."""

    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    CURRENTLY_REGISTERED = "CURRENTLY_REGISTERED"
    BLOCKED_BY_UNVERIFIED_RULE = "BLOCKED_BY_UNVERIFIED_RULE"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"
    CONDITIONAL = "CONDITIONAL"
    REQUIRES_ADVISOR_REVIEW = "REQUIRES_ADVISOR_REVIEW"


class EligibilityDecision(StrEnum):
    """Canonical future-facing decision vocabulary."""

    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    CONDITIONAL = "CONDITIONAL"
    REQUIRES_ADVISOR_REVIEW = "REQUIRES_ADVISOR_REVIEW"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class CourseEligibilityRuleSet:
    """Rules already selected for one target course by an upstream adapter.

    ``target_course`` is the binding between this collection and the course.
    The current ``AcademicRule`` contract intentionally does not claim that
    binding itself; selecting the correct records remains the adapter's
    responsibility.
    """

    target_course: CourseIdentity
    status: RuleSetStatus
    rules: tuple[AcademicRule, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.target_course, CourseIdentity):
            raise TypeError("target_course must be a CourseIdentity")
        if not isinstance(self.status, RuleSetStatus):
            raise TypeError("status must be a RuleSetStatus")

        normalized_rules = tuple(self.rules)
        if not all(isinstance(rule, AcademicRule) for rule in normalized_rules):
            raise TypeError("rules must contain only AcademicRule values")

        rule_ids = tuple(rule.rule_id for rule in normalized_rules)
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("rule IDs must be unique")

        normalized_reasons = _unique_reason_codes(tuple(self.reason_codes))
        if not all(isinstance(reason, ReasonCode) for reason in normalized_reasons):
            raise TypeError("reason_codes must contain only ReasonCode values")
        if (
            self.status is RuleSetStatus.COMPLETE
            and ReasonCode.UNSUPPORTED_RULE in normalized_reasons
        ):
            raise ValueError("COMPLETE rule sets cannot carry UNSUPPORTED_RULE")

        object.__setattr__(
            self, "rules", tuple(sorted(normalized_rules, key=lambda r: r.rule_id))
        )
        object.__setattr__(self, "reason_codes", normalized_reasons)


@dataclass(frozen=True, slots=True)
class EligibilityRequest:
    """Already-loaded typed inputs for one eligibility check."""

    student: StudentState
    course: Course
    rule_set: CourseEligibilityRuleSet
    context: EligibilityContext = EligibilityContext()

    def __post_init__(self) -> None:
        if not isinstance(self.student, StudentState):
            raise TypeError("student must be a StudentState")
        if not isinstance(self.course, Course):
            raise TypeError("course must be a Course")
        if not isinstance(self.rule_set, CourseEligibilityRuleSet):
            raise TypeError("rule_set must be a CourseEligibilityRuleSet")
        if not isinstance(self.context, EligibilityContext):
            raise TypeError("context must be an EligibilityContext")


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    """Eligibility payload composed with shared engine result metadata."""

    target_course: CourseIdentity
    status: EligibilityStatus
    eligible: bool | None
    rule_set_status: RuleSetStatus
    metadata: ResultMetadata
    rule_results: tuple[RuleEvaluationResult, ...] = ()
    conditions: tuple[FutureCondition, ...] = ()
    decision: EligibilityDecision | None = None
    intent: RegistrationIntent = RegistrationIntent.NORMAL
    horizon: EvaluationHorizon = EvaluationHorizon.CURRENT

    def __post_init__(self) -> None:
        if not isinstance(self.target_course, CourseIdentity):
            raise TypeError("target_course must be a CourseIdentity")
        if not isinstance(self.status, EligibilityStatus):
            raise TypeError("status must be an EligibilityStatus")
        if self.eligible is not None and not isinstance(self.eligible, bool):
            raise TypeError("eligible must be a bool or None")
        if not isinstance(self.rule_set_status, RuleSetStatus):
            raise TypeError("rule_set_status must be a RuleSetStatus")
        if not isinstance(self.metadata, ResultMetadata):
            raise TypeError("metadata must be a ResultMetadata")
        if self.metadata.decision_trace is None:
            raise ValueError("eligibility metadata must include a decision trace")

        expected_decision = _decision_for_status(self.status)
        normalized_decision = self.decision or expected_decision
        if not isinstance(normalized_decision, EligibilityDecision):
            raise TypeError("decision must be an EligibilityDecision")
        if self.decision is not None and normalized_decision is not expected_decision:
            raise ValueError("decision is inconsistent with legacy status")
        expected_eligibility = {
            EligibilityDecision.ELIGIBLE: True,
            EligibilityDecision.INELIGIBLE: False,
            EligibilityDecision.CONDITIONAL: None,
            EligibilityDecision.REQUIRES_ADVISOR_REVIEW: None,
            EligibilityDecision.HUMAN_REVIEW_REQUIRED: None,
            EligibilityDecision.UNSUPPORTED: None,
        }[normalized_decision]
        if self.eligible is not expected_eligibility:
            raise ValueError(
                f"eligible value {self.eligible!r} is inconsistent with "
                f"{normalized_decision.value}"
            )
        if not isinstance(self.intent, RegistrationIntent):
            raise TypeError("intent must be a RegistrationIntent")
        if not isinstance(self.horizon, EvaluationHorizon):
            raise TypeError("horizon must be an EvaluationHorizon")
        normalized_conditions = tuple(self.conditions)
        if not all(
            isinstance(condition, FutureCondition)
            for condition in normalized_conditions
        ):
            raise TypeError("conditions must contain FutureCondition values")
        object.__setattr__(self, "decision", normalized_decision)
        object.__setattr__(self, "conditions", normalized_conditions)

        normalized_results = tuple(self.rule_results)
        if not all(
            isinstance(result, RuleEvaluationResult) for result in normalized_results
        ):
            raise TypeError(
                "rule_results must contain only RuleEvaluationResult values"
            )
        result_ids = tuple(result.rule_id for result in normalized_results)
        if len(result_ids) != len(set(result_ids)):
            raise ValueError("rule result IDs must be unique")
        object.__setattr__(
            self,
            "rule_results",
            tuple(sorted(normalized_results, key=lambda result: result.rule_id)),
        )

    @property
    def authoritative(self) -> bool:
        return self.metadata.authoritative

    @property
    def requires_human_review(self) -> bool:
        return self.metadata.requires_human_review

    @property
    def reason_codes(self) -> tuple[ReasonCode, ...]:
        return self.metadata.reason_codes

    @property
    def warnings(self) -> tuple[ReasonCode, ...]:
        return self.metadata.warnings

    @property
    def satisfied_rules(self) -> tuple[RuleEvaluationResult, ...]:
        return tuple(
            result
            for result in self.rule_results
            if result.outcome is EvaluationOutcome.SATISFIED
        )

    @property
    def failed_rules(self) -> tuple[RuleEvaluationResult, ...]:
        return tuple(
            result
            for result in self.rule_results
            if result.outcome is EvaluationOutcome.UNSATISFIED
        )

    @property
    def indeterminate_rules(self) -> tuple[RuleEvaluationResult, ...]:
        return tuple(
            result
            for result in self.rule_results
            if result.outcome is EvaluationOutcome.INDETERMINATE
        )

    @property
    def satisfied_rule_ids(self) -> tuple[str, ...]:
        return tuple(result.rule_id for result in self.satisfied_rules)

    @property
    def failed_rule_ids(self) -> tuple[str, ...]:
        return tuple(result.rule_id for result in self.failed_rules)

    @property
    def indeterminate_rule_ids(self) -> tuple[str, ...]:
        return tuple(result.rule_id for result in self.indeterminate_rules)

    def to_dict(self) -> dict[str, object]:
        return {
            "target_course": self.target_course.course_id,
            "status": self.status.value,
            "decision": self.decision.value,
            "eligible": self.eligible,
            "intent": self.intent.value,
            "horizon": self.horizon.value,
            "conditions": [condition.to_dict() for condition in self.conditions],
            "rule_set_status": self.rule_set_status.value,
            "metadata": self.metadata.to_dict(),
            "rule_results": [result.to_dict() for result in self.rule_results],
        }


def _unique_reason_codes(
    reason_codes: tuple[ReasonCode, ...],
) -> tuple[ReasonCode, ...]:
    return tuple(dict.fromkeys(reason_codes))


def _decision_for_status(status: EligibilityStatus) -> EligibilityDecision:
    return {
        EligibilityStatus.ELIGIBLE: EligibilityDecision.ELIGIBLE,
        EligibilityStatus.NOT_ELIGIBLE: EligibilityDecision.INELIGIBLE,
        EligibilityStatus.ALREADY_COMPLETED: EligibilityDecision.INELIGIBLE,
        EligibilityStatus.CURRENTLY_REGISTERED: EligibilityDecision.INELIGIBLE,
        EligibilityStatus.BLOCKED_BY_UNVERIFIED_RULE: EligibilityDecision.HUMAN_REVIEW_REQUIRED,
        EligibilityStatus.HUMAN_REVIEW_REQUIRED: EligibilityDecision.HUMAN_REVIEW_REQUIRED,
        EligibilityStatus.UNSUPPORTED: EligibilityDecision.UNSUPPORTED,
        EligibilityStatus.CONDITIONAL: EligibilityDecision.CONDITIONAL,
        EligibilityStatus.REQUIRES_ADVISOR_REVIEW: EligibilityDecision.REQUIRES_ADVISOR_REVIEW,
    }[status]


__all__ = [
    "CourseEligibilityRuleSet",
    "EligibilityContext",
    "EligibilityDecision",
    "EligibilityRequest",
    "EligibilityResult",
    "EligibilityStatus",
    "EvaluationHorizon",
    "ProposedTermContext",
    "RegistrationIntent",
    "RuleSetStatus",
]
