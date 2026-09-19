"""Typed contracts for validating one proposed academic term."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from .conditions import FutureCondition
from .context import EvaluationHorizon, RegistrationIntent
from .course import Course, CourseIdentity, Program, Regulation
from .eligibility import CourseEligibilityRuleSet, EligibilityResult
from .lifecycle import ApprovalStatus, VerificationStatus
from .provenance import Provenance
from .reasons import ReasonCode
from .results import ResultMetadata
from .student import StudentState
from .trace import DecisionTrace, TraceValue


class TermType(StrEnum):
    """Broad term categories used by load policy, not course offering."""

    MAIN = "MAIN"
    SUMMER = "SUMMER"


class SemesterValidationStatus(StrEnum):
    """Overall or component status for a proposed-term validation."""

    VALID = "VALID"
    INVALID = "INVALID"
    CONDITIONAL = "CONDITIONAL"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"


class SemesterIssueCode(StrEnum):
    """Machine-readable issues found while validating a proposed term."""

    DUPLICATE_COURSE = "DUPLICATE_COURSE"
    UNKNOWN_COURSE_CREDITS = "UNKNOWN_COURSE_CREDITS"
    LOAD_POLICY_UNRESOLVED = "LOAD_POLICY_UNRESOLVED"
    LOAD_LIMIT_EXCEEDED = "LOAD_LIMIT_EXCEEDED"
    ELIGIBILITY_FAILED = "ELIGIBILITY_FAILED"
    ELIGIBILITY_UNRESOLVED = "ELIGIBILITY_UNRESOLVED"
    UNSUPPORTED_ELIGIBILITY = "UNSUPPORTED_ELIGIBILITY"


@dataclass(frozen=True, slots=True)
class ProposedCourse:
    """One course registration request inside a proposed term."""

    course: Course
    registration_intent: RegistrationIntent = RegistrationIntent.NORMAL
    credit_hours: int | float | None = None
    credit_hours_known: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.course, Course):
            raise TypeError("course must be a Course")
        if not isinstance(self.registration_intent, RegistrationIntent):
            raise TypeError("registration_intent must be a RegistrationIntent")
        if not isinstance(self.credit_hours_known, bool):
            raise TypeError("credit_hours_known must be a bool")
        if self.credit_hours_known and self.credit_hours is None:
            object.__setattr__(self, "credit_hours", self.course.credit_hours)
        if self.credit_hours is not None:
            if isinstance(self.credit_hours, bool) or not isinstance(
                self.credit_hours, (int, float)
            ):
                raise TypeError("credit_hours must be numeric or None")
            if not math.isfinite(self.credit_hours) or self.credit_hours < 0:
                raise ValueError("credit_hours must be finite and non-negative")
        if not self.credit_hours_known:
            object.__setattr__(self, "credit_hours", None)

    @property
    def identity(self) -> CourseIdentity:
        return self.course.identity

    def to_dict(self) -> dict[str, object]:
        return {
            "course": self.identity.course_id,
            "registration_intent": self.registration_intent.value,
            "credit_hours": self.credit_hours,
            "credit_hours_known": self.credit_hours_known,
        }


@dataclass(frozen=True, slots=True)
class ProposedSemester:
    """Immutable proposed term; duplicate entries remain visible for validation."""

    term_type: TermType
    courses: tuple[ProposedCourse, ...]
    term_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.term_type, TermType):
            raise TypeError("term_type must be a TermType")
        courses = tuple(self.courses)
        if not all(isinstance(item, ProposedCourse) for item in courses):
            raise TypeError("courses must contain ProposedCourse values")
        if self.term_id is not None and (
            not isinstance(self.term_id, str) or not self.term_id.strip()
        ):
            raise ValueError("term_id must be non-empty when provided")
        object.__setattr__(
            self,
            "courses",
            tuple(
                sorted(
                    courses,
                    key=lambda item: (
                        item.identity.course_id,
                        item.registration_intent.value,
                        item.credit_hours is None,
                        item.credit_hours if item.credit_hours is not None else 0,
                    ),
                )
            ),
        )

    @property
    def unique_course_ids(self) -> tuple[CourseIdentity, ...]:
        return tuple(
            sorted(
                {item.identity for item in self.courses},
                key=lambda item: item.course_id,
            )
        )

    @property
    def duplicate_course_ids(self) -> tuple[CourseIdentity, ...]:
        counts: dict[CourseIdentity, int] = {}
        for item in self.courses:
            counts[item.identity] = counts.get(item.identity, 0) + 1
        return tuple(
            sorted(
                (identity for identity, count in counts.items() if count > 1),
                key=lambda item: item.course_id,
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "term_type": self.term_type.value,
            "term_id": self.term_id,
            "courses": [item.to_dict() for item in self.courses],
        }


@dataclass(frozen=True, slots=True)
class LoadBand:
    """One GPA-selected alternative-cap band."""

    band_id: str
    gpa_min: int | float | None
    gpa_max_exclusive: int | float | None
    max_credit_hours: int | float
    max_course_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.band_id, str) or not self.band_id.strip():
            raise ValueError("band_id must be non-empty")
        for name in ("gpa_min", "gpa_max_exclusive"):
            value = getattr(self, name)
            if value is not None:
                _validate_number(value, name)
        if (
            self.gpa_min is not None
            and self.gpa_max_exclusive is not None
            and self.gpa_min >= self.gpa_max_exclusive
        ):
            raise ValueError("GPA band bounds must be ordered")
        _validate_number(self.max_credit_hours, "max_credit_hours", nonnegative=True)
        if (
            isinstance(self.max_course_count, bool)
            or not isinstance(self.max_course_count, int)
            or self.max_course_count < 0
        ):
            raise ValueError("max_course_count must be a non-negative integer")

    def contains_gpa(self, gpa: int | float) -> bool:
        return (self.gpa_min is None or gpa >= self.gpa_min) and (
            self.gpa_max_exclusive is None or gpa < self.gpa_max_exclusive
        )

    def allows(self, credit_hours: int | float, course_count: int) -> bool:
        """Apply the bylaw's OR alternative-cap semantics."""

        return (
            credit_hours <= self.max_credit_hours
            or course_count <= self.max_course_count
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "band_id": self.band_id,
            "gpa_min": self.gpa_min,
            "gpa_max_exclusive": self.gpa_max_exclusive,
            "max_credit_hours": self.max_credit_hours,
            "max_course_count": self.max_course_count,
        }


@dataclass(frozen=True, slots=True)
class SemesterLoadPolicy:
    """Governed load policy consumed by the validator."""

    policy_id: str
    regulation: Regulation
    program: Program
    main_bands: tuple[LoadBand, ...]
    summer_bands: tuple[LoadBand, ...]
    approval_status: ApprovalStatus
    verification_status: VerificationStatus
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id must be non-empty")
        if not isinstance(self.regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(self.program, Program):
            raise TypeError("program must be a Program")
        if not all(
            isinstance(item, LoadBand)
            for item in (*self.main_bands, *self.summer_bands)
        ):
            raise TypeError("load bands must contain LoadBand values")
        if not isinstance(self.approval_status, ApprovalStatus):
            raise TypeError("approval_status must be an ApprovalStatus")
        if not isinstance(self.verification_status, VerificationStatus):
            raise TypeError("verification_status must be a VerificationStatus")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")
        object.__setattr__(self, "main_bands", tuple(self.main_bands))
        object.__setattr__(self, "summer_bands", tuple(self.summer_bands))

    @classmethod
    def regulation_23(
        cls,
        *,
        approval_status: ApprovalStatus = ApprovalStatus.SOURCE_VERIFIED,
        verification_status: VerificationStatus = VerificationStatus.SOURCE_VERIFIED,
        provenance: Provenance | None = None,
    ) -> "SemesterLoadPolicy":
        """Return the explicitly governed Reg23 capability fixture.

        This is an engine policy definition, not a claim that the current
        Academic Data package contains an authoritative load-policy record.
        """

        return cls(
            policy_id="REG23_LOAD_POLICY",
            regulation=Regulation.R23,
            program=Program("CAIE"),
            main_bands=(
                LoadBand("MAIN_GPA_GE_3", 3.0, None, 21, 8),
                LoadBand("MAIN_GPA_GE_2", 2.0, 3.0, 18, 7),
                LoadBand("MAIN_GPA_LT_2", None, 2.0, 14, 5),
            ),
            summer_bands=(
                LoadBand("SUMMER_GPA_GE_3", 3.0, None, 9, 3),
                LoadBand("SUMMER_GPA_LT_3", None, 3.0, 8, 2),
            ),
            approval_status=approval_status,
            verification_status=verification_status,
            provenance=provenance,
        )

    def band_for(self, term_type: TermType, gpa: int | float | None) -> LoadBand | None:
        if not isinstance(term_type, TermType):
            raise TypeError("term_type must be a TermType")
        if gpa is None:
            return None
        bands = self.main_bands if term_type is TermType.MAIN else self.summer_bands
        return next((band for band in bands if band.contains_gpa(gpa)), None)

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "regulation": self.regulation.value,
            "program": str(self.program),
            "main_bands": [item.to_dict() for item in self.main_bands],
            "summer_bands": [item.to_dict() for item in self.summer_bands],
            "approval_status": self.approval_status.value,
            "verification_status": self.verification_status.value,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


@dataclass(frozen=True, slots=True)
class SemesterValidationIssue:
    code: SemesterIssueCode
    course: CourseIdentity | None = None
    expected: TraceValue = None
    actual: TraceValue = None
    reason_codes: tuple[ReasonCode, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, SemesterIssueCode):
            raise TypeError("code must be a SemesterIssueCode")
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
class SemesterLoadResult:
    status: SemesterValidationStatus
    term_type: TermType
    gpa: int | float | None
    band_id: str | None
    total_credit_hours: int | float | None
    course_count: int
    max_credit_hours: int | float | None
    max_course_count: int | None
    reason_codes: tuple[ReasonCode, ...]
    trace: DecisionTrace

    def __post_init__(self) -> None:
        if not isinstance(self.status, SemesterValidationStatus):
            raise TypeError("status must be a SemesterValidationStatus")
        if not isinstance(self.term_type, TermType):
            raise TypeError("term_type must be a TermType")
        if self.total_credit_hours is not None:
            _validate_number(
                self.total_credit_hours, "total_credit_hours", nonnegative=True
            )
        if (
            isinstance(self.course_count, bool)
            or not isinstance(self.course_count, int)
            or self.course_count < 0
        ):
            raise ValueError("course_count must be a non-negative integer")
        if self.max_credit_hours is not None:
            _validate_number(
                self.max_credit_hours, "max_credit_hours", nonnegative=True
            )
        if self.max_course_count is not None and (
            isinstance(self.max_course_count, bool)
            or not isinstance(self.max_course_count, int)
            or self.max_course_count < 0
        ):
            raise ValueError("max_course_count must be a non-negative integer or None")
        if not isinstance(self.trace, DecisionTrace):
            raise TypeError("trace must be a DecisionTrace")
        object.__setattr__(
            self, "reason_codes", tuple(dict.fromkeys(self.reason_codes))
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "term_type": self.term_type.value,
            "gpa": self.gpa,
            "band_id": self.band_id,
            "total_credit_hours": self.total_credit_hours,
            "course_count": self.course_count,
            "max_credit_hours": self.max_credit_hours,
            "max_course_count": self.max_course_count,
            "reason_codes": [reason.value for reason in self.reason_codes],
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SemesterCourseResult:
    proposed_course: ProposedCourse
    eligibility: EligibilityResult

    def __post_init__(self) -> None:
        if not isinstance(self.proposed_course, ProposedCourse):
            raise TypeError("proposed_course must be a ProposedCourse")
        if not isinstance(self.eligibility, EligibilityResult):
            raise TypeError("eligibility must be an EligibilityResult")

    def to_dict(self) -> dict[str, object]:
        return {
            "course": self.proposed_course.to_dict(),
            "eligibility": self.eligibility.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SemesterValidationRequest:
    student: StudentState
    semester: ProposedSemester
    rule_sets: tuple[CourseEligibilityRuleSet, ...]
    load_policy: SemesterLoadPolicy
    horizon: EvaluationHorizon = EvaluationHorizon.PROJECTED

    def __post_init__(self) -> None:
        if not isinstance(self.student, StudentState):
            raise TypeError("student must be a StudentState")
        if not isinstance(self.semester, ProposedSemester):
            raise TypeError("semester must be a ProposedSemester")
        if not isinstance(self.load_policy, SemesterLoadPolicy):
            raise TypeError("load_policy must be a SemesterLoadPolicy")
        if not isinstance(self.horizon, EvaluationHorizon):
            raise TypeError("horizon must be an EvaluationHorizon")
        rules = tuple(self.rule_sets)
        if not all(isinstance(item, CourseEligibilityRuleSet) for item in rules):
            raise TypeError("rule_sets must contain CourseEligibilityRuleSet values")
        if len({item.target_course for item in rules}) != len(rules):
            raise ValueError("rule_sets must contain one entry per target course")
        object.__setattr__(
            self,
            "rule_sets",
            tuple(sorted(rules, key=lambda item: item.target_course.course_id)),
        )


@dataclass(frozen=True, slots=True)
class SemesterValidationResult:
    status: SemesterValidationStatus
    course_results: tuple[SemesterCourseResult, ...]
    load_result: SemesterLoadResult
    conditions: tuple[FutureCondition, ...]
    violations: tuple[SemesterValidationIssue, ...]
    review_items: tuple[SemesterValidationIssue, ...]
    metadata: ResultMetadata
    trace: DecisionTrace

    def __post_init__(self) -> None:
        if not isinstance(self.status, SemesterValidationStatus):
            raise TypeError("status must be a SemesterValidationStatus")
        courses = tuple(self.course_results)
        if not all(isinstance(item, SemesterCourseResult) for item in courses):
            raise TypeError("course_results must contain SemesterCourseResult values")
        if not isinstance(self.load_result, SemesterLoadResult):
            raise TypeError("load_result must be a SemesterLoadResult")
        conditions = tuple(self.conditions)
        if not all(isinstance(item, FutureCondition) for item in conditions):
            raise TypeError("conditions must contain FutureCondition values")
        for name in ("violations", "review_items"):
            values = tuple(getattr(self, name))
            if not all(isinstance(item, SemesterValidationIssue) for item in values):
                raise TypeError(f"{name} must contain SemesterValidationIssue values")
            object.__setattr__(self, name, values)
        if not isinstance(self.metadata, ResultMetadata):
            raise TypeError("metadata must be a ResultMetadata")
        if not isinstance(self.trace, DecisionTrace):
            raise TypeError("trace must be a DecisionTrace")
        object.__setattr__(
            self,
            "course_results",
            tuple(
                sorted(
                    courses, key=lambda item: item.proposed_course.identity.course_id
                )
            ),
        )
        object.__setattr__(self, "conditions", conditions)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "course_results": [item.to_dict() for item in self.course_results],
            "load_result": self.load_result.to_dict(),
            "conditions": [condition.to_dict() for condition in self.conditions],
            "violations": [item.to_dict() for item in self.violations],
            "review_items": [item.to_dict() for item in self.review_items],
            "metadata": self.metadata.to_dict(),
            "trace": self.trace.to_dict(),
        }


def _validate_number(value: object, name: str, *, nonnegative: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if nonnegative and value < 0:
        raise ValueError(f"{name} must be non-negative")


__all__ = [
    "LoadBand",
    "ProposedCourse",
    "ProposedSemester",
    "SemesterCourseResult",
    "SemesterIssueCode",
    "SemesterLoadPolicy",
    "SemesterLoadResult",
    "SemesterValidationIssue",
    "SemesterValidationRequest",
    "SemesterValidationResult",
    "SemesterValidationStatus",
    "TermType",
]
