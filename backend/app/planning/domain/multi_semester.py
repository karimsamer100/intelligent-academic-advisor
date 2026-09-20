"""Typed contracts for bounded multi-semester academic projections."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .audit import DegreeAuditResult
from .candidates import CandidateGenerationRequest
from .conditions import FutureCondition
from .context import EvaluationHorizon
from .course import CourseIdentity
from .planning import (
    PlanDiagnostic,
    PlanningCoverage,
    PlanningPreferences,
    PlanningSearchPolicy,
    SingleSemesterPlanResult,
)
from .program_facts import StudentProgramFacts
from .projection import ProjectionPolicy
from .results import ResultMetadata
from .semester import SemesterLoadPolicy, TermType
from .student import StudentState
from .uel import UELProgressEvaluationResult
from .academic_state import HypotheticalAcademicOutcome
from .trace import DecisionTrace


class MultiSemesterPlanStatus(StrEnum):
    COMPLETION_PATH_FOUND = "COMPLETION_PATH_FOUND"
    PARTIAL_PATH = "PARTIAL_PATH"
    CONDITIONAL_PATH = "CONDITIONAL_PATH"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NO_PROGRESS = "NO_PROGRESS"
    NO_FEASIBLE_PATH = "NO_FEASIBLE_PATH"
    UNSUPPORTED = "UNSUPPORTED"


class MultiSemesterStopReason(StrEnum):
    ACADEMIC_REQUIREMENTS_SATISFIED = "ACADEMIC_REQUIREMENTS_SATISFIED"
    HORIZON_REACHED = "HORIZON_REACHED"
    NO_CANDIDATES = "NO_CANDIDATES"
    NO_FEASIBLE_SEMESTER = "NO_FEASIBLE_SEMESTER"
    NO_PROGRESS = "NO_PROGRESS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True, slots=True)
class PlanningTerm:
    index: int
    term_type: TermType
    term_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int):
            raise TypeError("index must be an integer")
        if self.index < 1:
            raise ValueError("index must be at least 1")
        if not isinstance(self.term_type, TermType):
            raise TypeError("term_type must be a TermType")
        if self.term_id is not None and (
            not isinstance(self.term_id, str) or not self.term_id.strip()
        ):
            raise ValueError("term_id must be non-empty when provided")

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "term_type": self.term_type.value,
            "term_id": self.term_id,
        }


@dataclass(frozen=True, slots=True)
class MultiSemesterSearchPolicy:
    """Engineering bounds for forward projection, not academic rules."""

    max_semesters: int = 4
    max_path_branches: int = 1
    max_alternatives: int = 1

    def __post_init__(self) -> None:
        for name in ("max_semesters", "max_path_branches"):
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
            "max_semesters": self.max_semesters,
            "max_path_branches": self.max_path_branches,
            "max_alternatives": self.max_alternatives,
        }


@dataclass(frozen=True, slots=True)
class ProjectedStateSummary:
    student_id: str
    fact_layer: str
    earned_credit_hours: int | float | None
    credits_known: bool
    projected_courses: tuple[str, ...] = ()

    @classmethod
    def from_student(cls, student: StudentState) -> "ProjectedStateSummary":
        return cls(
            student_id=student.student_id,
            fact_layer=student.fact_layer.value,
            earned_credit_hours=student.earned_credit_hours,
            credits_known=student.earned_credit_hours is not None,
            projected_courses=tuple(
                sorted({item.course.course_id for item in student.projected_outcomes})
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "student_id": self.student_id,
            "fact_layer": self.fact_layer,
            "earned_credit_hours": self.earned_credit_hours,
            "credits_known": self.credits_known,
            "projected_courses": list(self.projected_courses),
        }


@dataclass(frozen=True, slots=True)
class MultiSemesterPlanStep:
    term: PlanningTerm
    input_state: ProjectedStateSummary
    plan: SingleSemesterPlanResult
    applied_outcomes: tuple[HypotheticalAcademicOutcome, ...]
    output_state: ProjectedStateSummary
    audit: DegreeAuditResult | None
    conditions: tuple[FutureCondition, ...] = ()
    trace: DecisionTrace | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.term, PlanningTerm):
            raise TypeError("term must be a PlanningTerm")
        if not isinstance(self.input_state, ProjectedStateSummary):
            raise TypeError("input_state must be a ProjectedStateSummary")
        if not isinstance(self.plan, SingleSemesterPlanResult):
            raise TypeError("plan must be a SingleSemesterPlanResult")
        outcomes = tuple(self.applied_outcomes)
        if not all(isinstance(item, HypotheticalAcademicOutcome) for item in outcomes):
            raise TypeError(
                "applied_outcomes must contain HypotheticalAcademicOutcome values"
            )
        if not isinstance(self.output_state, ProjectedStateSummary):
            raise TypeError("output_state must be a ProjectedStateSummary")
        if self.audit is not None and not isinstance(self.audit, DegreeAuditResult):
            raise TypeError("audit must be a DegreeAuditResult or None")
        conditions = tuple(self.conditions)
        if not all(isinstance(item, FutureCondition) for item in conditions):
            raise TypeError("conditions must contain FutureCondition values")
        if self.trace is not None and not isinstance(self.trace, DecisionTrace):
            raise TypeError("trace must be a DecisionTrace or None")
        object.__setattr__(self, "applied_outcomes", outcomes)
        object.__setattr__(self, "conditions", _unique_conditions(conditions))

    def to_dict(self) -> dict[str, object]:
        return {
            "term": self.term.to_dict(),
            "input_state": self.input_state.to_dict(),
            "plan": self.plan.to_dict(),
            "applied_outcomes": [item.to_dict() for item in self.applied_outcomes],
            "output_state": self.output_state.to_dict(),
            "audit": self.audit.to_dict() if self.audit else None,
            "conditions": [item.to_dict() for item in self.conditions],
            "trace": self.trace.to_dict() if self.trace else None,
        }


@dataclass(frozen=True, slots=True)
class MultiSemesterPlanningRequest:
    initial_student: StudentState
    candidate_request: CandidateGenerationRequest
    load_policy: SemesterLoadPolicy
    max_semesters: int = 4
    term_sequence: tuple[PlanningTerm, ...] = ()
    horizon: EvaluationHorizon = EvaluationHorizon.PROJECTED
    preferences: PlanningPreferences = field(default_factory=PlanningPreferences)
    single_search_policy: PlanningSearchPolicy = field(
        default_factory=PlanningSearchPolicy
    )
    search_policy: MultiSemesterSearchPolicy = field(
        default_factory=MultiSemesterSearchPolicy
    )
    projection_policy: ProjectionPolicy = (
        ProjectionPolicy.ASSUME_SELECTED_COURSES_PASSED
    )
    program_facts: StudentProgramFacts = field(default_factory=StudentProgramFacts)
    excluded_courses: tuple[CourseIdentity, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.initial_student, StudentState):
            raise TypeError("initial_student must be a StudentState")
        if not isinstance(self.candidate_request, CandidateGenerationRequest):
            raise TypeError("candidate_request must be a CandidateGenerationRequest")
        if self.candidate_request.student != self.initial_student:
            raise ValueError("candidate request and initial student must match")
        if not isinstance(self.load_policy, SemesterLoadPolicy):
            raise TypeError("load_policy must be a SemesterLoadPolicy")
        if (
            self.load_policy.regulation is not self.initial_student.regulation
            or self.load_policy.program != self.initial_student.program
        ):
            raise ValueError("load policy scope must match initial student")
        if isinstance(self.max_semesters, bool) or not isinstance(
            self.max_semesters, int
        ):
            raise TypeError("max_semesters must be an integer")
        if self.max_semesters < 1:
            raise ValueError("max_semesters must be positive")
        if not isinstance(self.horizon, EvaluationHorizon):
            raise TypeError("horizon must be an EvaluationHorizon")
        if not isinstance(self.preferences, PlanningPreferences):
            raise TypeError("preferences must be PlanningPreferences")
        if not isinstance(self.single_search_policy, PlanningSearchPolicy):
            raise TypeError("single_search_policy must be PlanningSearchPolicy")
        if not isinstance(self.search_policy, MultiSemesterSearchPolicy):
            raise TypeError("search_policy must be MultiSemesterSearchPolicy")
        if not isinstance(self.projection_policy, ProjectionPolicy):
            raise TypeError("projection_policy must be a ProjectionPolicy")
        if not isinstance(self.program_facts, StudentProgramFacts):
            raise TypeError("program_facts must be StudentProgramFacts")
        terms = tuple(self.term_sequence)
        if not all(isinstance(item, PlanningTerm) for item in terms):
            raise TypeError("term_sequence must contain PlanningTerm values")
        if len({item.index for item in terms}) != len(terms):
            raise ValueError("term_sequence indexes must be unique")
        if terms and len(terms) < self.max_semesters:
            raise ValueError("term_sequence must cover max_semesters")
        excluded = tuple(self.excluded_courses)
        if not all(isinstance(item, CourseIdentity) for item in excluded):
            raise TypeError("excluded_courses must contain CourseIdentity values")
        if len(excluded) != len(set(excluded)):
            raise ValueError("excluded_courses must be unique")
        if any(
            item.regulation is not self.initial_student.regulation
            or item.program != self.initial_student.program
            for item in excluded
        ):
            raise ValueError("excluded course scope must match initial student scope")
        object.__setattr__(
            self,
            "term_sequence",
            tuple(sorted(terms, key=lambda item: item.index)),
        )
        object.__setattr__(
            self,
            "excluded_courses",
            tuple(sorted(excluded, key=lambda item: item.course_id)),
        )

    @property
    def terms(self) -> tuple[PlanningTerm, ...]:
        if self.term_sequence:
            return self.term_sequence[: self.max_semesters]
        return tuple(
            PlanningTerm(index, TermType.MAIN)
            for index in range(1, self.max_semesters + 1)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "student_id": self.initial_student.student_id,
            "max_semesters": self.max_semesters,
            "terms": [item.to_dict() for item in self.terms],
            "horizon": self.horizon.value,
            "preferences": self.preferences.to_dict(),
            "single_search_policy": self.single_search_policy.to_dict(),
            "search_policy": self.search_policy.to_dict(),
            "projection_policy": self.projection_policy.value,
            "excluded_courses": [item.course_id for item in self.excluded_courses],
        }


@dataclass(frozen=True, slots=True)
class MultiSemesterPlanResult:
    status: MultiSemesterPlanStatus
    initial_state: StudentState
    final_state: StudentState
    steps: tuple[MultiSemesterPlanStep, ...]
    final_audit: DegreeAuditResult | None
    stop_reason: MultiSemesterStopReason
    projection_policy: ProjectionPolicy
    conditions: tuple[FutureCondition, ...]
    review_items: tuple[PlanDiagnostic, ...]
    coverage: PlanningCoverage
    metadata: ResultMetadata
    trace: DecisionTrace
    uel_evaluation: UELProgressEvaluationResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, MultiSemesterPlanStatus):
            raise TypeError("status must be a MultiSemesterPlanStatus")
        if not isinstance(self.initial_state, StudentState):
            raise TypeError("initial_state must be a StudentState")
        if not isinstance(self.final_state, StudentState):
            raise TypeError("final_state must be a StudentState")
        steps = tuple(self.steps)
        if not all(isinstance(item, MultiSemesterPlanStep) for item in steps):
            raise TypeError("steps must contain MultiSemesterPlanStep values")
        if self.final_audit is not None and not isinstance(
            self.final_audit, DegreeAuditResult
        ):
            raise TypeError("final_audit must be a DegreeAuditResult or None")
        if not isinstance(self.stop_reason, MultiSemesterStopReason):
            raise TypeError("stop_reason must be a MultiSemesterStopReason")
        if not isinstance(self.projection_policy, ProjectionPolicy):
            raise TypeError("projection_policy must be a ProjectionPolicy")
        conditions = tuple(self.conditions)
        if not all(isinstance(item, FutureCondition) for item in conditions):
            raise TypeError("conditions must contain FutureCondition values")
        review_items = tuple(self.review_items)
        if not all(isinstance(item, PlanDiagnostic) for item in review_items):
            raise TypeError("review_items must contain PlanDiagnostic values")
        if not isinstance(self.coverage, PlanningCoverage):
            raise TypeError("coverage must be PlanningCoverage")
        if not isinstance(self.metadata, ResultMetadata):
            raise TypeError("metadata must be ResultMetadata")
        if not isinstance(self.trace, DecisionTrace):
            raise TypeError("trace must be a DecisionTrace")
        if self.uel_evaluation is not None and not isinstance(
            self.uel_evaluation, UELProgressEvaluationResult
        ):
            raise TypeError(
                "uel_evaluation must be a UELProgressEvaluationResult or None"
            )
        object.__setattr__(self, "steps", steps)
        object.__setattr__(self, "conditions", _unique_conditions(conditions))
        object.__setattr__(self, "review_items", review_items)

    @property
    def academic_path_valid(self) -> bool:
        return self.status is MultiSemesterPlanStatus.COMPLETION_PATH_FOUND

    @property
    def registration_ready(self) -> bool:
        return (
            self.academic_path_valid
            and self.coverage.overall.value == "COMPLETE"
            and self.metadata.authoritative
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "initial_state": ProjectedStateSummary.from_student(
                self.initial_state
            ).to_dict(),
            "final_state": ProjectedStateSummary.from_student(
                self.final_state
            ).to_dict(),
            "steps": [item.to_dict() for item in self.steps],
            "final_audit": self.final_audit.to_dict() if self.final_audit else None,
            "stop_reason": self.stop_reason.value,
            "projection_policy": self.projection_policy.value,
            "conditions": [item.to_dict() for item in self.conditions],
            "review_items": [item.to_dict() for item in self.review_items],
            "coverage": self.coverage.to_dict(),
            "academic_path_valid": self.academic_path_valid,
            "registration_ready": self.registration_ready,
            "metadata": self.metadata.to_dict(),
            "trace": self.trace.to_dict(),
            "uel_evaluation": (
                self.uel_evaluation.to_dict() if self.uel_evaluation else None
            ),
        }


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
    "MultiSemesterPlanResult",
    "MultiSemesterPlanStatus",
    "MultiSemesterPlanStep",
    "MultiSemesterPlanningRequest",
    "MultiSemesterSearchPolicy",
    "MultiSemesterStopReason",
    "PlanningTerm",
    "ProjectedStateSummary",
]
