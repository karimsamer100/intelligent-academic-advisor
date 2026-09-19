"""Typed contracts for deterministic single-semester planning."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from .candidates import CandidateCourse, CandidateGenerationRequest
from .conditions import FutureCondition
from .context import EvaluationHorizon, RegistrationIntent
from .course import CourseIdentity
from .ranking import PriorityFactors
from .results import ResultMetadata
from .semester import (
    SemesterLoadPolicy,
    SemesterValidationResult,
    TermType,
)
from .student import StudentState
from .trace import DecisionTrace, TraceValue
from .reasons import ReasonCode


class PlanningCoverageStatus(StrEnum):
    """Availability of one planning input, not academic truth itself."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class PlanningCoverage:
    """Coverage of academic and operational inputs used by a plan."""

    academic_requirements: PlanningCoverageStatus
    candidate_generation: PlanningCoverageStatus
    eligibility_rules: PlanningCoverageStatus
    dependency: PlanningCoverageStatus
    offering: PlanningCoverageStatus = PlanningCoverageStatus.UNAVAILABLE
    timetable: PlanningCoverageStatus = PlanningCoverageStatus.UNAVAILABLE
    search: PlanningCoverageStatus = PlanningCoverageStatus.COMPLETE
    projection: PlanningCoverageStatus = PlanningCoverageStatus.COMPLETE

    def __post_init__(self) -> None:
        for name in (
            "academic_requirements",
            "candidate_generation",
            "eligibility_rules",
            "dependency",
            "offering",
            "timetable",
            "search",
            "projection",
        ):
            if not isinstance(getattr(self, name), PlanningCoverageStatus):
                raise TypeError(f"{name} must be a PlanningCoverageStatus")

    @property
    def overall(self) -> PlanningCoverageStatus:
        inputs = (
            self.academic_requirements,
            self.candidate_generation,
            self.eligibility_rules,
            self.dependency,
            self.offering,
            self.timetable,
            self.search,
        )
        values = (*inputs, self.projection)
        if all(value is PlanningCoverageStatus.UNAVAILABLE for value in inputs):
            if self.projection is PlanningCoverageStatus.INCOMPLETE:
                return PlanningCoverageStatus.INCOMPLETE
            return PlanningCoverageStatus.UNAVAILABLE
        if any(value is not PlanningCoverageStatus.COMPLETE for value in values):
            return PlanningCoverageStatus.INCOMPLETE
        return PlanningCoverageStatus.COMPLETE

    @property
    def academic_overall(self) -> PlanningCoverageStatus:
        """Coverage needed to establish academic plan validity.

        Offering and timetable coverage are intentionally excluded.  Their
        absence prevents registration readiness, but does not change whether
        the selected course set is academically valid.
        """

        inputs = (
            self.academic_requirements,
            self.candidate_generation,
            self.eligibility_rules,
            self.dependency,
            self.search,
        )
        values = (*inputs, self.projection)
        if all(value is PlanningCoverageStatus.UNAVAILABLE for value in inputs):
            if self.projection is PlanningCoverageStatus.INCOMPLETE:
                return PlanningCoverageStatus.INCOMPLETE
            return PlanningCoverageStatus.UNAVAILABLE
        if any(value is not PlanningCoverageStatus.COMPLETE for value in values):
            return PlanningCoverageStatus.INCOMPLETE
        return PlanningCoverageStatus.COMPLETE

    def to_dict(self) -> dict[str, object]:
        return {
            "academic_requirements": self.academic_requirements.value,
            "candidate_generation": self.candidate_generation.value,
            "eligibility_rules": self.eligibility_rules.value,
            "dependency": self.dependency.value,
            "offering": self.offering.value,
            "timetable": self.timetable.value,
            "search": self.search.value,
            "projection": self.projection.value,
            "overall": self.overall.value,
            "academic_overall": self.academic_overall.value,
        }


class LoadPreference(StrEnum):
    """Product preference for how much of an academic capacity to pursue."""

    LIGHT = "LIGHT"
    BALANCED = "BALANCED"
    MAXIMIZE_ALLOWED = "MAXIMIZE_ALLOWED"


@dataclass(frozen=True, slots=True)
class PlanningPreferencePolicy:
    """Configurable product policy for relative light/balanced targets.

    These ratios are planning preferences, not university load rules.  The
    SemesterLoadPolicy remains the only source of legal academic limits.
    """

    light_ratio: float = 0.5
    balanced_ratio: float = 0.75

    def __post_init__(self) -> None:
        for name in ("light_ratio", "balanced_ratio"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric")
            if not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{name} must be greater than 0 and at most 1")

    def to_dict(self) -> dict[str, object]:
        return {
            "light_ratio": self.light_ratio,
            "balanced_ratio": self.balanced_ratio,
        }


@dataclass(frozen=True, slots=True)
class PlanningPreferences:
    """Soft planner preferences; none can relax academic validation."""

    load_preference: LoadPreference = LoadPreference.BALANCED
    target_credit_hours: int | float | None = None
    maximum_preferred_credit_hours: int | float | None = None
    maximum_preferred_course_count: int | None = None
    include_review_candidates: bool = False
    preference_policy: PlanningPreferencePolicy = field(
        default_factory=PlanningPreferencePolicy
    )

    def __post_init__(self) -> None:
        if not isinstance(self.load_preference, LoadPreference):
            raise TypeError("load_preference must be a LoadPreference")
        for name in (
            "target_credit_hours",
            "maximum_preferred_credit_hours",
        ):
            value = getattr(self, name)
            if value is not None:
                _validate_number(value, name)
        if self.maximum_preferred_course_count is not None and (
            isinstance(self.maximum_preferred_course_count, bool)
            or not isinstance(self.maximum_preferred_course_count, int)
            or self.maximum_preferred_course_count < 0
        ):
            raise ValueError(
                "maximum_preferred_course_count must be a non-negative integer"
            )
        if not isinstance(self.include_review_candidates, bool):
            raise TypeError("include_review_candidates must be a bool")
        if not isinstance(self.preference_policy, PlanningPreferencePolicy):
            raise TypeError("preference_policy must be a PlanningPreferencePolicy")

    def preferred_credit_target(
        self, legal_max_credit_hours: int | float | None
    ) -> int | float | None:
        """Return a transparent soft target derived from legal capacity."""

        if self.target_credit_hours is not None:
            return self.target_credit_hours
        if self.maximum_preferred_credit_hours is not None:
            return self.maximum_preferred_credit_hours
        if legal_max_credit_hours is None:
            return None
        if self.load_preference is LoadPreference.MAXIMIZE_ALLOWED:
            return legal_max_credit_hours
        ratio = (
            self.preference_policy.light_ratio
            if self.load_preference is LoadPreference.LIGHT
            else self.preference_policy.balanced_ratio
        )
        return max(1, math.ceil(legal_max_credit_hours * ratio))

    def to_dict(self) -> dict[str, object]:
        return {
            "load_preference": self.load_preference.value,
            "target_credit_hours": self.target_credit_hours,
            "maximum_preferred_credit_hours": self.maximum_preferred_credit_hours,
            "maximum_preferred_course_count": self.maximum_preferred_course_count,
            "include_review_candidates": self.include_review_candidates,
            "preference_policy": self.preference_policy.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PlanningSearchPolicy:
    """Bounded, deterministic search controls rather than academic rules."""

    max_candidates_considered: int = 24
    max_combinations_evaluated: int = 256
    max_alternatives: int = 2

    def __post_init__(self) -> None:
        for name in (
            "max_candidates_considered",
            "max_combinations_evaluated",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(self.max_alternatives, bool)
            or not isinstance(self.max_alternatives, int)
            or self.max_alternatives < 0
        ):
            raise ValueError("max_alternatives must be a non-negative integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "max_candidates_considered": self.max_candidates_considered,
            "max_combinations_evaluated": self.max_combinations_evaluated,
            "max_alternatives": self.max_alternatives,
        }


class PlanStatus(StrEnum):
    """Semantic status of a constructed single-semester plan."""

    VALID = "VALID"
    CONDITIONAL = "CONDITIONAL"
    PARTIAL = "PARTIAL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NO_FEASIBLE_PLAN = "NO_FEASIBLE_PLAN"
    UNSUPPORTED = "UNSUPPORTED"


class PlanAlternativeType(StrEnum):
    PRIMARY = "PRIMARY"
    LOWER_LOAD = "LOWER_LOAD"
    ALTERNATE_ELECTIVE = "ALTERNATE_ELECTIVE"
    CONDITIONAL_PATH = "CONDITIONAL_PATH"
    REVIEW_PATH = "REVIEW_PATH"


class PlanSelectionReasonCode(StrEnum):
    REQUIRED_PROGRESS = "REQUIRED_PROGRESS"
    ZERO_CREDIT_PROGRESS = "ZERO_CREDIT_PROGRESS"
    ELECTIVE_PROGRESS = "ELECTIVE_PROGRESS"
    CONCENTRATION_PROGRESS = "CONCENTRATION_PROGRESS"
    DEPENDENCY_UNLOCK = "DEPENDENCY_UNLOCK"
    RETAKE_REQUEST = "RETAKE_REQUEST"
    PRIORITY_ORDER = "PRIORITY_ORDER"
    PREFERENCE_FIT = "PREFERENCE_FIT"
    CONDITIONAL_FUTURE = "CONDITIONAL_FUTURE"


class PlanExclusionCode(StrEnum):
    ACADEMICALLY_INELIGIBLE = "ACADEMICALLY_INELIGIBLE"
    LOAD_LIMIT = "LOAD_LIMIT"
    LOWER_PRIORITY = "LOWER_PRIORITY"
    USER_LOAD_PREFERENCE = "USER_LOAD_PREFERENCE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"
    DUPLICATE = "DUPLICATE"
    CONDITIONAL_NOT_NEEDED = "CONDITIONAL_NOT_NEEDED"
    SEARCH_LIMIT = "SEARCH_LIMIT"
    SCENARIO_EXCLUDED = "SCENARIO_EXCLUDED"


class PlanDiagnosticCode(StrEnum):
    NO_CANDIDATES = "NO_CANDIDATES"
    NO_FEASIBLE_PLAN = "NO_FEASIBLE_PLAN"
    PLAN_TARGET_NOT_REACHED = "PLAN_TARGET_NOT_REACHED"
    COVERAGE_INCOMPLETE = "COVERAGE_INCOMPLETE"
    SEARCH_LIMIT_REACHED = "SEARCH_LIMIT_REACHED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"
    OFFERING_UNAVAILABLE = "OFFERING_UNAVAILABLE"
    TIMETABLE_UNAVAILABLE = "TIMETABLE_UNAVAILABLE"
    NO_PROGRESS = "NO_PROGRESS"
    HORIZON_REACHED = "HORIZON_REACHED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True, slots=True)
class PlanTargetDeviation:
    requested_credit_hours: int | float
    achieved_credit_hours: int | float
    difference: int | float
    reason_codes: tuple[ReasonCode, ...] = ()

    def __post_init__(self) -> None:
        _validate_number(self.requested_credit_hours, "requested_credit_hours")
        _validate_number(self.achieved_credit_hours, "achieved_credit_hours")
        _validate_numeric(self.difference, "difference")
        reasons = tuple(dict.fromkeys(self.reason_codes))
        if not all(isinstance(reason, ReasonCode) for reason in reasons):
            raise TypeError("reason_codes must contain ReasonCode values")
        object.__setattr__(self, "reason_codes", reasons)

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_credit_hours": self.requested_credit_hours,
            "achieved_credit_hours": self.achieved_credit_hours,
            "difference": self.difference,
            "absolute_difference": abs(self.difference),
            "reason_codes": [reason.value for reason in self.reason_codes],
        }


@dataclass(frozen=True, slots=True)
class PlanDiagnostic:
    code: PlanDiagnosticCode
    course: CourseIdentity | None = None
    expected: TraceValue = None
    actual: TraceValue = None
    reason_codes: tuple[ReasonCode, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, PlanDiagnosticCode):
            raise TypeError("code must be a PlanDiagnosticCode")
        if self.course is not None and not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity or None")
        reasons = tuple(dict.fromkeys(self.reason_codes))
        if not all(isinstance(reason, ReasonCode) for reason in reasons):
            raise TypeError("reason_codes must contain ReasonCode values")
        object.__setattr__(self, "reason_codes", reasons)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "course": self.course.course_id if self.course else None,
            "expected": self.expected,
            "actual": self.actual,
            "reason_codes": [reason.value for reason in self.reason_codes],
        }


@dataclass(frozen=True, slots=True)
class PlanExclusion:
    course: CourseIdentity
    code: PlanExclusionCode
    candidate: CandidateCourse | None = None
    reason_codes: tuple[ReasonCode, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")
        if not isinstance(self.code, PlanExclusionCode):
            raise TypeError("code must be a PlanExclusionCode")
        if self.candidate is not None and not isinstance(
            self.candidate, CandidateCourse
        ):
            raise TypeError("candidate must be a CandidateCourse or None")
        if self.candidate is not None and self.candidate.identity != self.course:
            raise ValueError("candidate identity must match course")
        reasons = tuple(dict.fromkeys(self.reason_codes))
        if not all(isinstance(reason, ReasonCode) for reason in reasons):
            raise TypeError("reason_codes must contain ReasonCode values")
        object.__setattr__(self, "reason_codes", reasons)

    def to_dict(self) -> dict[str, object]:
        return {
            "course": self.course.course_id,
            "code": self.code.value,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "reason_codes": [reason.value for reason in self.reason_codes],
        }


@dataclass(frozen=True, slots=True)
class SelectedPlanCourse:
    candidate: CandidateCourse
    priority_factors: PriorityFactors
    registration_intent: RegistrationIntent
    why_selected: tuple[PlanSelectionReasonCode, ...]
    conditions: tuple[FutureCondition, ...] = ()
    trace: DecisionTrace | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, CandidateCourse):
            raise TypeError("candidate must be a CandidateCourse")
        if not isinstance(self.priority_factors, PriorityFactors):
            raise TypeError("priority_factors must be PriorityFactors")
        if not isinstance(self.registration_intent, RegistrationIntent):
            raise TypeError("registration_intent must be a RegistrationIntent")
        reasons = tuple(dict.fromkeys(self.why_selected))
        if not all(isinstance(item, PlanSelectionReasonCode) for item in reasons):
            raise TypeError("why_selected must contain PlanSelectionReasonCode values")
        conditions = tuple(self.conditions)
        if not all(isinstance(item, FutureCondition) for item in conditions):
            raise TypeError("conditions must contain FutureCondition values")
        if self.trace is not None and not isinstance(self.trace, DecisionTrace):
            raise TypeError("trace must be a DecisionTrace or None")
        object.__setattr__(
            self,
            "why_selected",
            tuple(sorted(reasons, key=lambda item: item.value)),
        )
        object.__setattr__(self, "conditions", _unique_conditions(conditions))

    @property
    def identity(self) -> CourseIdentity:
        return self.candidate.identity

    def to_dict(self) -> dict[str, object]:
        return {
            "course": self.identity.course_id,
            "registration_intent": self.registration_intent.value,
            "candidate": self.candidate.to_dict(),
            "priority_factors": self.priority_factors.to_dict(),
            "why_selected": [item.value for item in self.why_selected],
            "conditions": [item.to_dict() for item in self.conditions],
            "trace": self.trace.to_dict() if self.trace else None,
        }


@dataclass(frozen=True, slots=True)
class PlanAlternative:
    alternative_type: PlanAlternativeType
    selected_courses: tuple[SelectedPlanCourse, ...]
    validation_result: SemesterValidationResult
    status: PlanStatus
    conditions: tuple[FutureCondition, ...] = ()
    deviation: PlanTargetDeviation | None = None
    trace: DecisionTrace | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.alternative_type, PlanAlternativeType):
            raise TypeError("alternative_type must be a PlanAlternativeType")
        courses = tuple(self.selected_courses)
        if not all(isinstance(item, SelectedPlanCourse) for item in courses):
            raise TypeError("selected_courses must contain SelectedPlanCourse values")
        if len({item.identity for item in courses}) != len(courses):
            raise ValueError("alternative cannot contain duplicate courses")
        if not isinstance(self.validation_result, SemesterValidationResult):
            raise TypeError("validation_result must be a SemesterValidationResult")
        if not isinstance(self.status, PlanStatus):
            raise TypeError("status must be a PlanStatus")
        conditions = tuple(self.conditions)
        if not all(isinstance(item, FutureCondition) for item in conditions):
            raise TypeError("conditions must contain FutureCondition values")
        if self.deviation is not None and not isinstance(
            self.deviation, PlanTargetDeviation
        ):
            raise TypeError("deviation must be a PlanTargetDeviation or None")
        if self.trace is not None and not isinstance(self.trace, DecisionTrace):
            raise TypeError("trace must be a DecisionTrace or None")
        object.__setattr__(self, "selected_courses", courses)
        object.__setattr__(self, "conditions", _unique_conditions(conditions))

    def to_dict(self) -> dict[str, object]:
        return {
            "alternative_type": self.alternative_type.value,
            "status": self.status.value,
            "selected_courses": [item.to_dict() for item in self.selected_courses],
            "validation_result": self.validation_result.to_dict(),
            "conditions": [item.to_dict() for item in self.conditions],
            "deviation": self.deviation.to_dict() if self.deviation else None,
            "trace": self.trace.to_dict() if self.trace else None,
        }


@dataclass(frozen=True, slots=True)
class SingleSemesterPlanningRequest:
    student: StudentState
    term_type: TermType
    load_policy: SemesterLoadPolicy
    candidate_request: CandidateGenerationRequest
    preferences: PlanningPreferences = field(default_factory=PlanningPreferences)
    search_policy: PlanningSearchPolicy = field(default_factory=PlanningSearchPolicy)
    term_id: str | None = None
    excluded_courses: tuple[CourseIdentity, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.student, StudentState):
            raise TypeError("student must be a StudentState")
        if not isinstance(self.term_type, TermType):
            raise TypeError("term_type must be a TermType")
        if not isinstance(self.load_policy, SemesterLoadPolicy):
            raise TypeError("load_policy must be a SemesterLoadPolicy")
        if not isinstance(self.candidate_request, CandidateGenerationRequest):
            raise TypeError("candidate_request must be a CandidateGenerationRequest")
        if self.candidate_request.student != self.student:
            raise ValueError(
                "candidate request and planning request students must match"
            )
        if (
            self.load_policy.regulation is not self.student.regulation
            or self.load_policy.program != self.student.program
        ):
            raise ValueError("load policy scope must match student scope")
        if not isinstance(self.preferences, PlanningPreferences):
            raise TypeError("preferences must be PlanningPreferences")
        if not isinstance(self.search_policy, PlanningSearchPolicy):
            raise TypeError("search_policy must be PlanningSearchPolicy")
        if self.term_id is not None and (
            not isinstance(self.term_id, str) or not self.term_id.strip()
        ):
            raise ValueError("term_id must be non-empty when provided")
        excluded = tuple(self.excluded_courses)
        if not all(isinstance(item, CourseIdentity) for item in excluded):
            raise TypeError("excluded_courses must contain CourseIdentity values")
        if len(excluded) != len(set(excluded)):
            raise ValueError("excluded_courses must be unique")
        if any(
            item.regulation is not self.student.regulation
            or item.program != self.student.program
            for item in excluded
        ):
            raise ValueError("excluded course scope must match student scope")
        object.__setattr__(
            self,
            "excluded_courses",
            tuple(sorted(excluded, key=lambda item: item.course_id)),
        )

    @property
    def horizon(self) -> EvaluationHorizon:
        return self.candidate_request.context.horizon

    @property
    def effective_term_id(self) -> str | None:
        return self.term_id or self.candidate_request.context.term_id

    def to_dict(self) -> dict[str, object]:
        return {
            "student_id": self.student.student_id,
            "term_type": self.term_type.value,
            "term_id": self.effective_term_id,
            "horizon": self.horizon.value,
            "load_policy": self.load_policy.policy_id,
            "preferences": self.preferences.to_dict(),
            "search_policy": self.search_policy.to_dict(),
            "excluded_courses": [item.course_id for item in self.excluded_courses],
        }


@dataclass(frozen=True, slots=True)
class SingleSemesterPlanResult:
    status: PlanStatus
    selected_courses: tuple[SelectedPlanCourse, ...]
    validation_result: SemesterValidationResult | None
    alternatives: tuple[PlanAlternative, ...]
    achieved_credit_hours: int | float | None
    achieved_course_count: int
    preferences: PlanningPreferences
    conditions: tuple[FutureCondition, ...]
    review_items: tuple[PlanDiagnostic, ...]
    exclusions: tuple[PlanExclusion, ...]
    coverage: PlanningCoverage
    metadata: ResultMetadata
    trace: DecisionTrace
    deviation: PlanTargetDeviation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, PlanStatus):
            raise TypeError("status must be a PlanStatus")
        courses = tuple(self.selected_courses)
        if not all(isinstance(item, SelectedPlanCourse) for item in courses):
            raise TypeError("selected_courses must contain SelectedPlanCourse values")
        if len({item.identity for item in courses}) != len(courses):
            raise ValueError("selected_courses must contain unique identities")
        if self.validation_result is not None and not isinstance(
            self.validation_result, SemesterValidationResult
        ):
            raise TypeError(
                "validation_result must be a SemesterValidationResult or None"
            )
        alternatives = tuple(self.alternatives)
        if not all(isinstance(item, PlanAlternative) for item in alternatives):
            raise TypeError("alternatives must contain PlanAlternative values")
        if any(
            item.alternative_type is PlanAlternativeType.PRIMARY
            for item in alternatives
        ):
            raise ValueError("alternatives cannot contain PRIMARY")
        if self.achieved_credit_hours is not None:
            _validate_number(self.achieved_credit_hours, "achieved_credit_hours")
        if (
            isinstance(self.achieved_course_count, bool)
            or not isinstance(self.achieved_course_count, int)
            or self.achieved_course_count < 0
        ):
            raise ValueError("achieved_course_count must be a non-negative integer")
        if not isinstance(self.preferences, PlanningPreferences):
            raise TypeError("preferences must be PlanningPreferences")
        conditions = tuple(self.conditions)
        if not all(isinstance(item, FutureCondition) for item in conditions):
            raise TypeError("conditions must contain FutureCondition values")
        review_items = tuple(self.review_items)
        if not all(isinstance(item, PlanDiagnostic) for item in review_items):
            raise TypeError("review_items must contain PlanDiagnostic values")
        exclusions = tuple(self.exclusions)
        if not all(isinstance(item, PlanExclusion) for item in exclusions):
            raise TypeError("exclusions must contain PlanExclusion values")
        if not isinstance(self.coverage, PlanningCoverage):
            raise TypeError("coverage must be PlanningCoverage")
        if not isinstance(self.metadata, ResultMetadata):
            raise TypeError("metadata must be ResultMetadata")
        if not isinstance(self.trace, DecisionTrace):
            raise TypeError("trace must be a DecisionTrace")
        if self.deviation is not None and not isinstance(
            self.deviation, PlanTargetDeviation
        ):
            raise TypeError("deviation must be a PlanTargetDeviation or None")
        object.__setattr__(self, "selected_courses", courses)
        object.__setattr__(self, "alternatives", alternatives)
        object.__setattr__(self, "conditions", _unique_conditions(conditions))
        object.__setattr__(self, "review_items", review_items)
        object.__setattr__(self, "exclusions", exclusions)

    @property
    def registration_ready(self) -> bool:
        """Whether all operational coverage and authority gates are present."""

        return (
            self.status is PlanStatus.VALID
            and self.coverage.overall is PlanningCoverageStatus.COMPLETE
            and self.metadata.authoritative
        )

    @property
    def diagnostics(self) -> tuple[PlanDiagnostic, ...]:
        """Structured planner diagnostics; ``review_items`` remains the field.

        The compatibility field is retained because review items were the
        initial result contract.  This alias gives API/tool consumers a
        semantically clearer name without maintaining a second collection.
        """

        return self.review_items

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "selected_courses": [item.to_dict() for item in self.selected_courses],
            "validation_result": (
                self.validation_result.to_dict()
                if self.validation_result is not None
                else None
            ),
            "alternatives": [item.to_dict() for item in self.alternatives],
            "achieved_credit_hours": self.achieved_credit_hours,
            "achieved_course_count": self.achieved_course_count,
            "preferences": self.preferences.to_dict(),
            "conditions": [item.to_dict() for item in self.conditions],
            "review_items": [item.to_dict() for item in self.review_items],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "exclusions": [item.to_dict() for item in self.exclusions],
            "coverage": self.coverage.to_dict(),
            "deviation": self.deviation.to_dict() if self.deviation else None,
            "metadata": self.metadata.to_dict(),
            "registration_ready": self.registration_ready,
            "trace": self.trace.to_dict(),
        }


def _validate_number(value: object, name: str) -> None:
    _validate_numeric(value, name)
    if value < 0:
        raise ValueError(f"{name} must be finite and non-negative")


def _validate_numeric(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _unique_conditions(
    conditions: tuple[FutureCondition, ...],
) -> tuple[FutureCondition, ...]:
    result: list[FutureCondition] = []
    seen: set[str] = set()
    for condition in conditions:
        key = repr(condition.to_dict())
        if key not in seen:
            seen.add(key)
            result.append(condition)
    return tuple(result)


__all__ = [
    "LoadPreference",
    "PlanAlternative",
    "PlanAlternativeType",
    "PlanDiagnostic",
    "PlanDiagnosticCode",
    "PlanExclusion",
    "PlanExclusionCode",
    "PlanSelectionReasonCode",
    "PlanStatus",
    "PlanTargetDeviation",
    "PlanningCoverage",
    "PlanningCoverageStatus",
    "PlanningPreferencePolicy",
    "PlanningPreferences",
    "PlanningSearchPolicy",
    "SelectedPlanCourse",
    "SingleSemesterPlanResult",
    "SingleSemesterPlanningRequest",
]
