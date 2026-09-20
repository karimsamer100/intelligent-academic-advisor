"""Typed candidate-generation contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .audit import DegreeAuditResult
from .context import EvaluationHorizon, RegistrationIntent
from .course import Course, CourseIdentity
from .dependency import DependencyGraph
from .electives import Concentration, ConcentrationId, ElectivePool
from .eligibility import (
    CourseEligibilityRuleSet,
    EligibilityResult,
)
from .requirements import ProgramRequirementSet
from .results import ResultMetadata
from .provenance import Provenance
from .student import StudentState
from .trace import DecisionTrace
from .uel import UELModuleId, UELProgressEvaluationResult, UELRiskLevel


class CandidateAvailability(StrEnum):
    """Candidate category; this is academic relevance, not course offering."""

    AVAILABLE = "AVAILABLE"
    CONDITIONAL = "CONDITIONAL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class CandidateReasonCode(StrEnum):
    REQUIRED_FOR_PROGRAM = "REQUIRED_FOR_PROGRAM"
    REQUIRED_ZERO_CREDIT = "REQUIRED_ZERO_CREDIT"
    ELECTIVE_REQUIREMENT = "ELECTIVE_REQUIREMENT"
    CONCENTRATION_PROGRESS = "CONCENTRATION_PROGRESS"
    UNLOCKS_REQUIRED_COURSE = "UNLOCKS_REQUIRED_COURSE"
    UNLOCKS_MULTIPLE_COURSES = "UNLOCKS_MULTIPLE_COURSES"
    PROJECTED_NEXT_STEP = "PROJECTED_NEXT_STEP"
    RETAKE_AFTER_FAILURE = "RETAKE_AFTER_FAILURE"
    RETAKE_FOR_IMPROVEMENT = "RETAKE_FOR_IMPROVEMENT"
    UEL_MODULE_OUTSTANDING = "UEL_MODULE_OUTSTANDING"
    UEL_PROGRESSION_RISK = "UEL_PROGRESSION_RISK"


class CandidateGenerationStatus(StrEnum):
    """Coverage of the candidate source inputs."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class CandidateIntent:
    course: CourseIdentity
    intent: RegistrationIntent

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")
        if not isinstance(self.intent, RegistrationIntent):
            raise TypeError("intent must be a RegistrationIntent")


@dataclass(frozen=True, slots=True)
class CandidateGenerationContext:
    """Deterministic horizon and proposed-term facts for candidate checks."""

    horizon: EvaluationHorizon = EvaluationHorizon.CURRENT
    proposed_courses: tuple[CourseIdentity, ...] = ()
    term_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.horizon, EvaluationHorizon):
            raise TypeError("horizon must be an EvaluationHorizon")
        courses = tuple(self.proposed_courses)
        if not all(isinstance(course, CourseIdentity) for course in courses):
            raise TypeError("proposed_courses must contain CourseIdentity values")
        if len(courses) != len(set(courses)):
            raise ValueError("proposed_courses must not contain duplicates")
        if self.term_id is not None and (
            not isinstance(self.term_id, str) or not self.term_id.strip()
        ):
            raise ValueError("term_id must be non-empty when provided")
        object.__setattr__(
            self,
            "proposed_courses",
            tuple(sorted(courses, key=lambda item: item.course_id)),
        )


@dataclass(frozen=True, slots=True)
class CandidateSourceCoverage:
    catalog: CandidateGenerationStatus = CandidateGenerationStatus.COMPLETE
    requirements: CandidateGenerationStatus = CandidateGenerationStatus.UNAVAILABLE
    eligibility_rules: CandidateGenerationStatus = CandidateGenerationStatus.UNAVAILABLE
    dependency_graph: CandidateGenerationStatus = CandidateGenerationStatus.UNAVAILABLE
    uel: CandidateGenerationStatus = CandidateGenerationStatus.UNAVAILABLE

    def __post_init__(self) -> None:
        for name in (
            "catalog",
            "requirements",
            "eligibility_rules",
            "dependency_graph",
            "uel",
        ):
            if not isinstance(getattr(self, name), CandidateGenerationStatus):
                raise TypeError(f"{name} must be a CandidateGenerationStatus")

    @property
    def overall(self) -> CandidateGenerationStatus:
        values = (
            self.catalog,
            self.requirements,
            self.eligibility_rules,
            self.dependency_graph,
        )
        if all(value is CandidateGenerationStatus.UNAVAILABLE for value in values):
            return CandidateGenerationStatus.UNAVAILABLE
        if any(value is not CandidateGenerationStatus.COMPLETE for value in values):
            return CandidateGenerationStatus.INCOMPLETE
        return CandidateGenerationStatus.COMPLETE

    def to_dict(self) -> dict[str, object]:
        return {
            "catalog": self.catalog.value,
            "requirements": self.requirements.value,
            "eligibility_rules": self.eligibility_rules.value,
            "dependency_graph": self.dependency_graph.value,
            "uel": self.uel.value,
            "overall": self.overall.value,
            "uel_awareness": self.uel.value,
        }


@dataclass(frozen=True, slots=True)
class CandidateGenerationRequest:
    student: StudentState
    courses: tuple[Course, ...]
    requirement_set: ProgramRequirementSet | None = None
    degree_audit: DegreeAuditResult | None = None
    rule_sets: tuple[CourseEligibilityRuleSet, ...] = ()
    dependency_graph: DependencyGraph | None = None
    pools: tuple[ElectivePool, ...] = ()
    concentrations: tuple[Concentration, ...] = ()
    context: CandidateGenerationContext = field(
        default_factory=CandidateGenerationContext
    )
    intents: tuple[CandidateIntent, ...] = ()
    source_coverage: CandidateSourceCoverage = field(
        default_factory=CandidateSourceCoverage
    )
    uel_evaluation: UELProgressEvaluationResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.student, StudentState):
            raise TypeError("student must be a StudentState")
        courses = tuple(self.courses)
        if not all(isinstance(item, Course) for item in courses):
            raise TypeError("courses must contain Course values")
        if len({item.identity for item in courses}) != len(courses):
            raise ValueError("courses must contain unique canonical identities")
        if self.requirement_set is not None and not isinstance(
            self.requirement_set, ProgramRequirementSet
        ):
            raise TypeError("requirement_set must be a ProgramRequirementSet or None")
        if self.degree_audit is not None and not isinstance(
            self.degree_audit, DegreeAuditResult
        ):
            raise TypeError("degree_audit must be a DegreeAuditResult or None")
        rules = tuple(self.rule_sets)
        if not all(isinstance(item, CourseEligibilityRuleSet) for item in rules):
            raise TypeError("rule_sets must contain CourseEligibilityRuleSet values")
        if len({item.target_course for item in rules}) != len(rules):
            raise ValueError("rule_sets must have unique target courses")
        pools = tuple(self.pools)
        concentrations = tuple(self.concentrations)
        if not all(isinstance(item, ElectivePool) for item in pools):
            raise TypeError("pools must contain ElectivePool values")
        if not all(isinstance(item, Concentration) for item in concentrations):
            raise TypeError("concentrations must contain Concentration values")
        intents = tuple(self.intents)
        if not all(isinstance(item, CandidateIntent) for item in intents):
            raise TypeError("intents must contain CandidateIntent values")
        if len({item.course for item in intents}) != len(intents):
            raise ValueError("intents must contain unique courses")
        if not isinstance(self.context, CandidateGenerationContext):
            raise TypeError("context must be a CandidateGenerationContext")
        if not isinstance(self.source_coverage, CandidateSourceCoverage):
            raise TypeError("source_coverage must be CandidateSourceCoverage")
        if self.uel_evaluation is not None and not isinstance(
            self.uel_evaluation, UELProgressEvaluationResult
        ):
            raise TypeError(
                "uel_evaluation must be a UELProgressEvaluationResult or None"
            )
        for item in courses:
            if (
                item.identity.regulation is not self.student.regulation
                or item.identity.program != self.student.program
            ):
                raise ValueError("course scope must match student scope")
        if self.requirement_set is not None and (
            self.requirement_set.regulation is not self.student.regulation
            or self.requirement_set.program != self.student.program
        ):
            raise ValueError("requirement-set scope must match student scope")
        if self.dependency_graph is not None and (
            self.dependency_graph.scope.regulation is not self.student.regulation
            or self.dependency_graph.scope.program != self.student.program
        ):
            raise ValueError("dependency-graph scope must match student scope")
        object.__setattr__(
            self,
            "courses",
            tuple(sorted(courses, key=lambda item: item.identity.course_id)),
        )
        object.__setattr__(
            self,
            "rule_sets",
            tuple(sorted(rules, key=lambda item: item.target_course.course_id)),
        )
        object.__setattr__(
            self,
            "pools",
            tuple(sorted(pools, key=lambda item: item.pool_id.identifier)),
        )
        object.__setattr__(
            self,
            "concentrations",
            tuple(
                sorted(
                    concentrations, key=lambda item: item.concentration_id.identifier
                )
            ),
        )
        object.__setattr__(
            self,
            "intents",
            tuple(sorted(intents, key=lambda item: item.course.course_id)),
        )


@dataclass(frozen=True, slots=True)
class CandidateCourse:
    course: Course
    eligibility: EligibilityResult | None
    availability: CandidateAvailability
    reason_codes: tuple[CandidateReasonCode, ...]
    requirement_ids: tuple[str, ...] = ()
    unlocks: tuple[CourseIdentity, ...] = ()
    concentration_ids: tuple[ConcentrationId, ...] = ()
    uel_module_ids: tuple[UELModuleId, ...] = ()
    uel_risk_level: UELRiskLevel | None = None
    uel_provenance: tuple[Provenance, ...] = ()
    metadata: ResultMetadata | None = None
    trace: DecisionTrace | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.course, Course):
            raise TypeError("course must be a Course")
        if not isinstance(self.availability, CandidateAvailability):
            raise TypeError("availability must be a CandidateAvailability")
        reasons = tuple(dict.fromkeys(self.reason_codes))
        if not all(isinstance(item, CandidateReasonCode) for item in reasons):
            raise TypeError("reason_codes must contain CandidateReasonCode values")
        if self.eligibility is not None and not isinstance(
            self.eligibility, EligibilityResult
        ):
            raise TypeError("eligibility must be an EligibilityResult or None")
        if self.metadata is not None and not isinstance(self.metadata, ResultMetadata):
            raise TypeError("metadata must be a ResultMetadata or None")
        if self.trace is not None and not isinstance(self.trace, DecisionTrace):
            raise TypeError("trace must be a DecisionTrace or None")
        if self.eligibility is not None and self.metadata is None:
            object.__setattr__(self, "metadata", self.eligibility.metadata)
        if self.trace is None and self.metadata is not None:
            object.__setattr__(self, "trace", self.metadata.decision_trace)
        for name in ("requirement_ids",):
            values = tuple(getattr(self, name))
            if not all(isinstance(item, str) and item.strip() for item in values):
                raise TypeError(f"{name} must contain non-empty strings")
            object.__setattr__(self, name, tuple(sorted(set(values))))
        for name in ("unlocks",):
            values = tuple(getattr(self, name))
            if not all(isinstance(item, CourseIdentity) for item in values):
                raise TypeError(f"{name} must contain CourseIdentity values")
            object.__setattr__(
                self, name, tuple(sorted(set(values), key=lambda item: item.course_id))
            )
        values = tuple(self.concentration_ids)
        if not all(isinstance(item, ConcentrationId) for item in values):
            raise TypeError("concentration_ids must contain ConcentrationId values")
        object.__setattr__(
            self,
            "concentration_ids",
            tuple(sorted(set(values), key=lambda item: item.identifier)),
        )
        uel_modules = tuple(self.uel_module_ids)
        if not all(isinstance(item, UELModuleId) for item in uel_modules):
            raise TypeError("uel_module_ids must contain UELModuleId values")
        object.__setattr__(
            self, "uel_module_ids", tuple(sorted(set(uel_modules), key=str))
        )
        if self.uel_risk_level is not None and not isinstance(
            self.uel_risk_level, UELRiskLevel
        ):
            raise TypeError("uel_risk_level must be a UELRiskLevel or None")
        uel_provenance = tuple(self.uel_provenance)
        if not all(isinstance(item, Provenance) for item in uel_provenance):
            raise TypeError("uel_provenance must contain Provenance values")
        object.__setattr__(
            self,
            "uel_provenance",
            tuple(dict.fromkeys(uel_provenance)),
        )
        object.__setattr__(
            self, "reason_codes", tuple(sorted(reasons, key=lambda item: item.value))
        )

    @property
    def identity(self) -> CourseIdentity:
        return self.course.identity

    def to_dict(self) -> dict[str, object]:
        return {
            "course": self.course.identity.course_id,
            "availability": self.availability.value,
            "eligibility": self.eligibility.to_dict() if self.eligibility else None,
            "reason_codes": [item.value for item in self.reason_codes],
            "requirement_ids": list(self.requirement_ids),
            "unlocks": [item.course_id for item in self.unlocks],
            "concentration_ids": [item.identifier for item in self.concentration_ids],
            "uel_module_ids": [item.module_id for item in self.uel_module_ids],
            "uel_risk_level": (
                self.uel_risk_level.value if self.uel_risk_level is not None else None
            ),
            "uel_provenance": [item.to_dict() for item in self.uel_provenance],
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "trace": self.trace.to_dict() if self.trace else None,
        }


@dataclass(frozen=True, slots=True)
class CandidateGenerationResult:
    status: CandidateGenerationStatus
    available_candidates: tuple[CandidateCourse, ...]
    conditional_candidates: tuple[CandidateCourse, ...]
    review_candidates: tuple[CandidateCourse, ...]
    excluded_course_ids: tuple[CourseIdentity, ...]
    source_coverage: CandidateSourceCoverage
    metadata: ResultMetadata
    trace: DecisionTrace

    def __post_init__(self) -> None:
        if not isinstance(self.status, CandidateGenerationStatus):
            raise TypeError("status must be a CandidateGenerationStatus")
        for name in (
            "available_candidates",
            "conditional_candidates",
            "review_candidates",
        ):
            values = tuple(getattr(self, name))
            if not all(isinstance(item, CandidateCourse) for item in values):
                raise TypeError(f"{name} must contain CandidateCourse values")
            object.__setattr__(
                self,
                name,
                tuple(sorted(values, key=lambda item: item.identity.course_id)),
            )
        excluded = tuple(self.excluded_course_ids)
        if not all(isinstance(item, CourseIdentity) for item in excluded):
            raise TypeError("excluded_course_ids must contain CourseIdentity values")
        object.__setattr__(
            self,
            "excluded_course_ids",
            tuple(sorted(set(excluded), key=lambda item: item.course_id)),
        )
        if not isinstance(self.source_coverage, CandidateSourceCoverage):
            raise TypeError("source_coverage must be CandidateSourceCoverage")
        if not isinstance(self.metadata, ResultMetadata):
            raise TypeError("metadata must be a ResultMetadata")
        if not isinstance(self.trace, DecisionTrace):
            raise TypeError("trace must be a DecisionTrace")

    @property
    def candidates(self) -> tuple[CandidateCourse, ...]:
        return (
            *self.available_candidates,
            *self.conditional_candidates,
            *self.review_candidates,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "source_coverage": self.source_coverage.to_dict(),
            "available_candidates": [
                item.to_dict() for item in self.available_candidates
            ],
            "conditional_candidates": [
                item.to_dict() for item in self.conditional_candidates
            ],
            "review_candidates": [item.to_dict() for item in self.review_candidates],
            "excluded_course_ids": [
                item.course_id for item in self.excluded_course_ids
            ],
            "metadata": self.metadata.to_dict(),
            "trace": self.trace.to_dict(),
        }


__all__ = [
    "CandidateAvailability",
    "CandidateCourse",
    "CandidateGenerationContext",
    "CandidateGenerationRequest",
    "CandidateGenerationResult",
    "CandidateGenerationStatus",
    "CandidateIntent",
    "CandidateReasonCode",
    "CandidateSourceCoverage",
]
